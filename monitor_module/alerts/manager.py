"""告警管理器"""
import time
import threading
from typing import Dict, List, Optional, Callable
from ..data.models import AnomalyResult


class AlertManager:
    """告警管理器"""
    
    def __init__(self, config: Dict):
        self.cooldown_seconds = config['alert']['cooldown_minutes'] * 60
        self.max_batch_size = config['alert']['max_batch_size']
        self.send_delay_seconds = config['alert'].get('send_delay_seconds', 3)
        
        self._last_alert_time: Dict[str, float] = {}
        self._pending_alerts: Dict[str, AnomalyResult] = {}
        self._current_kline_timestamp: Optional[int] = None
        self._send_timer: Optional[threading.Timer] = None
        self._send_callback: Optional[Callable] = None
        self._timer_lock = threading.Lock()
    
    def should_alert(self, symbol: str) -> bool:
        """判断是否应该发送告警"""
        if self.cooldown_seconds == 0:
            return True
        
        if symbol in self._last_alert_time:
            elapsed = time.time() - self._last_alert_time[symbol]
            return elapsed >= self.cooldown_seconds
        
        return True
    
    def add_alert(self, result: AnomalyResult):
        """添加告警"""
        self._last_alert_time[result.symbol] = time.time()
        self._pending_alerts[result.symbol] = result
    
    def set_send_callback(self, callback: Callable):
        """设置发送回调"""
        self._send_callback = callback
    
    def check_kline_cycle(self, kline_timestamp: int):
        """检查K线周期并管理延迟发送"""
        with self._timer_lock:
            if self._current_kline_timestamp is None:
                self._current_kline_timestamp = kline_timestamp
                return
            
            # 新周期：立即发送上一周期的告警
            if kline_timestamp != self._current_kline_timestamp:
                if self._send_timer:
                    self._send_timer.cancel()
                self._trigger_send()
                self._current_kline_timestamp = kline_timestamp
            
            # 重启延迟定时器（Debounce机制）
            if self._send_timer:
                self._send_timer.cancel()
            
            self._send_timer = threading.Timer(self.send_delay_seconds, self._trigger_send)
            self._send_timer.daemon = True
            self._send_timer.start()
    
    def _trigger_send(self):
        """触发发送告警"""
        if not self._pending_alerts:
            return
        
        alerts = list(self._pending_alerts.values())[:self.max_batch_size]
        
        if len(self._pending_alerts) > self.max_batch_size:
            from ..utils.logger import get_logger
            logger = get_logger('alert_manager')
            drop_count = len(self._pending_alerts) - self.max_batch_size
            # 展示被丢弃告警的触发类型数量，便于监控噪音
            dropped = list(self._pending_alerts.values())[self.max_batch_size:]
            details = ', '.join([f"{a.symbol}({len(a.triggered_indicators)}项触发)" for a in dropped])
            logger.warning(f"告警超限，丢弃 {drop_count} 个: {details}")
        
        self._pending_alerts.clear()
        
        if self._send_callback:
            self._send_callback(alerts)
    
    def force_send_pending(self) -> List[AnomalyResult]:
        """强制发送所有待发送的告警"""
        with self._timer_lock:
            if self._send_timer:
                self._send_timer.cancel()
            alerts = list(self._pending_alerts.values())[:self.max_batch_size]
            self._pending_alerts.clear()
            return alerts
    
    def stop(self):
        """停止告警管理器"""
        with self._timer_lock:
            if self._send_timer:
                self._send_timer.cancel()
    
    def get_pending_count(self) -> int:
        """获取待发送告警数量"""
        return len(self._pending_alerts)

