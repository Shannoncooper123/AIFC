"""TP/SL管理与触发"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from modules.agent.trade_simulator.models import Account, Position
from modules.agent.trade_simulator.storage import ConfigFacade
from modules.agent.utils.trace_utils import get_current_workflow_run_id
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.trade_engine.tpsl_manager')


class TPSLManager:
    """TP/SL管理服务：负责更新TP/SL和K线触发检查"""
    def __init__(self, config: Dict, account: Account, positions: Dict[str, Position],
                 risk_service, state_manager, position_manager, lock: threading.RLock):
        self.cfg = ConfigFacade(config)
        self.account = account
        self.positions = positions
        self.risk = risk_service
        self.state = state_manager
        self.position_mgr = position_manager
        self.lock = lock

    def update_tp_sl(self, symbol: str,
                     tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        """更新持仓的TP/SL（通过交易对查找）
        
        Args:
            symbol: 交易对
            tp_price: 新止盈价（可选，但推荐与 sl_price 同时更新）
            sl_price: 新止损价（可选，但推荐与 tp_price 同时更新）
        
        Note:
            虽然参数设计为可选（允许只更新一个），但从交易安全角度：
            - 推荐同时更新 tp_price 和 sl_price
            - 工具层（update_tp_sl_tool.py）强制要求两个都必填
            - 避免出现只有止盈无止损、或只有止损无止盈的情况
            
            run_id 通过 trace_context 自动获取
        """
        run_id = get_current_workflow_run_id()
        with self.lock:
            logger.info(f"update_tp_sl: symbol={symbol}, tp_price={tp_price}, sl_price={sl_price}")

            # 通过交易对查找持仓
            pos = self.positions.get(symbol)

            if not pos or pos.status != 'open':
                logger.error(f"update_tp_sl: 未找到 {symbol} 的可更新持仓")
                return {"error": f"TOOL_INPUT_ERROR: 未找到 {symbol} 的可更新持仓"}

            # 记录旧值
            old_tp = pos.tp_price
            old_sl = pos.sl_price

            # 允许单独更新（灵活性），但推荐同时更新（安全性）
            if tp_price is not None:
                pos.tp_price = tp_price
            if sl_price is not None:
                pos.sl_price = sl_price

            pos.operation_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "operation": "update_tp_sl",
                "run_id": run_id,
                "details": {
                    "old_tp": old_tp,
                    "new_tp": pos.tp_price,
                    "old_sl": old_sl,
                    "new_sl": pos.sl_price
                }
            })

            logger.info(f"update_tp_sl: symbol={pos.symbol}, new_tp={pos.tp_price}, new_sl={pos.sl_price}")

            return self.state.pos_to_dict(pos)

    def on_kline(self, symbol: str, kline_data: Dict[str, Any]) -> None:
        """K线回调：检查TP/SL触发"""
        try:
            with self.lock:
                pos = self.positions.get(symbol)
                if not pos or pos.status != 'open':
                    return

                k = kline_data
                high = float(k.get('h'))
                low = float(k.get('l'))
                close = float(k.get('c'))
                pos.latest_mark_price = close

                # 触发逻辑（止损优先）
                if pos.side == 'long':
                    if pos.sl_price is not None and low <= pos.sl_price:
                        logger.info(f"on_kline: LONG SL触发 symbol={symbol}, low={low:.6f} <= SL={pos.sl_price:.6f}")
                        # 使用 SL 价格作为平仓价格
                        self.position_mgr.close_position(symbol=symbol, close_reason='止损', close_price=pos.sl_price)
                        return
                    if pos.tp_price is not None and high >= pos.tp_price:
                        logger.info(f"on_kline: LONG TP触发 symbol={symbol}, high={high:.6f} >= TP={pos.tp_price:.6f}")
                        # 使用 TP 价格作为平仓价格
                        self.position_mgr.close_position(symbol=symbol, close_reason='止盈', close_price=pos.tp_price)
                        return
                else:
                    if pos.sl_price is not None and high >= pos.sl_price:
                        logger.info(f"on_kline: SHORT SL触发 symbol={symbol}, high={high:.6f} >= SL={pos.sl_price:.6f}")
                        # 使用 SL 价格作为平仓价格
                        self.position_mgr.close_position(symbol=symbol, close_reason='止损', close_price=pos.sl_price)
                        return
                    if pos.tp_price is not None and low <= pos.tp_price:
                        logger.info(f"on_kline: SHORT TP触发 symbol={symbol}, low={low:.6f} <= TP={pos.tp_price:.6f}")
                        # 使用 TP 价格作为平仓价格
                        self.position_mgr.close_position(symbol=symbol, close_reason='止盈', close_price=pos.tp_price)
                        return
        except Exception as e:
            logger.error(f"on_kline错误: {e}")
            # 保守处理，避免回调异常影响主流程

