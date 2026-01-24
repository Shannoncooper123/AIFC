"""告警管理器"""
import threading
import time
from typing import Dict, List, Optional, Callable
from ..data.models import AnomalyResult


class AlertManager:
    """告警管理器
    
    使用防抖机制聚合同一周期内的告警：
    - 每次添加告警后重置定时器
    - 定时器到期（10秒内无新告警）后批量发送
    """
    
    def __init__(self, config: Dict):
        self.cooldown_seconds = config['alert']['cooldown_minutes'] * 60
        self.max_batch_size = config['alert']['max_batch_size']
        self.debounce_seconds = config['alert'].get('debounce_seconds', 10)
        
        self._last_alert_time: Dict[str, float] = {}
        self._pending_alerts: Dict[str, AnomalyResult] = {}
        self._send_callback: Optional[Callable] = None
        
        self._debounce_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
    
    def should_alert(self, symbol: str) -> bool:
        """判断是否应该发送告警"""
        if self.cooldown_seconds == 0:
            return True
        
        if symbol in self._last_alert_time:
            elapsed = time.time() - self._last_alert_time[symbol]
            return elapsed >= self.cooldown_seconds
        
        return True
    
    def add_alert(self, result: AnomalyResult):
        """添加告警并重置防抖定时器"""
        with self._lock:
            self._last_alert_time[result.symbol] = time.time()
            self._pending_alerts[result.symbol] = result
            self._reset_debounce_timer()
    
    def _reset_debounce_timer(self):
        """重置防抖定时器（需在锁内调用）"""
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        
        self._debounce_timer = threading.Timer(
            self.debounce_seconds, 
            self._on_debounce_timeout
        )
        self._debounce_timer.daemon = True
        self._debounce_timer.start()
    
    def _on_debounce_timeout(self):
        """防抖定时器到期，触发发送"""
        with self._lock:
            self._debounce_timer = None
            self._trigger_send()
    
    def set_send_callback(self, callback: Callable):
        """设置发送回调"""
        self._send_callback = callback
    
    def _trigger_send(self):
        """触发发送告警（需在锁内调用）"""
        if not self._pending_alerts:
            return
        
        alerts = list(self._pending_alerts.values())[:self.max_batch_size]
        
        if len(self._pending_alerts) > self.max_batch_size:
            from ..utils.logger import get_logger
            logger = get_logger('alert_manager')
            drop_count = len(self._pending_alerts) - self.max_batch_size
            dropped = list(self._pending_alerts.values())[self.max_batch_size:]
            details = ', '.join([f"{a.symbol}({len(a.triggered_indicators)}项触发)" for a in dropped])
            logger.warning(f"告警超限，丢弃 {drop_count} 个: {details}")
        
        self._pending_alerts.clear()
        
        if self._send_callback:
            self._send_callback(alerts)
    
    def force_send_pending(self) -> List[AnomalyResult]:
        """强制发送所有待发送的告警"""
        with self._lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            
            alerts = list(self._pending_alerts.values())[:self.max_batch_size]
            self._pending_alerts.clear()
            return alerts
    
    def stop(self):
        """停止告警管理器"""
        with self._lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None
    
    def get_pending_count(self) -> int:
        """获取待发送告警数量"""
        with self._lock:
            return len(self._pending_alerts)
