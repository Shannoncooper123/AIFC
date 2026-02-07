"""反向交易引擎（策略层）

当 Agent 下限价单时，自动创建反向订单进行对冲交易。
使用固定保证金和杠杆，与 Agent 的参数无关。

架构说明（v5 - 统一基础设施）：
- 使用 live_engine 的 OrderManager 进行下单
- 使用 live_engine 的 RecordService 管理开仓记录
- 本模块只负责策略逻辑：信号解析、方向反转、订单类型选择

职责：
- 监听 Agent 限价单创建事件
- 计算反向订单参数（方向反转、TP/SL 互换）
- 智能选择订单类型（限价单/条件单）以优化手续费
- 监听成交事件并处理后续逻辑
"""

import threading
from typing import Dict, Any, Optional, List, Set, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger
from modules.monitor.clients.binance_ws import BinanceMarkPriceWSClient

from .config import ConfigManager
from .workflow_runner import ReverseWorkflowManager
from modules.agent.shared import (
    ExchangeInfoCache, 
    JsonStateManager,
    PendingOrder,
    AlgoOrderStatus,
    OrderKind,
)

if TYPE_CHECKING:
    from modules.agent.live_engine.engine import BinanceLiveEngine

logger = get_logger('reverse_engine')

PENDING_ORDERS_STATE_FILE = 'modules/data/reverse_pending_orders.json'


