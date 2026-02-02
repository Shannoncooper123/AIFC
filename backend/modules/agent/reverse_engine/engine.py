"""反向交易引擎

当 Agent 下限价单时，自动创建反向条件单进行对冲交易。
使用固定保证金和杠杆，与 Agent 的参数无关。

架构说明（v2 - 自主管理 TP/SL）：
- 强制复用 live_engine 的 REST 客户端（不创建独立连接）
- 复用 live_engine 的 WebSocket 连接
- 独立管理：条件单状态、开仓记录、TP/SL 监控
- 通过 Mark Price WebSocket 监控价格，自行判断 TP/SL 触发
- 每个开仓记录有独立的 TP/SL，不依赖 Binance 持仓合并
"""

import threading
import time
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger

from .config import ConfigManager
from .services.algo_order_service import AlgoOrderService
from .services.trade_record_service import TradeRecordService
from .services.tpsl_monitor import TPSLMonitorService
from .services.history_writer import ReverseHistoryWriter
from .events.order_handler import ReverseOrderHandler
from .workflow_runner import ReverseWorkflowManager
from modules.monitor.clients.mark_price_ws import MarkPriceWSClient

if TYPE_CHECKING:
    from modules.agent.live_engine.engine import BinanceLiveEngine

logger = get_logger('reverse_engine')


