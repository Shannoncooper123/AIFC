"""反向交易引擎

当 Agent 下限价单时，自动创建反向条件单进行对冲交易。
使用固定保证金和杠杆，与 Agent 的参数无关。
"""

import threading
import time
from typing import Dict, Any, Optional, List
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.clients.binance_ws import BinanceUserDataWSClient
from modules.monitor.utils.logger import get_logger

from .config import ConfigManager
from .services.algo_order_service import AlgoOrderService
from .services.position_service import ReversePositionService
from .services.history_writer import ReverseHistoryWriter
from .events.order_handler import ReverseOrderHandler
from .workflow_runner import ReverseWorkflowManager

logger = get_logger('reverse_engine')


class ReverseEngine:
    """反向交易引擎
    
    职责：
    - 监听 Agent 限价单创建事件
    - 创建反向条件单
    - 管理反向交易持仓
    - 处理 TP/SL 触发
    """
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.config = config
        self._lock = threading.RLock()
        self._running = False
        self._sync_thread = None
        
        self.rest_client = BinanceRestClient(config)
        
        self.config_manager = ConfigManager()
        
        self.algo_order_service = AlgoOrderService(self.rest_client, self.config_manager)
        self.position_service = ReversePositionService(self.rest_client)
        self.history_writer = ReverseHistoryWriter(config)
        
        self.order_handler = ReverseOrderHandler(
            self.algo_order_service,
            self.position_service,
            self.history_writer
        )
        
        self.user_data_ws: Optional[BinanceUserDataWSClient] = None
        
        self.workflow_manager = ReverseWorkflowManager()
        
        logger.info("反向交易引擎已初始化")
    
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
            logger.info("[反向] 反向交易引擎启动")
            logger.info(f"[反向] 配置: margin={self.config_manager.fixed_margin_usdt}U, "
                       f"leverage={self.config_manager.fixed_leverage}x, "
                       f"expiration={self.config_manager.expiration_days}days")
            logger.info("=" * 60)
            
            try:
                self.algo_order_service.sync_from_api()
                self.position_service.sync_from_api()
                
                self.user_data_ws = BinanceUserDataWSClient(
                    self.config,
                    self.rest_client,
                    self.order_handler.handle_event
                )
                self.user_data_ws.start()
                
                self._sync_thread = threading.Thread(target=self._periodic_sync_loop, daemon=True)
                self._sync_thread.start()
                
                logger.info("[反向] 反向交易引擎启动完成")
                logger.info(f"[反向] 待触发条件单: {len(self.algo_order_service.pending_orders)}")
                logger.info(f"[反向] 当前持仓: {len(self.position_service.positions)}")
                
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
                
                if self._sync_thread and self._sync_thread.is_alive():
                    time.sleep(0.5)
                
                if self.user_data_ws:
                    self.user_data_ws.stop()
                
                if self.rest_client:
                    self.rest_client.close()
                
                logger.info("[反向] 反向交易引擎已停止")
                
            except Exception as e:
                logger.error(f"[反向] 停止引擎时出错: {e}")
    
    def _periodic_sync_loop(self):
        """定时同步线程"""
        sync_interval = 30
        logger.info(f"[反向] 定时同步线程已启动（间隔={sync_interval}秒）")
        
        while self._running:
            try:
                time.sleep(sync_interval)
                
                if not self._running:
                    break
                
                self.algo_order_service.sync_from_api()
                self.position_service.sync_from_api()
                
            except Exception as e:
                logger.error(f"[反向] 定时同步失败: {e}")
        
        logger.info("[反向] 定时同步线程已退出")
    
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
        """
        if not self.config_manager.enabled:
            logger.debug(f"[反向] 引擎未启用，跳过处理 {symbol}")
            return
        
        max_positions = self.config_manager.max_positions
        current_positions = len(self.position_service.positions)
        current_pending = len(self.algo_order_service.pending_orders)
        
        if current_positions + current_pending >= max_positions:
            logger.warning(f"[反向] 达到最大持仓/挂单数限制 ({max_positions})，跳过 {symbol}")
            return
        
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
        else:
            logger.error(f"[反向] 条件单创建失败: {symbol}")
    
    def start_symbol_workflow(self, symbol: str, interval: str = "15m") -> bool:
        """启动指定币种的 workflow 分析
        
        每根K线收盘时触发 workflow 分析，Agent 开仓后自动创建反向条件单。
        
        Args:
            symbol: 交易对（如 "BTCUSDT"）
            interval: K线周期（如 "15m"）
            
        Returns:
            是否成功启动
        """
        if not self.config_manager.enabled:
            logger.warning(f"[反向] 引擎未启用，无法启动 {symbol} workflow")
            return False
        
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
        """获取持仓汇总"""
        return self.position_service.get_positions_summary()
    
    def get_pending_orders_summary(self) -> Dict[str, Any]:
        """获取待触发条件单汇总"""
        return self.algo_order_service.get_summary()
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取历史记录"""
        return self.history_writer.get_history(limit)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.history_writer.get_statistics()
    
    def cancel_pending_order(self, algo_id: str) -> bool:
        """撤销待触发条件单
        
        Args:
            algo_id: 条件单ID
            
        Returns:
            是否成功
        """
        return self.algo_order_service.cancel_order(algo_id)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取引擎汇总信息"""
        return {
            'enabled': self.config_manager.enabled,
            'config': self.config_manager.get_dict(),
            'pending_orders_count': len(self.algo_order_service.pending_orders),
            'positions_count': len(self.position_service.positions),
            'statistics': self.history_writer.get_statistics()
        }