class ReverseEngine:
    """反向交易引擎（策略层）
    
    职责：
    - 解析 Agent 限价单信号
    - 计算反向订单参数（方向反转、TP/SL 互换）
    - 调用 live_engine 执行下单
    - 监听成交事件并处理后续逻辑
    
    架构：
    - 强制依赖 live_engine，使用其 OrderManager 和 RecordService
    - 不再维护独立的订单/记录管理
    """
    
    def __init__(self, live_engine: 'BinanceLiveEngine', config: Dict):
        """初始化
        
        Args:
            live_engine: 实盘引擎实例（必需）
            config: 配置字典
            
        Raises:
            ValueError: 如果 live_engine 为 None
        """
        if live_engine is None:
            raise ValueError("ReverseEngine 必须传入 live_engine 参数，不支持独立运行")
        
        self.config = config
        self._lock = threading.RLock()
        self._running = False
        
        self.live_engine = live_engine
        self.config_manager = ConfigManager()
        
        self.workflow_manager = ReverseWorkflowManager()
        
        self._pending_state = JsonStateManager(PENDING_ORDERS_STATE_FILE)
        self.pending_algo_orders: Dict[str, PendingOrder] = {}
        self.pending_limit_orders: Dict[int, PendingOrder] = {}
        self._load_pending_orders()
        
        self.mark_price_ws: Optional[BinanceMarkPriceWSClient] = None
        self._watched_symbols: Set[str] = set()
        
        logger.info("[反向] 反向交易引擎已初始化（v5 - 统一基础设施）")
    
    @property
    def order_manager(self):
        """获取订单管理器（来自 live_engine）"""
        return self.live_engine.order_manager
    
    @property
    def record_service(self):
        """获取记录服务（来自 live_engine）"""
        return self.live_engine.record_service
    
    @property
    def rest_client(self):
        """获取 REST 客户端（来自 live_engine）"""
        return self.live_engine.rest_client
    
    def _load_pending_orders(self):
        """加载待触发订单"""
        data = self._pending_state.load()
        
        for algo_id, order_data in data.get('pending_algo_orders', {}).items():
            self.pending_algo_orders[algo_id] = PendingOrder.from_dict(order_data)
        
        for order_id_str, order_data in data.get('pending_limit_orders', {}).items():
            order_id = int(order_id_str)
            self.pending_limit_orders[order_id] = PendingOrder.from_dict(order_data)
        
        if self.pending_algo_orders or self.pending_limit_orders:
            logger.info(f"[反向] 已加载 {len(self.pending_algo_orders)} 个条件单, "
                       f"{len(self.pending_limit_orders)} 个限价单")
    
    def _save_pending_orders(self):
        """保存待触发订单"""
        from datetime import datetime
        data = {
            'pending_algo_orders': {
                algo_id: order.to_dict()
                for algo_id, order in self.pending_algo_orders.items()
            },
            'pending_limit_orders': {
                str(order_id): order.to_dict()
                for order_id, order in self.pending_limit_orders.items()
            },
            'updated_at': datetime.now().isoformat()
        }
        self._pending_state.save(data)
    
    def is_enabled(self) -> bool:
        """是否启用"""
        return self.config_manager.enabled
    
    def start(self):
        """启动引擎"""
        with self._lock:
            if self._running:
                logger.warning("[反向] 引擎已在运行")
                return
            
            if not self.config_manager.enabled:
                logger.info("[反向] 引擎未启用，跳过启动")
                return
            
            self._running = True
            logger.info("=" * 60)
            logger.info("[反向] 反向交易引擎启动 (v5 - 统一基础设施)")
            logger.info(f"[反向] 配置: margin={self.config_manager.fixed_margin_usdt}U, "
                       f"leverage={self.config_manager.fixed_leverage}x")
            logger.info("[反向] 策略: 开仓优先限价单(Maker) | 止盈限价单 | 止损条件单")
            logger.info("=" * 60)
            
            try:
                if self.live_engine and hasattr(self.live_engine, 'event_dispatcher'):
                    self.live_engine.event_dispatcher.register_listener(self._handle_event)
                    logger.info("[反向] 已注册到 live_engine 的事件分发器")
                
                self._start_mark_price_ws()
                
                open_records = self.record_service.get_open_records(source='reverse')
                logger.info("[反向] 反向交易引擎启动完成")
                logger.info(f"[反向] 待触发条件单: {len(self.pending_algo_orders)}")
                logger.info(f"[反向] 待成交限价单: {len(self.pending_limit_orders)}")
                logger.info(f"[反向] 当前开仓记录: {len(open_records)}")
                
            except Exception as e:
                logger.error(f"[反向] 启动引擎失败: {e}", exc_info=True)
                self._running = False
                raise
    
    def stop(self):
        """停止引擎"""
        with self._lock:
            if not self._running:
                return
            
            logger.info("[反向] 正在停止反向交易引擎...")
            self._running = False
            
            try:
                self.workflow_manager.stop_all()
                self._stop_mark_price_ws()
                
                if self.live_engine and hasattr(self.live_engine, 'event_dispatcher'):
                    self.live_engine.event_dispatcher.unregister_listener(self._handle_event)
                    logger.info("[反向] 已从 live_engine 事件分发器取消注册")
                
                logger.info("[反向] 反向交易引擎已停止")
                
            except Exception as e:
                logger.error(f"[反向] 停止引擎时出错: {e}")
    
    def on_agent_limit_order(self, symbol: str, side: str, limit_price: float,
                              tp_price: float, sl_price: float,
                              agent_order_id: Optional[str] = None):
        """Agent 下限价单时触发
        
        智能创建反向订单：
        - 方向反转：Agent BUY -> 我们 SELL
        - TP/SL 互换：Agent 的 TP 变成我们的 SL，Agent 的 SL 变成我们的 TP
        - 使用固定保证金和杠杆
        - 智能选择订单类型（限价单/条件单）以优化手续费
        """
        if not self.config_manager.enabled:
            logger.debug(f"[反向] 引擎未启用，跳过处理 {symbol}")
            return None
        
        max_positions = self.config_manager.max_positions
        open_records = self.record_service.get_open_records(source='reverse')
        current_count = len(open_records) + len(self.pending_algo_orders) + len(self.pending_limit_orders)
        
        if current_count >= max_positions:
            logger.warning(f"[反向] 达到最大持仓/挂单数限制 ({max_positions})，跳过 {symbol}")
            return None
        
        reverse_side = 'SELL' if side == 'long' else 'BUY'
        reverse_tp = sl_price
        reverse_sl = tp_price
        
        logger.info(f"[反向] 处理 Agent 限价单: {symbol} {side} @ {limit_price}")
        logger.info(f"[反向] 创建反向订单: {reverse_side} price={limit_price} TP={reverse_tp} SL={reverse_sl}")
        
        return self._create_entry_order(
            symbol=symbol,
            side=reverse_side,
            trigger_price=limit_price,
            tp_price=reverse_tp,
            sl_price=reverse_sl,
            agent_order_id=agent_order_id,
            agent_side=side
        )
    
    def _create_entry_order(self, symbol: str, side: str, trigger_price: float,
                            tp_price: float, sl_price: float,
                            agent_order_id: Optional[str] = None,
                            agent_side: Optional[str] = None) -> Optional[PendingOrder]:
        """智能创建开仓订单（选择限价单或条件单）"""
        fixed_margin = self.config_manager.fixed_margin_usdt
        fixed_leverage = self.config_manager.fixed_leverage
        
        self.order_manager.ensure_dual_position_mode()
        self.order_manager.ensure_leverage(symbol, fixed_leverage)
        
        notional = fixed_margin * fixed_leverage
        quantity = notional / trigger_price
        quantity = ExchangeInfoCache.format_quantity(symbol, quantity)
        
        current_price = self.order_manager.get_mark_price(symbol)
        if not current_price:
            current_price = trigger_price
        
        use_limit_order = False
        if side.upper() == 'BUY' and current_price > trigger_price:
            use_limit_order = True
            logger.info(f"[反向] 当前价格 {current_price} > 触发价 {trigger_price}，使用限价单 (Maker)")
        elif side.upper() == 'SELL' and current_price < trigger_price:
            use_limit_order = True
            logger.info(f"[反向] 当前价格 {current_price} < 触发价 {trigger_price}，使用限价单 (Maker)")
        
        if use_limit_order:
            return self._create_limit_order(
                symbol, side, trigger_price, quantity, fixed_leverage, fixed_margin,
                tp_price, sl_price, agent_order_id, agent_side
            )
        else:
            logger.info(f"[反向] 使用条件单 (Taker)")
            return self._create_algo_order(
                symbol, side, trigger_price, quantity, fixed_leverage, fixed_margin,
                tp_price, sl_price, agent_order_id, agent_side
            )
    
    def _create_limit_order(self, symbol: str, side: str, price: float, quantity: float,
                            leverage: int, margin: float, tp_price: float, sl_price: float,
                            agent_order_id: Optional[str], agent_side: Optional[str]) -> Optional[PendingOrder]:
        """创建限价单"""
        from datetime import datetime
        
        position_side = 'LONG' if side.upper() == 'BUY' else 'SHORT'
        
        result = self.order_manager.place_limit_order(
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            position_side=position_side
        )
        
        if not result.get('success'):
            logger.error(f"[反向] 限价单下单失败: {result.get('error')}")
            return None
        
        order_id = result.get('order_id')
        
        order = PendingOrder(
            id=f"LIMIT_{order_id}",
            symbol=symbol,
            side=side.lower(),
            trigger_price=price,
            quantity=quantity,
            status=AlgoOrderStatus.NEW,
            order_kind=OrderKind.LIMIT_ORDER,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage,
            margin_usdt=margin,
            order_id=order_id,
            source='reverse',
            agent_order_id=agent_order_id,
            agent_limit_price=price,
            agent_side=agent_side,
            created_at=datetime.now().isoformat()
        )
        
        self.pending_limit_orders[order_id] = order
        self._save_pending_orders()
        
        logger.info(f"[反向] ✅ 限价单创建成功: orderId={order_id}")
        return order
    
    def _create_algo_order(self, symbol: str, side: str, trigger_price: float, quantity: float,
                           leverage: int, margin: float, tp_price: float, sl_price: float,
                           agent_order_id: Optional[str], agent_side: Optional[str]) -> Optional[PendingOrder]:
        """创建条件单"""
        from datetime import datetime
        
        position_side = 'LONG' if side.upper() == 'BUY' else 'SHORT'
        
        current_price = self.order_manager.get_mark_price(symbol) or trigger_price
        if side.upper() == 'BUY':
            order_type = 'STOP_MARKET' if trigger_price > current_price else 'TAKE_PROFIT_MARKET'
        else:
            order_type = 'STOP_MARKET' if trigger_price < current_price else 'TAKE_PROFIT_MARKET'
        
        result = self.order_manager.place_algo_order(
            symbol=symbol,
            side=side,
            trigger_price=trigger_price,
            quantity=quantity,
            order_type=order_type,
            position_side=position_side,
            expiration_days=self.config_manager.expiration_days
        )
        
        if not result.get('success'):
            logger.error(f"[反向] 条件单下单失败: {result.get('error')}")
            return None
        
        algo_id = result.get('algo_id')
        
        order = PendingOrder(
            id=algo_id,
            symbol=symbol,
            side=side.lower(),
            trigger_price=trigger_price,
            quantity=quantity,
            status=AlgoOrderStatus.NEW,
            order_kind=OrderKind.CONDITIONAL_ORDER,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage,
            margin_usdt=margin,
            algo_id=algo_id,
            source='reverse',
            agent_order_id=agent_order_id,
            agent_limit_price=trigger_price,
            agent_side=agent_side,
            created_at=datetime.now().isoformat()
        )
        
        self.pending_algo_orders[algo_id] = order
        self._save_pending_orders()
        
        logger.info(f"[反向] ✅ 条件单创建成功: algoId={algo_id}")
        return order
    
    def _handle_event(self, event: Dict[str, Any]):
        """处理 WebSocket 事件"""
        event_type = event.get('e')
        
        if event_type == 'ORDER_TRADE_UPDATE':
            self._handle_order_update(event.get('o', {}))
        elif event_type == 'ALGO_UPDATE':
            self._handle_algo_update(event)
    
    def _handle_order_update(self, order_data: Dict):
        """处理普通订单更新（限价单成交）"""
        order_id = order_data.get('i')
        status = order_data.get('X')
        symbol = order_data.get('s')
        
        if status == 'FILLED' and order_id in self.pending_limit_orders:
            order = self.pending_limit_orders[order_id]
            filled_price = float(order_data.get('ap', order.trigger_price))
            
            logger.info(f"[反向] 📦 限价单成交: {symbol} orderId={order_id} price={filled_price}")
            
            self.record_service.create_record(
                symbol=order.symbol,
                side=order.side,
                qty=order.quantity,
                entry_price=filled_price,
                leverage=order.leverage,
                tp_price=order.tp_price,
                sl_price=order.sl_price,
                source='reverse',
                entry_order_id=order_id,
                agent_order_id=order.agent_order_id,
                auto_place_tpsl=True
            )
            
            del self.pending_limit_orders[order_id]
            self._save_pending_orders()
    
    def _handle_algo_update(self, event: Dict):
        """处理策略单更新（条件单触发）"""
        algo_id = str(event.get('ai', ''))
        status = event.get('as', '')
        symbol = event.get('s', '')
        
        if status == 'FILLED' and algo_id in self.pending_algo_orders:
            order = self.pending_algo_orders[algo_id]
            filled_price = float(event.get('ap', order.trigger_price))
            triggered_order_id = event.get('oi')
            
            logger.info(f"[反向] 📦 条件单触发: {symbol} algoId={algo_id} price={filled_price}")
            
            self.record_service.create_record(
                symbol=order.symbol,
                side=order.side,
                qty=order.quantity,
                entry_price=filled_price,
                leverage=order.leverage,
                tp_price=order.tp_price,
                sl_price=order.sl_price,
                source='reverse',
                entry_algo_id=algo_id,
                agent_order_id=order.agent_order_id,
                auto_place_tpsl=True
            )
            
            del self.pending_algo_orders[algo_id]
            self._save_pending_orders()
        
        elif status in ('FILLED', 'USER_CANCELLED'):
            record = self.record_service.find_record_by_tp_algo_id(algo_id)
            if record:
                close_price = float(event.get('ap', record.tp_price or record.entry_price))
                self.record_service.cancel_remaining_tpsl(record, 'TP')
                self.record_service.close_record(record.id, close_price, 'TP_CLOSED')
                return
            
            record = self.record_service.find_record_by_sl_algo_id(algo_id)
            if record:
                close_price = float(event.get('ap', record.sl_price or record.entry_price))
                self.record_service.cancel_remaining_tpsl(record, 'SL')
                self.record_service.close_record(record.id, close_price, 'SL_CLOSED')
    
    def _start_mark_price_ws(self):
        """启动标记价格 WebSocket"""
        try:
            self._update_watched_symbols()
            
            if not self._watched_symbols:
                logger.info("[反向] 无需监控的交易对，跳过 MarkPriceWS 启动")
                return
            
            self.mark_price_ws = BinanceMarkPriceWSClient(
                on_price_update=self._on_mark_price_update,
                symbols_filter=self._watched_symbols.copy()
            )
            self.mark_price_ws.start()
            logger.info(f"[反向] MarkPriceWS 已启动，监控 {len(self._watched_symbols)} 个交易对")
            
        except Exception as e:
            logger.error(f"[反向] 启动 MarkPriceWS 失败: {e}")
    
    def _stop_mark_price_ws(self):
        """停止标记价格 WebSocket"""
        if self.mark_price_ws:
            try:
                self.mark_price_ws.stop()
                self.mark_price_ws = None
                logger.info("[反向] MarkPriceWS 已停止")
            except Exception as e:
                logger.error(f"[反向] 停止 MarkPriceWS 失败: {e}")
    
    def _update_watched_symbols(self):
        """更新需要监控的交易对列表"""
        new_symbols = set()
        
        for record in self.record_service.get_open_records(source='reverse'):
            new_symbols.add(record.symbol)
        
        for order in self.pending_algo_orders.values():
            new_symbols.add(order.symbol)
        
        for order in self.pending_limit_orders.values():
            new_symbols.add(order.symbol)
        
        if new_symbols != self._watched_symbols:
            self._watched_symbols = new_symbols
            if self.mark_price_ws:
                self.mark_price_ws.set_symbols_filter(new_symbols)
                logger.info(f"[反向] 更新监控交易对: {len(new_symbols)} 个")
    
    def _on_mark_price_update(self, prices: Dict[str, float]):
        """处理标记价格更新"""
        try:
            for symbol, mark_price in prices.items():
                if symbol in self._watched_symbols:
                    self.record_service.update_mark_price(symbol, mark_price)
        except Exception as e:
            logger.error(f"[反向] 处理标记价格更新失败: {e}")
    
    def start_symbol_workflow(self, symbol: str, interval: str = "15m") -> bool:
        """启动指定币种的 workflow 分析"""
        if not self.config_manager.enabled:
            logger.info(f"[反向] 自动启用反向交易引擎以启动 {symbol} workflow")
            self.config_manager.update(enabled=True)
        
        if not self._running:
            logger.info(f"[反向] 自动启动反向交易引擎")
            self.start()
        
        return self.workflow_manager.start_symbol(symbol, interval)
    
    def stop_symbol_workflow(self, symbol: str) -> bool:
        """停止指定币种的 workflow 分析"""
        return self.workflow_manager.stop_symbol(symbol)
    
    def get_running_workflows(self) -> List[str]:
        """获取正在运行 workflow 的币种列表"""
        return self.workflow_manager.get_running_symbols()
    
    def get_workflow_status(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取 workflow 运行状态"""
        return self.workflow_manager.get_status(symbol)
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return self.config_manager.get_dict()
    
    def update_config(self, **kwargs) -> Dict[str, Any]:
        """更新配置"""
        config = self.config_manager.update(**kwargs)
        return config.to_dict()
    
    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """获取开仓记录汇总"""
        return self.record_service.get_summary(source='reverse')
    
    def get_pending_orders_summary(self) -> Dict[str, Any]:
        """获取待触发订单汇总"""
        return {
            'total_conditional': len(self.pending_algo_orders),
            'total_limit': len(self.pending_limit_orders),
            'conditional_orders': [o.to_dict() for o in self.pending_algo_orders.values()],
            'limit_orders': [o.to_dict() for o in self.pending_limit_orders.values()]
        }
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取历史记录"""
        records = [
            r for r in self.record_service.records.values()
            if r.source == 'reverse' and r.status.value != 'OPEN'
        ]
        records.sort(key=lambda x: x.close_time or '', reverse=True)
        
        result = []
        for record in records[:limit]:
            pnl_pct = (record.realized_pnl / record.margin_usdt * 100) if record.margin_usdt > 0 else 0
            result.append({
                'id': record.id,
                'symbol': record.symbol,
                'side': record.side.upper(),
                'qty': record.qty,
                'entry_price': record.entry_price,
                'exit_price': record.close_price,
                'leverage': record.leverage,
                'margin_usdt': round(record.margin_usdt, 2),
                'realized_pnl': round(record.realized_pnl or 0, 4),
                'pnl_percent': round(pnl_pct, 2),
                'open_time': record.open_time,
                'close_time': record.close_time,
                'close_reason': record.close_reason
            })
        return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.record_service.get_statistics(source='reverse')
    
    def cancel_pending_order(self, algo_id: str) -> bool:
        """撤销待触发条件单"""
        if algo_id in self.pending_algo_orders:
            order = self.pending_algo_orders[algo_id]
            if self.order_manager.cancel_algo_order(order.symbol, algo_id):
                del self.pending_algo_orders[algo_id]
                self._save_pending_orders()
                return True
        return False
    
    def cancel_limit_order(self, order_id: int) -> bool:
        """撤销待成交限价单"""
        if order_id in self.pending_limit_orders:
            order = self.pending_limit_orders[order_id]
            if self.order_manager.cancel_order(order.symbol, order_id):
                del self.pending_limit_orders[order_id]
                self._save_pending_orders()
                return True
        return False
    
    def close_record(self, record_id: str) -> bool:
        """手动关闭指定开仓记录"""
        record = self.record_service.get_record(record_id)
        if not record or record.source != 'reverse':
            return False
        
        current_price = self.order_manager.get_mark_price(record.symbol) or record.entry_price
        
        result = self.order_manager.place_market_order(
            symbol=record.symbol,
            side='SELL' if record.side.upper() in ('LONG', 'BUY') else 'BUY',
            quantity=record.qty,
            position_side='LONG' if record.side.upper() in ('LONG', 'BUY') else 'SHORT',
            reduce_only=True
        )
        
        if result.get('success'):
            self.record_service.cancel_remaining_tpsl(record, 'TP')
            self.record_service.cancel_remaining_tpsl(record, 'SL')
            self.record_service.close_record(record_id, current_price, 'MANUAL_CLOSED')
            return True
        
        return False
    
    def get_summary(self) -> Dict[str, Any]:
        """获取引擎汇总信息"""
        open_records = self.record_service.get_open_records(source='reverse')
        return {
            'enabled': self.config_manager.enabled,
            'config': self.config_manager.get_dict(),
            'pending_orders_count': len(self.pending_algo_orders) + len(self.pending_limit_orders),
            'positions_count': len(open_records),
            'statistics': self.get_statistics()
        }