class ReverseEngine:
    """反向交易引擎
    
    职责：
    - 监听 Agent 限价单创建事件
    - 创建反向条件单
    - 自主管理开仓记录和 TP/SL（不依赖 Binance 的 TP/SL 订单）
    - 通过 Mark Price WebSocket 监控价格，自行触发平仓
    
    架构：
    - 强制依赖 live_engine，复用其 REST 连接
    - 独立的 Mark Price WebSocket 用于价格监控
    - 每个开仓记录有独立的 TP/SL，支持同币种多仓位
    """
    
    def __init__(self, live_engine: 'BinanceLiveEngine', config: Dict):
        """初始化
        
        Args:
            live_engine: 实盘引擎实例（必需），用于复用 REST 连接
            config: 配置字典
            
        Raises:
            ValueError: 如果 live_engine 为 None
        """
        if live_engine is None:
            raise ValueError("ReverseEngine 必须传入 live_engine 参数，不支持独立运行")
        
        self.config = config
        self._lock = threading.RLock()
        self._running = False
        self._sync_thread = None
        
        self.live_engine = live_engine
        self.rest_client = live_engine.rest_client
        
        self.config_manager = ConfigManager()
        
        self.algo_order_service = AlgoOrderService(self.rest_client, self.config_manager)
        
        self.trade_record_service = TradeRecordService()
        
        self.tpsl_monitor = TPSLMonitorService(self.trade_record_service, self.rest_client)
        
        self.mark_price_ws: Optional[MarkPriceWSClient] = None
        
        self.history_writer = ReverseHistoryWriter(
            config, 
            live_history_writer=live_engine.history_writer
        )
        
        self.order_handler = ReverseOrderHandler(
            self.algo_order_service,
            self.trade_record_service,
            self.history_writer
        )
        
        self.workflow_manager = ReverseWorkflowManager()
        
        logger.info("[反向] 反向交易引擎已初始化（v2 - 自主管理 TP/SL）")
    
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
            logger.info("[反向] 反向交易引擎启动 (v2 - 自主管理 TP/SL)")
            logger.info(f"[反向] 配置: margin={self.config_manager.fixed_margin_usdt}U, "
                       f"leverage={self.config_manager.fixed_leverage}x, "
                       f"expiration={self.config_manager.expiration_days}days")
            logger.info("=" * 60)
            
            try:
                self.algo_order_service.sync_from_api()
                
                self._start_mark_price_ws()
                
                if self.live_engine and hasattr(self.live_engine, 'event_dispatcher'):
                    self.live_engine.event_dispatcher.register_listener(self.order_handler.handle_event)
                    logger.info("[反向] 已注册到 live_engine 的事件分发器")
                else:
                    logger.warning("[反向] 无法注册到 live_engine 事件分发器，将依赖定时同步")
                
                self._sync_thread = threading.Thread(target=self._periodic_sync_loop, daemon=True)
                self._sync_thread.start()
                
                logger.info("[反向] 反向交易引擎启动完成")
                logger.info(f"[反向] 待触发条件单: {len(self.algo_order_service.pending_orders)}")
                logger.info(f"[反向] 当前开仓记录: {len(self.trade_record_service.get_open_records())}")
                
            except Exception as e:
                logger.error(f"[反向] 启动引擎失败: {e}", exc_info=True)
                self._running = False
                raise
    
    def _start_mark_price_ws(self):
        """启动 Mark Price WebSocket"""
        try:
            watched_symbols = self.trade_record_service.get_watched_symbols()
            
            self.mark_price_ws = MarkPriceWSClient(
                on_price_update=self._on_mark_price_update,
                symbols_filter=watched_symbols if watched_symbols else None
            )
            self.mark_price_ws.start()
            logger.info(f"[反向] Mark Price WebSocket 已启动，监控 {len(watched_symbols)} 个交易对")
        except Exception as e:
            logger.error(f"[反向] 启动 Mark Price WebSocket 失败: {e}")
    
    def _on_mark_price_update(self, prices: Dict[str, float]):
        """处理标记价格更新
        
        Args:
            prices: {symbol: mark_price} 字典
        """
        try:
            self.tpsl_monitor.on_mark_price_update(prices)
        except Exception as e:
            logger.error(f"[反向] 处理标记价格更新失败: {e}")
    
    def stop(self):
        """停止引擎"""
        with self._lock:
            if not self._running:
                return
            
            logger.info("[反向] 正在停止反向交易引擎...")
            self._running = False
            
            try:
                self.workflow_manager.stop_all()
                
                if self.mark_price_ws:
                    self.mark_price_ws.stop()
                    logger.info("[反向] Mark Price WebSocket 已停止")
                
                if self.live_engine and hasattr(self.live_engine, 'event_dispatcher'):
                    self.live_engine.event_dispatcher.unregister_listener(self.order_handler.handle_event)
                    logger.info("[反向] 已从 live_engine 事件分发器取消注册")
                
                if self._sync_thread and self._sync_thread.is_alive():
                    time.sleep(0.5)
                
                logger.info("[反向] 反向交易引擎已停止")
                
            except Exception as e:
                logger.error(f"[反向] 停止引擎时出错: {e}")
    
    def _periodic_sync_loop(self):
        """定时同步线程
        
        作为 WebSocket 的兜底机制：
        - 定期检查条件单是否已触发
        - 如果 WebSocket 没有收到事件，通过 API 同步来补偿
        """
        sync_interval = 30
        logger.info(f"[反向] 定时同步线程已启动（间隔={sync_interval}秒）")
        
        while self._running:
            try:
                time.sleep(sync_interval)
                
                if not self._running:
                    break
                
                triggered_orders = self.algo_order_service.sync_from_api()
                
                for order in triggered_orders:
                    logger.info(f"[反向] 🔄 通过定时同步检测到条件单触发: {order.symbol} algoId={order.algo_id}")
                    
                    try:
                        ticker = self.rest_client.get_ticker_price(order.symbol)
                        filled_price = float(ticker.get('price', order.trigger_price))
                    except:
                        filled_price = order.trigger_price
                    
                    logger.info(f"[反向] 创建开仓记录: {order.symbol} @ {filled_price}")
                    
                    self.algo_order_service.mark_order_triggered(order.algo_id, filled_price)
                    
                    record = self.trade_record_service.create_record(order, filled_price)
                    
                    if record:
                        logger.info(f"[反向] ✅ 开仓记录已创建: {order.symbol} {record.side} @ {filled_price}")
                        logger.info(f"[反向]    TP={record.tp_price} SL={record.sl_price}")
                        
                        if self.mark_price_ws:
                            self.mark_price_ws.add_symbol(order.symbol)
                    
                    self.algo_order_service.remove_order(order.algo_id)
                
                self._update_watched_symbols()
                
            except Exception as e:
                logger.error(f"[反向] 定时同步失败: {e}", exc_info=True)
        
        logger.info("[反向] 定时同步线程已退出")
    
    def _update_watched_symbols(self):
        """更新 Mark Price WebSocket 监控的交易对"""
        if not self.mark_price_ws:
            return
        
        watched_symbols = self.trade_record_service.get_watched_symbols()
        
        pending_symbols = {o.symbol for o in self.algo_order_service.pending_orders.values()}
        all_symbols = watched_symbols | pending_symbols
        
        if all_symbols:
            self.mark_price_ws.set_symbols_filter(all_symbols)
        else:
            self.mark_price_ws.symbols_filter = None
    
    def on_agent_limit_order(self, symbol: str, side: str, limit_price: float,
                              tp_price: float, sl_price: float,
                              agent_order_id: Optional[str] = None):
        """Agent 下限价单时触发
        
        创建反向条件单：
        - 方向反转：Agent BUY -> 我们 SELL
        - TP/SL 互换：Agent 的 TP 变成我们的 SL，Agent 的 SL 变成我们的 TP
        - 使用固定保证金和杠杆
        
        Args:
            symbol: 交易对
            side: Agent 方向（long/short）
            limit_price: Agent 限价（作为我们的触发价）
            tp_price: Agent 止盈价（作为我们的止损价）
            sl_price: Agent 止损价（作为我们的止盈价）
            agent_order_id: Agent 订单ID
            
        Returns:
            创建的条件单对象，失败返回 None
        """
        if not self.config_manager.enabled:
            logger.debug(f"[反向] 引擎未启用，跳过处理 {symbol}")
            return None
        
        max_positions = self.config_manager.max_positions
        current_records = len(self.trade_record_service.get_open_records())
        current_pending = len(self.algo_order_service.pending_orders)
        
        if current_records + current_pending >= max_positions:
            logger.warning(f"[反向] 达到最大持仓/挂单数限制 ({max_positions})，跳过 {symbol}")
            return None
        
        reverse_side = 'SELL' if side == 'long' else 'BUY'
        
        reverse_tp = sl_price
        reverse_sl = tp_price
        
        logger.info(f"[反向] 处理 Agent 限价单: {symbol} {side} @ {limit_price}")
        logger.info(f"[反向] 创建反向条件单: {reverse_side} trigger={limit_price} "
                   f"TP={reverse_tp} SL={reverse_sl}")
        
        order = self.algo_order_service.create_conditional_order(
            symbol=symbol,
            side=reverse_side,
            trigger_price=limit_price,
            tp_price=reverse_tp,
            sl_price=reverse_sl,
            agent_order_id=agent_order_id,
            agent_side=side
        )
        
        if order:
            logger.info(f"[反向] 条件单创建成功: {symbol} algoId={order.algo_id}")
            
            if self.mark_price_ws:
                self.mark_price_ws.add_symbol(symbol)
        else:
            logger.error(f"[反向] 条件单创建失败: {symbol}")
        
        return order
    
    def start_symbol_workflow(self, symbol: str, interval: str = "15m") -> bool:
        """启动指定币种的 workflow 分析
        
        每根K线收盘时触发 workflow 分析，Agent 开仓后自动创建反向条件单。
        启动 workflow 会自动启用反向交易引擎。
        
        Args:
            symbol: 交易对（如 "BTCUSDT"）
            interval: K线周期（如 "15m"）
            
        Returns:
            是否成功启动
        """
        if not self.config_manager.enabled:
            logger.info(f"[反向] 自动启用反向交易引擎以启动 {symbol} workflow")
            self.config_manager.update(enabled=True)
        
        return self.workflow_manager.start_symbol(symbol, interval)
    
    def stop_symbol_workflow(self, symbol: str) -> bool:
        """停止指定币种的 workflow 分析
        
        Args:
            symbol: 交易对
            
        Returns:
            是否成功停止
        """
        return self.workflow_manager.stop_symbol(symbol)
    
    def get_running_workflows(self) -> List[str]:
        """获取正在运行 workflow 的币种列表"""
        return self.workflow_manager.get_running_symbols()
    
    def get_workflow_status(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取 workflow 运行状态
        
        Args:
            symbol: 指定币种，None 表示获取所有
        """
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
        return self.trade_record_service.get_summary()
    
    def get_pending_orders_summary(self) -> Dict[str, Any]:
        """获取待触发条件单汇总"""
        return self.algo_order_service.get_summary()
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取历史记录"""
        return self.trade_record_service.get_history(limit)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.trade_record_service.get_statistics()
    
    def cancel_pending_order(self, algo_id: str) -> bool:
        """撤销待触发条件单
        
        Args:
            algo_id: 条件单ID
            
        Returns:
            是否成功
        """
        return self.algo_order_service.cancel_order(algo_id)
    
    def close_record(self, record_id: str) -> bool:
        """手动关闭指定开仓记录
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否成功
        """
        return self.tpsl_monitor.manual_close(record_id, 'MANUAL_CLOSED')
    
    def close_all_records_by_symbol(self, symbol: str) -> int:
        """关闭指定交易对的所有开仓记录
        
        Args:
            symbol: 交易对
            
        Returns:
            关闭的记录数量
        """
        return self.tpsl_monitor.close_all_by_symbol(symbol, 'MANUAL_CLOSED')
    
    def get_summary(self) -> Dict[str, Any]:
        """获取引擎汇总信息
        
        返回格式与前端 ReverseSummary 类型匹配
        """
        return {
            'enabled': self.config_manager.enabled,
            'config': self.config_manager.get_dict(),
            'pending_orders_count': len(self.algo_order_service.pending_orders),
            'positions_count': len(self.trade_record_service.get_open_records()),
            'statistics': self.trade_record_service.get_statistics(),
            'tpsl_monitor_status': self.tpsl_monitor.get_status()
        }
    
    def get_mark_price(self, symbol: str) -> Optional[float]:
        """获取指定交易对的最新标记价格
        
        Args:
            symbol: 交易对
            
        Returns:
            标记价格
        """
        if self.mark_price_ws:
            return self.mark_price_ws.get_latest_price(symbol)
        return None
