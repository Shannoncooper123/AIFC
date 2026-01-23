"""限价单管理器：负责限价单的创建、成交检测、持久化"""
from __future__ import annotations
import uuid
import threading
import json
from typing import Dict, Optional, List, Any
from pathlib import Path
from datetime import datetime, timezone

from modules.agent.trade_simulator.models import PendingOrder
from modules.agent.trade_simulator.utils.file_utils import WriteQueue
from modules.agent.trade_simulator.storage import ConfigFacade
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
        
        # 限价单字典：order_id -> PendingOrder
        self.orders: Dict[str, PendingOrder] = {}
        
        # 持久化文件路径
        state_path = Path(config['agent']['state_path'])
        self.orders_file = state_path.parent / 'pending_orders.json'
        
        logger.info(f"LimitOrderManager 初始化，持久化文件: {self.orders_file}")
    
    def create_limit_order(
        self,
        symbol: str,
        side: str,
        limit_price: float,
        margin_usdt: float,
        leverage: int,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """创建限价单
        
        Args:
            symbol: 交易对
            side: 方向（long/short）
            limit_price: 挂单价格
            margin_usdt: 保证金金额
            leverage: 杠杆倍数
            tp_price: 止盈价
            sl_price: 止损价
            
        Returns:
            订单信息字典或错误字典
        """
        with self.lock:
            logger.info(
                f"create_limit_order: symbol={symbol}, side={side}, "
                f"limit_price={limit_price}, margin={margin_usdt}, leverage={leverage}"
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
            
            # 创建限价单
            order_id = f"order_{uuid.uuid4().hex[:12]}"
            order = PendingOrder(
                id=order_id,
                symbol=symbol,
                side=side,
                order_type="limit",
                limit_price=limit_price,
                margin_usdt=margin_usdt,
                leverage=leverage,
                tp_price=tp_price,
                sl_price=sl_price,
                create_time=datetime.now(timezone.utc).isoformat(),
                status="pending",
            )
            
            self.orders[order_id] = order
            
            logger.info(
                f"create_limit_order: 限价单已创建 id={order_id}, "
                f"symbol={symbol}, side={side}, limit_price={limit_price}"
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
                return {"error": f"TOOL_INPUT_ERROR: 订单状态不是pending，无法取消"}
            
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
        """K线回调：检查限价单是否触发成交
        
        Args:
            symbol: 交易对
            kline_data: K线数据字典
        """
        try:
            with self.lock:
                # 查找该symbol的所有pending订单
                pending_orders = [
                    order for order in self.orders.values()
                    if order.symbol == symbol and order.status == "pending"
                ]
                
                if not pending_orders:
                    return
                
                # 提取K线价格
                high = float(kline_data.get('h', 0))
                low = float(kline_data.get('l', 0))
                close = float(kline_data.get('c', 0))
                
                # 检查每个订单是否成交
                for order in pending_orders:
                    filled = False
                    filled_price = None
                    
                    if order.side == "long":
                        # 多头限价单：价格下探到挂单价或以下时成交
                        if low <= order.limit_price:
                            filled = True
                            filled_price = order.limit_price
                            logger.info(
                                f"on_kline: LONG限价单触发成交 symbol={symbol}, "
                                f"low={low:.6f} <= limit={order.limit_price:.6f}"
                            )
                    else:  # short
                        # 空头限价单：价格上涨到挂单价或以上时成交
                        if high >= order.limit_price:
                            filled = True
                            filled_price = order.limit_price
                            logger.info(
                                f"on_kline: SHORT限价单触发成交 symbol={symbol}, "
                                f"high={high:.6f} >= limit={order.limit_price:.6f}"
                            )
                    
                    if filled:
                        # 执行成交：调用position_manager开仓
                        self._fill_order(order, filled_price)
        
        except Exception as e:
            logger.error(f"on_kline 限价单检查错误: {e}", exc_info=True)
    
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
        }
    
    def persist(self) -> None:
        """持久化所有待成交的限价单到文件"""
        try:
            from modules.agent.trade_simulator.utils.file_utils import TaskType

            # 只保留 pending 状态的订单
            pending_orders = [self._order_to_dict(o) for o in self.orders.values() if o.status == 'pending']
            
            # 使用写入队列异步写入
            write_queue = WriteQueue.get_instance()
            write_queue.enqueue(TaskType.STATE, str(self.orders_file), pending_orders)
            
            logger.debug(f"已提交 {len(pending_orders)} 个待成交订单到写入队列: {self.orders_file}")
        except Exception as e:
            logger.error(f"持久化待成交订单失败: {e}", exc_info=True)
    
    def restore(self) -> None:
        """从文件恢复待成交订单"""
        try:
            if not self.orders_file.exists():
                logger.warning(f"restore: 未找到挂单文件 {self.orders_file}，跳过恢复")
                return
    
            with open(self.orders_file, 'r', encoding='utf-8') as f:
                orders_data = json.load(f)
            
            # 直接加载列表
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
