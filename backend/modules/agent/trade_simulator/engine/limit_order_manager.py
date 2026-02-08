"""限价单管理器：负责限价单的创建、成交检测、持久化"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.agent.trade_simulator.models import PendingOrder
from modules.agent.trade_simulator.storage import ConfigFacade
from modules.agent.trade_simulator.utils.file_utils import WriteQueue
from modules.agent.utils.trace_utils import get_current_workflow_run_id
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.trade_engine.limit_order_manager')


class LimitOrderManager:
    """限价单管理服务"""

    def __init__(self, config: Dict, account, positions: Dict, position_manager, lock: threading.RLock):
        """初始化限价单管理器
        
        Args:
            config: 配置字典
            account: 账户对象
            positions: 持仓字典
            position_manager: 持仓管理器（用于成交后开仓）
            lock: 线程锁
        """
        self.config = config
        self.cfg = ConfigFacade(config)
        self.account = account
        self.positions = positions
        self.position_mgr = position_manager
        self.lock = lock

        self.max_leverage = self.cfg.max_leverage
        self._disable_persistence = config.get('agent', {}).get('disable_persistence', False)

        self.orders: Dict[str, PendingOrder] = {}

        state_path = config.get('agent', {}).get('state_path')
        if state_path:
            self.orders_file = Path(state_path).parent / 'pending_orders.json'
        else:
            self.orders_file = None

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        limit_price: float,
        margin_usdt: float,
        leverage: int,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        order_kind: str = "LIMIT"
    ) -> Dict[str, Any]:
        """创建限价单/条件单
        
        Args:
            symbol: 交易对
            side: 方向（long/short）
            limit_price: 挂单/触发价格
            margin_usdt: 保证金金额
            leverage: 杠杆倍数
            tp_price: 止盈价
            sl_price: 止损价
            order_kind: 订单类型 "LIMIT"(Maker) 或 "CONDITIONAL"(Taker)
            
        Returns:
            订单信息字典或错误字典
            
        Note:
            run_id 通过 trace_context 自动获取
        """
        run_id = get_current_workflow_run_id()
        with self.lock:
            order_type_cn = "条件单" if order_kind == "CONDITIONAL" else "限价单"
            logger.info(
                f"create_limit_order: symbol={symbol}, side={side}, "
                f"limit_price={limit_price}, margin={margin_usdt}, leverage={leverage}, "
                f"order_kind={order_kind} ({order_type_cn})"
            )

            # 参数校验
            if side not in ("long", "short"):
                logger.error("create_limit_order: 参数错误 side")
                return {"error": "TOOL_INPUT_ERROR: side必须为long/short"}

            if limit_price <= 0:
                logger.error("create_limit_order: 参数错误 limit_price")
                return {"error": "TOOL_INPUT_ERROR: limit_price必须>0"}

            if margin_usdt <= 0:
                logger.error("create_limit_order: 参数错误 margin_usdt")
                return {"error": "TOOL_INPUT_ERROR: margin_usdt必须>0"}

            if leverage < 1 or leverage > self.max_leverage:
                logger.error("create_limit_order: 参数错误 leverage")
                return {"error": f"TOOL_INPUT_ERROR: leverage需在1..{self.max_leverage}"}

            # 保证金检查（预留保证金）
            notional = margin_usdt * leverage
            free_balance = self.account.balance - self.account.reserved_margin_sum

            if free_balance < margin_usdt:
                logger.warning(
                    f"create_limit_order: 保证金不足 free={free_balance:.4f} < need={margin_usdt:.4f}"
                )
                return {"error": "TOOL_INPUT_ERROR: 保证金不足"}

            # 预占保证金
            self.account.reserved_margin_sum += margin_usdt

            order_id = f"order_{uuid.uuid4().hex[:12]}"
            order = PendingOrder(
                id=order_id,
                symbol=symbol,
                side=side,
                order_type="limit",
                order_kind=order_kind,
                limit_price=limit_price,
                margin_usdt=margin_usdt,
                leverage=leverage,
                tp_price=tp_price,
                sl_price=sl_price,
                create_time=datetime.now(timezone.utc).isoformat(),
                status="pending",
                create_run_id=run_id,
            )

            self.orders[order_id] = order

            logger.info(
                f"create_limit_order: {order_type_cn}已创建 id={order_id}, "
                f"symbol={symbol}, side={side}, limit_price={limit_price}, kind={order_kind}"
            )

            return self._order_to_dict(order)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """取消单个限价单
        
        Args:
            order_id: 订单ID
            
        Returns:
            订单信息字典或错误字典
        """
        with self.lock:
            logger.info(f"cancel_order: order_id={order_id}")

            if order_id not in self.orders:
                logger.error(f"cancel_order: 未找到订单 {order_id}")
                return {"error": f"TOOL_INPUT_ERROR: 未找到订单 {order_id}"}

            order = self.orders[order_id]

            if order.status != "pending":
                logger.error(f"cancel_order: 订单状态不是pending ({order.status})")
                return {"error": "TOOL_INPUT_ERROR: 订单状态不是pending，无法取消"}

            self.account.reserved_margin_sum = max(0.0, self.account.reserved_margin_sum - order.margin_usdt)
            # 标记为取消
            order.status = "cancelled"

            logger.info(f"cancel_order: 订单已取消 id={order_id}, symbol={order.symbol}")

            return self._order_to_dict(order)

    def cancel_orders_by_symbol(self, symbol: str) -> Dict[str, Any]:
        """取消指定交易对的所有待成交限价单
        
        Args:
            symbol: 交易对
            
        Returns:
            包含取消订单数量和详情的字典或错误字典
        """
        with self.lock:
            logger.info(f"cancel_orders_by_symbol: symbol={symbol}")

            # 查找该symbol的所有pending订单
            pending_orders = [
                order for order in self.orders.values()
                if order.symbol == symbol and order.status == "pending"
            ]

            if not pending_orders:
                logger.warning(f"cancel_orders_by_symbol: 未找到 {symbol} 的待成交订单")
                return {
                    "symbol": symbol,
                    "cancelled_count": 0,
                    "cancelled_orders": [],
                    "message": f"未找到 {symbol} 的待成交订单"
                }

            # 取消所有找到的订单
            cancelled_orders = []
            for order in pending_orders:
                self.account.reserved_margin_sum = max(0.0, self.account.reserved_margin_sum - order.margin_usdt)
                order.status = "cancelled"
                cancelled_orders.append(self._order_to_dict(order))

            logger.info(
                f"cancel_orders_by_symbol: 已取消 {symbol} 的 {len(cancelled_orders)} 个挂单"
            )

            return {
                "symbol": symbol,
                "cancelled_count": len(cancelled_orders),
                "cancelled_orders": cancelled_orders
            }

    def on_kline(self, symbol: str, kline_data: Dict[str, Any]) -> None:
        """K线回调：检查限价单/条件单是否触发成交
        
        限价单 (LIMIT/Maker) 成交逻辑 - 等待价格回撤：
        - 做多: 当 low <= limit_price 时触发
          - 如果 open <= limit_price，以 open 成交
          - 否则以 limit_price 成交
        - 做空: 当 high >= limit_price 时触发
          - 如果 open >= limit_price，以 open 成交
          - 否则以 limit_price 成交
        
        条件单 (CONDITIONAL/Taker) 成交逻辑 - 等待价格突破：
        - 做多: 当 high >= trigger_price 时触发
          - 如果 open >= trigger_price，以 open 成交
          - 否则以 trigger_price 成交
        - 做空: 当 low <= trigger_price 时触发
          - 如果 open <= trigger_price，以 open 成交
          - 否则以 trigger_price 成交
        
        Args:
            symbol: 交易对
            kline_data: K线数据字典
        """
        try:
            with self.lock:
                pending_orders = [
                    order for order in self.orders.values()
                    if order.symbol == symbol and order.status == "pending"
                ]

                if not pending_orders:
                    return

                open_price = float(kline_data.get('o', 0))
                high = float(kline_data.get('h', 0))
                low = float(kline_data.get('l', 0))
                close = float(kline_data.get('c', 0))

                for order in pending_orders:
                    filled = False
                    filled_price = None
                    order_kind = getattr(order, 'order_kind', 'LIMIT')
                    is_conditional = order_kind == 'CONDITIONAL'
                    kind_label = "条件单" if is_conditional else "限价单"

                    if order.side == "long":
                        if is_conditional:
                            if high >= order.limit_price:
                                filled = True
                                if open_price > 0 and open_price >= order.limit_price:
                                    filled_price = open_price
                                    logger.info(
                                        f"on_kline: LONG{kind_label}立即突破 symbol={symbol}, "
                                        f"open={open_price:.6f} >= trigger={order.limit_price:.6f}, "
                                        f"成交价={filled_price:.6f}"
                                    )
                                else:
                                    filled_price = order.limit_price
                                    logger.info(
                                        f"on_kline: LONG{kind_label}突破触发 symbol={symbol}, "
                                        f"high={high:.6f} >= trigger={order.limit_price:.6f}, "
                                        f"成交价={filled_price:.6f}"
                                    )
                        else:
                            if low <= order.limit_price:
                                filled = True
                                if open_price > 0 and open_price <= order.limit_price:
                                    filled_price = open_price
                                    logger.info(
                                        f"on_kline: LONG{kind_label}立即成交 symbol={symbol}, "
                                        f"open={open_price:.6f} <= limit={order.limit_price:.6f}, "
                                        f"成交价={filled_price:.6f}"
                                    )
                                else:
                                    filled_price = order.limit_price
                                    logger.info(
                                        f"on_kline: LONG{kind_label}触发成交 symbol={symbol}, "
                                        f"low={low:.6f} <= limit={order.limit_price:.6f}, "
                                        f"成交价={filled_price:.6f}"
                                    )
                    else:  # short
                        if is_conditional:
                            if low <= order.limit_price:
                                filled = True
                                if open_price > 0 and open_price <= order.limit_price:
                                    filled_price = open_price
                                    logger.info(
                                        f"on_kline: SHORT{kind_label}立即突破 symbol={symbol}, "
                                        f"open={open_price:.6f} <= trigger={order.limit_price:.6f}, "
                                        f"成交价={filled_price:.6f}"
                                    )
                                else:
                                    filled_price = order.limit_price
                                    logger.info(
                                        f"on_kline: SHORT{kind_label}突破触发 symbol={symbol}, "
                                        f"low={low:.6f} <= trigger={order.limit_price:.6f}, "
                                        f"成交价={filled_price:.6f}"
                                    )
                        else:
                            if high >= order.limit_price:
                                filled = True
                                if open_price > 0 and open_price >= order.limit_price:
                                    filled_price = open_price
                                    logger.info(
                                        f"on_kline: SHORT{kind_label}立即成交 symbol={symbol}, "
                                        f"open={open_price:.6f} >= limit={order.limit_price:.6f}, "
                                        f"成交价={filled_price:.6f}"
                                    )
                                else:
                                    filled_price = order.limit_price
                                    logger.info(
                                        f"on_kline: SHORT{kind_label}触发成交 symbol={symbol}, "
                                        f"high={high:.6f} >= limit={order.limit_price:.6f}, "
                                        f"成交价={filled_price:.6f}"
                                    )

                    if filled:
                        self._fill_order(order, filled_price)

        except Exception as e:
            logger.error(f"on_kline 订单检查错误: {e}", exc_info=True)

    def _fill_order(self, order: PendingOrder, filled_price: float) -> None:
        """执行限价单成交
        
        Args:
            order: 待成交订单
            filled_price: 成交价格
        """
        try:
            logger.info(
                f"_fill_order: 开始执行限价单成交 order_id={order.id}, "
                f"symbol={order.symbol}, filled_price={filled_price}"
            )

            # 计算名义价值
            notional = order.margin_usdt * order.leverage

            # 调用position_manager开仓（使用成交价格）
            # 注意：我们需要特殊处理，直接传入成交价格而非使用市价
            result = self.position_mgr.open_position(
                symbol=order.symbol,
                side=order.side,
                quote_notional_usdt=notional,
                leverage=order.leverage,
                tp_price=order.tp_price,
                sl_price=order.sl_price,
                entry_price=filled_price,
                pre_reserved_margin=True,
            )

            if 'error' in result:
                logger.error(f"_fill_order: 开仓失败 {result['error']}")
                order.status = "failed"
                self.account.reserved_margin_sum = max(0.0, self.account.reserved_margin_sum - order.margin_usdt)
                return

            # 更新订单状态
            order.status = "filled"
            order.filled_time = datetime.now(timezone.utc).isoformat()
            order.filled_price = filled_price
            order.position_id = result.get('id')

            logger.info(
                f"_fill_order: 限价单成交完成 order_id={order.id}, "
                f"position_id={order.position_id}"
            )

        except Exception as e:
            logger.error(f"_fill_order 执行失败: {e}", exc_info=True)

    def get_pending_orders_summary(self) -> List[Dict[str, Any]]:
        """获取所有待成交订单摘要
        
        Returns:
            订单摘要列表
        """
        with self.lock:
            pending_list = []
            for order in self.orders.values():
                if order.status == "pending":
                    pending_list.append(self._order_to_dict(order))
            return pending_list

    def _order_to_dict(self, order: PendingOrder) -> Dict[str, Any]:
        """将订单对象转换为字典
        
        Args:
            order: 订单对象
            
        Returns:
            订单字典
        """
        return {
            'id': order.id,
            'symbol': order.symbol,
            'side': order.side,
            'order_type': order.order_type,
            'order_kind': getattr(order, 'order_kind', 'LIMIT'),
            'limit_price': round(order.limit_price, 8),
            'margin_usdt': round(order.margin_usdt, 2),
            'leverage': order.leverage,
            'tp_price': round(order.tp_price, 8) if order.tp_price else None,
            'sl_price': round(order.sl_price, 8) if order.sl_price else None,
            'create_time': order.create_time,
            'status': order.status,
            'filled_time': order.filled_time,
            'filled_price': round(order.filled_price, 8) if order.filled_price else None,
            'position_id': order.position_id,
            'create_run_id': order.create_run_id,
            'fill_run_id': order.fill_run_id,
        }

    def persist(self) -> None:
        """持久化所有待成交的限价单到文件"""
        if self._disable_persistence or not self.orders_file:
            return
        try:
            from modules.agent.trade_simulator.utils.file_utils import TaskType

            pending_orders = [self._order_to_dict(o) for o in self.orders.values() if o.status == 'pending']

            write_queue = WriteQueue.get_instance()
            write_queue.enqueue(TaskType.STATE, str(self.orders_file), pending_orders)

            logger.debug(f"已提交 {len(pending_orders)} 个待成交订单到写入队列: {self.orders_file}")
        except Exception as e:
            logger.error(f"持久化待成交订单失败: {e}", exc_info=True)

    def restore(self) -> None:
        """从文件恢复待成交订单"""
        if self._disable_persistence or not self.orders_file:
            return
        try:
            if not self.orders_file.exists():
                logger.warning(f"restore: 未找到挂单文件 {self.orders_file}，跳过恢复")
                return

            with open(self.orders_file, 'r', encoding='utf-8') as f:
                orders_data = json.load(f)

            if isinstance(orders_data, list):
                restored_orders = [PendingOrder(**data) for data in orders_data]
                for order in restored_orders:
                    if order.status == 'pending':
                        self.orders[order.id] = order
                logger.info(f"从 {self.orders_file} 恢复了 {len(restored_orders)} 个待成交订单")
            else:
                logger.error(f"restore: 挂单文件格式错误，期望是列表: {self.orders_file}")

        except json.JSONDecodeError:
            logger.error(f"restore: 解析挂单文件失败 {self.orders_file}")
        except Exception as e:
            logger.error(f"restore: 从文件恢复挂单失败: {e}", exc_info=True)
