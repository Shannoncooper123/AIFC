"""同步管理器

协调所有同步器的执行，作为 WebSocket 事件的兜底机制。
支持按 source 过滤，可同时服务 live 和 reverse 两种来源。
"""

import threading
import time
from typing import TYPE_CHECKING, Optional
from modules.monitor.utils.logger import get_logger

from .tpsl_syncer import TPSLSyncer
from .position_syncer import PositionSyncer

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient
    from ..services.record_service import RecordService

logger = get_logger('live_engine.sync')


class SyncManager:
    """同步管理器
    
    职责：
    - 启动和停止定时同步线程
    - 协调各个同步器的执行
    - 支持按 source 过滤同步范围
    
    架构：
    - 作为 WebSocket 的兜底机制，定期检查订单和持仓状态
    - 支持 live 和 reverse 两种来源的独立或联合同步
    """
    
    SYNC_INTERVAL = 5
    POSITION_SYNC_MULTIPLIER = 6
    
    def __init__(self, rest_client: 'BinanceRestClient',
                 record_service: 'RecordService'):
        """初始化
        
        Args:
            rest_client: Binance REST 客户端
            record_service: 记录服务
        """
        self.rest_client = rest_client
        self.record_service = record_service
        
        self.tpsl_syncer = TPSLSyncer(rest_client, record_service)
        self.position_syncer = PositionSyncer(rest_client, record_service)
        
        self._running = False
        self._thread = None
        self._source_filter: Optional[str] = None
    
    def set_source_filter(self, source: Optional[str]):
        """设置同步的来源过滤
        
        Args:
            source: 'live', 'reverse' 或 None (全部)
        """
        self._source_filter = source
        logger.info(f"[SyncManager] 同步范围设置为: {source or '全部'}")
    
    def start(self, source: Optional[str] = None):
        """启动同步线程
        
        Args:
            source: 同步的来源过滤 ('live', 'reverse' 或 None 表示全部)
        """
        if self._running:
            logger.warning("[SyncManager] 已在运行")
            return
        
        self._source_filter = source
        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()
        
        position_interval = self.SYNC_INTERVAL * self.POSITION_SYNC_MULTIPLIER
        logger.info(f"[SyncManager] 已启动 (同步间隔={self.SYNC_INTERVAL}s, 持仓同步间隔={position_interval}s, 范围={source or '全部'})")
    
    def stop(self):
        """停止同步线程"""
        if not self._running:
            return
        
        self._running = False
        
        if self._thread and self._thread.is_alive():
            time.sleep(0.5)
        
        logger.info("[SyncManager] 已停止")
    
    def _sync_loop(self):
        """定时同步循环"""
        position_sync_counter = 0
        
        while self._running:
            try:
                time.sleep(self.SYNC_INTERVAL)
                
                if not self._running:
                    break
                
                self.tpsl_syncer.sync(source=self._source_filter)
                
                position_sync_counter += 1
                if position_sync_counter >= self.POSITION_SYNC_MULTIPLIER:
                    position_sync_counter = 0
                    self.position_syncer.sync(source=self._source_filter)
                
            except Exception as e:
                logger.error(f"[SyncManager] 同步失败: {e}", exc_info=True)
        
        logger.info("[SyncManager] 同步线程已退出")
    
    def force_sync(self, source: Optional[str] = None):
        """强制立即执行一次完整同步
        
        Args:
            source: 同步的来源过滤 ('live', 'reverse' 或 None 表示全部)
        """
        src = source if source is not None else self._source_filter
        logger.info(f"[SyncManager] 执行强制同步 (范围={src or '全部'})...")
        
        try:
            self.tpsl_syncer.sync(source=src)
            self.position_syncer.sync(source=src)
            logger.info("[SyncManager] 强制同步完成")
        except Exception as e:
            logger.error(f"[SyncManager] 强制同步失败: {e}")
    
    def get_status(self) -> dict:
        """获取同步状态"""
        return {
            'running': self._running,
            'source_filter': self._source_filter,
            'sync_interval': self.SYNC_INTERVAL,
            'position_sync_interval': self.SYNC_INTERVAL * self.POSITION_SYNC_MULTIPLIER
        }
