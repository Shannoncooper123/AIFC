"""持仓开平仓管理"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.agent.trade_simulator.models import Account, Position
from modules.agent.trade_simulator.storage import ConfigFacade
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.trade_engine.position_manager')


class PositionManager:
    """持仓管理服务：负责开平仓逻辑"""
    def __init__(self, config: Dict, account: Account, positions: Dict[str, Position],
                 risk_service, state_manager, lock: threading.RLock):
        self.cfg = ConfigFacade(config)
        self.account = account
        self.positions = positions
        self.risk = risk_service
        self.state = state_manager
        self.lock = lock
        self.rest = BinanceRestClient(config)
        self.max_leverage = self.cfg.max_leverage
        self.ws_interval = self.cfg.ws_interval

    def get_latest_close_price(self, symbol: str) -> Optional[float]:
        """获取最新收盘价"""
        try:
            kl = self.rest.get_klines(symbol, self.ws_interval, limit=1)
            if isinstance(kl, list) and kl:
                return float(kl[0][4])  # close
        except Exception as e:
            logger.error(f"获取价格失败: symbol={symbol}, error={e}")
            return None
        return None

    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """获取持仓汇总"""
        with self.lock:
            items: List[Dict[str, Any]] = []
            for p in self.positions.values():
                if p.status != 'open':
                    continue
                mark = p.latest_mark_price or p.entry_price
                items.append({
                    'id': p.id,
                    'symbol': p.symbol,
                    'side': p.side,
                    'qty': round(p.qty, 8),
                    'entry_price': round(p.entry_price, 8),
                    'leverage': p.leverage,
                    'tp_price': p.tp_price,
                    'sl_price': p.sl_price,
                    'original_sl_price': p.original_sl_price,  # 添加原始止损价
                    'original_tp_price': p.original_tp_price,  # 添加原始止盈价
                    'mark_price': round(mark, 8),
                    'unrealized_pnl': round(p.unrealized_pnl(mark), 6),
                    'roe': round(p.roe(mark), 6),
                    'opened_at': p.open_time,
                    'operation_history': p.operation_history,  # 添加操作历史
                })
            return items

    def open_position(self, symbol: str, side: str, quote_notional_usdt: float, leverage: int,
                      tp_price: Optional[float] = None, sl_price: Optional[float] = None,
                      entry_price: Optional[float] = None, pre_reserved_margin: bool = False) -> Dict[str, Any]:
        """开仓或加仓
        
        Args:
            symbol: 交易对
            side: 方向（long/short）
            quote_notional_usdt: 名义价值（由工具层计算：保证金 × 杠杆）
            leverage: 杠杆倍数
            tp_price: 止盈价（可选）
            sl_price: 止损价（可选）
        
        Note:
            调用链路：
            1. 用户输入保证金 margin_usdt（如 100U）
            2. 工具层计算名义价值：notional = margin_usdt × leverage（100 × 10 = 1000U）
            3. 传入本方法：quote_notional_usdt = 1000U
            4. 本方法反算保证金：margin = notional / leverage（1000 / 10 = 100U）
            
            这样设计的原因：
            - 工具层统一处理用户输入（保证金）到名义价值的转换
            - 引擎层基于名义价值计算数量和保证金需求
            - 保持与历史逻辑兼容
        """
        with self.lock:
            logger.info(f"open_position: symbol={symbol}, side={side}, lev={leverage}, notional={quote_notional_usdt}, tp_price={tp_price}, sl_price={sl_price}")

            # 校验参数
            if side not in ("long", "short"):
                logger.error("open_position: 参数错误 side")
                return {"error": "TOOL_INPUT_ERROR: side必须为long/short"}
            if leverage < 1 or leverage > self.max_leverage:
                logger.error("open_position: 参数错误 leverage 超限")
                return {"error": f"TOOL_INPUT_ERROR: leverage需在1..{self.max_leverage}"}
            if quote_notional_usdt <= 0:
                logger.error("open_position: 参数错误 notional <= 0")
                return {"error": "TOOL_INPUT_ERROR: quote_notional_usdt必须>0"}

            # 同一交易对仅允许一边仓位
            if symbol in self.positions and self.positions[symbol].status == 'open':
                pos0 = self.positions[symbol]
                if pos0.side != side:
                    logger.error("open_position: 对向仓位冲突，禁止")
                    return {"error": "TOOL_INPUT_ERROR: 同一交易对仅允许一边仓位，不能对向"}

            # 获取入场价格
            entry = entry_price or self.get_latest_close_price(symbol)
            if entry is None:
                logger.error("open_position: 获取入场价格失败")
                return {"error": "TOOL_RUNTIME_ERROR: 获取价格失败"}

            # 基于名义价值计算数量和实际保证金需求
            qty_add = quote_notional_usdt / entry  # 持仓数量 = 名义价值 / 价格
            margin_add = quote_notional_usdt / float(leverage)  # 保证金需求 = 名义价值 / 杠杆

            # 保证金检查
            if pre_reserved_margin:
                if self.account.reserved_margin_sum < margin_add:
                    logger.warning("open_position: 预占保证金不足")
                    return {"error": "TOOL_INPUT_ERROR: 预占保证金不足"}
            else:
                free_bal = self.account.balance - self.account.reserved_margin_sum
                if free_bal < margin_add:
                    logger.warning(f"open_position: 保证金不足 free={free_bal:.4f} < need={margin_add:.4f}")
                    return {"error": "TOOL_INPUT_ERROR: 保证金不足"}

            # 手续费（开仓）
            fee_open = self.risk.charge_open_fee(quote_notional_usdt)
            if not pre_reserved_margin:
                self.account.reserved_margin_sum += margin_add

            # 建立/加仓
            if symbol not in self.positions or self.positions[symbol].status != 'open':
                pid = uuid.uuid4().hex[:12]
                pos = Position(
                    id=pid,
                    symbol=symbol,
                    side=side,
                    qty=qty_add,
                    entry_price=entry,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    original_sl_price=sl_price,  # 记录开仓时的原始止损价
                    original_tp_price=tp_price,  # 记录开仓时的原始止盈价
                    leverage=int(leverage),
                    notional_usdt=quote_notional_usdt,
                    margin_used=margin_add,
                    fees_open=fee_open,
                    operation_history=[{  # 初始化操作历史
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "operation": "open",
                        "details": {
                            "entry_price": entry,
                            "tp_price": tp_price,
                            "sl_price": sl_price,
                            "notional": quote_notional_usdt,
                            "leverage": int(leverage),
                            "margin_usdt": margin_add
                        }
                    }]
                )
                pos.latest_mark_price = entry
                self.positions[symbol] = pos
                logger.info(f"open_position: 建立持仓 id={pid}, entry={entry:.6f}, qty={pos.qty:.8f}, tp={pos.tp_price}, sl={pos.sl_price}, margin={pos.margin_used:.6f}")

            else:
                pos = self.positions[symbol]
                # 记录加仓前的状态
                old_entry = pos.entry_price
                old_qty = pos.qty
                old_margin = pos.margin_used

                # 加权重算均价
                total_notional = pos.notional_usdt + quote_notional_usdt
                total_qty = pos.qty + qty_add
                new_entry = ((pos.entry_price * pos.qty) + (entry * qty_add)) / total_qty
                pos.entry_price = new_entry
                pos.qty = total_qty
                pos.notional_usdt = total_notional
                pos.margin_used += margin_add
                pos.fees_open += fee_open

                # TP/SL若传入则更新
                old_tp = pos.tp_price
                old_sl = pos.sl_price
                if tp_price is not None:
                    pos.tp_price = tp_price
                if sl_price is not None:
                    pos.sl_price = sl_price
                pos.latest_mark_price = entry

                # 添加加仓操作到历史
                pos.operation_history.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "operation": "add_position",
                    "details": {
                        "add_qty": qty_add,
                        "add_margin": margin_add,
                        "add_notional": quote_notional_usdt,
                        "current_price": entry,
                        "old_entry": old_entry,
                        "new_entry": new_entry,
                        "old_qty": old_qty,
                        "new_qty": total_qty,
                        "old_margin": old_margin,
                        "new_margin": pos.margin_used,
                        "old_tp": old_tp,
                        "new_tp": pos.tp_price,
                        "old_sl": old_sl,
                        "new_sl": pos.sl_price,
                        "leverage": int(leverage)
                    }
                })

                logger.info(f"open_position: 加仓 symbol={symbol}, new_entry={new_entry:.6f}, qty={pos.qty:.8f}, notional={pos.notional_usdt:.6f}, margin={pos.margin_used:.6f}, tp={pos.tp_price}, sl={pos.sl_price}")

            return self.state.pos_to_dict(self.positions[symbol])

    def close_position(self, position_id: Optional[str] = None, symbol: Optional[str] = None,
                       close_reason: Optional[str] = None, close_price: Optional[float] = None) -> Dict[str, Any]:
        """平仓（全平）
        
        Args:
            position_id: 持仓ID（可选）
            symbol: 交易对（可选）
            close_reason: 平仓原因（可选）
            close_price: 指定平仓价格（可选），如果提供则使用此价格，否则使用当前市场价格
        """
        with self.lock:
            # 查找持仓
            pos: Optional[Position] = None
            if symbol and symbol in self.positions:
                pos = self.positions[symbol]
            else:
                for p in self.positions.values():
                    if p.id == position_id:
                        pos = p
                        break

            if not pos or pos.status != 'open':
                logger.error(f"close_position: 未找到可平持仓 (查询: position_id={position_id}, symbol={symbol})")
                return {"error": "TOOL_INPUT_ERROR: 未找到可平持仓"}

            # 日志中显示实际找到的持仓信息
            logger.info(f"close_position: position_id={pos.id}, symbol={pos.symbol}, reason={close_reason}, close_price={close_price}")

            # 如果提供了 close_price 则使用指定价格，否则使用当前市场价格
            if close_price is not None:
                mark = close_price
            else:
                mark = pos.latest_mark_price or self.get_latest_close_price(pos.symbol) or pos.entry_price
            original_notional = pos.notional_usdt
            original_qty = pos.qty
            original_margin = pos.margin_used

            # 全平
            notional_close = pos.qty * mark
            if pos.side == 'long':
                pnl = pos.qty * (mark - pos.entry_price)
            else:
                pnl = pos.qty * (pos.entry_price - mark)

            self.account.balance += pnl
            fee_close = self.risk.charge_close_fee(notional_close)
            self.account.realized_pnl += pnl
            pos.realized_pnl += pnl

            # 释放保证金
            self.account.reserved_margin_sum -= pos.margin_used
            pos.fees_close += fee_close

            pos.status = 'closed'
            pos.close_price = mark
            pos.close_time = datetime.now(timezone.utc).isoformat()
            pos.close_reason = close_reason or 'agent'  # 记录平仓原因
            pos.qty = 0.0
            pos.notional_usdt = 0.0
            pos.margin_used = 0.0

            # 添加平仓操作到历史
            pos.operation_history.append({
                "timestamp": pos.close_time,
                "operation": "close",
                "details": {
                    "close_price": mark,
                    "realized_pnl": pos.realized_pnl,
                    "close_reason": pos.close_reason,
                    "trigger_type": self._get_trigger_type(pos.close_reason)
                }
            })

            logger.info(f"close_position: symbol={pos.symbol}, close_price={mark:.6f}, realized_pnl={pos.realized_pnl:.6f}, fee={fee_close:.6f}, original_notional={original_notional:.6f}, reason={pos.close_reason}")

            # 记录平仓事件
            evt_payload = self.state.pos_to_dict(pos)
            evt_payload['notional_usdt'] = original_notional
            evt_payload['qty'] = original_qty
            evt_payload['margin_used'] = original_margin
            evt_payload.update({'action': 'close_position', 'close_reason': close_reason})
            self.state.log_operation('close_position', evt_payload)
            logger.info(f"close_position: 历史记录调用完成, symbol={pos.symbol}")

            return self.state.pos_to_dict(pos)

    def _get_trigger_type(self, close_reason: Optional[str]) -> str:
        """判断平仓触发类型"""
        if close_reason in ('止盈', '止损'):
            return 'auto'  # 自动触发
        elif close_reason == 'agent':
            return 'manual'  # Agent 主动平仓
        else:
            return 'unknown'
