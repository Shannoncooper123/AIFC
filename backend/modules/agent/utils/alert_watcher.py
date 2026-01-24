"""告警文件监控器 - 监控 alerts.jsonl 文件变化并触发工作流"""
import os
import time
import threading
from typing import Callable, Optional, Set
from modules.monitor.utils.logger import get_logger


class AlertFileWatcher:
    """监控 alerts.jsonl 文件的变化，当有新告警写入时触发回调
    
    内置去重机制：同一 K 线周期内的多次告警会被合并，避免短时间内重复触发 workflow
    """
    
    DEDUP_WINDOW_SECONDS = 120  # 去重时间窗口（秒），同一窗口内的告警会被合并
    
    def __init__(self, alerts_file_path: str, callback: Callable):
        """
        初始化告警文件监控器
        
        Args:
            alerts_file_path: alerts.jsonl 文件的绝对路径
            callback: 当检测到新告警时的回调函数
        """
        self.alerts_file_path = alerts_file_path
        self.callback = callback
        self.logger = get_logger('agent.utils.alert_watcher')
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_position = 0  # 记录上次读取的文件位置
        self._last_mtime = 0  # 记录上次修改时间
        
        self._last_trigger_time: float = 0  # 上次触发 workflow 的时间
        self._pending_symbols: Set[str] = set()  # 待处理的币种（去重窗口内累积）
        self._pending_alerts: list = []  # 待处理的告警详情
        self._dedup_timer: Optional[threading.Timer] = None
        self._dedup_lock = threading.RLock()
        
        # 确保文件存在
        if not os.path.exists(alerts_file_path):
            os.makedirs(os.path.dirname(alerts_file_path), exist_ok=True)
            with open(alerts_file_path, 'w', encoding='utf-8') as f:
                pass  # 创建空文件
            self.logger.info(f"创建告警文件: {alerts_file_path}")
        
        # 初始化文件位置到文件末尾(避免启动时读取历史数据)
        with open(alerts_file_path, 'r', encoding='utf-8') as f:
            f.seek(0, 2)  # 移动到文件末尾
            self._last_position = f.tell()
        
        # 初始化 _last_mtime 为文件当前的修改时间，避免首次告警被跳过
        self._last_mtime = os.path.getmtime(alerts_file_path)
    
    def start(self):
        """启动监控线程"""
        if self._running:
            self.logger.warning("告警监控器已在运行中")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        self.logger.info(f"✓ 告警文件监控器已启动: {self.alerts_file_path}")
    
    def stop(self):
        """停止监控线程"""
        if not self._running:
            return
        
        self._running = False
        
        with self._dedup_lock:
            if self._dedup_timer:
                self._dedup_timer.cancel()
                self._dedup_timer = None
        
        if self._thread:
            self._thread.join(timeout=5)
        self.logger.info("告警文件监控器已停止")
    
    def _watch_loop(self):
        """监控循环主逻辑"""
        poll_interval = 0.5  # 轮询间隔(秒)
        
        while self._running:
            try:
                # 检查文件是否存在
                if not os.path.exists(self.alerts_file_path):
                    self.logger.warning(f"告警文件不存在: {self.alerts_file_path}")
                    time.sleep(poll_interval)
                    continue
                
                # 获取文件修改时间
                current_mtime = os.path.getmtime(self.alerts_file_path)
                
                # 如果文件被修改了
                if current_mtime > self._last_mtime:
                    self._last_mtime = current_mtime
                    
                    # 读取新增的内容
                    with open(self.alerts_file_path, 'r', encoding='utf-8') as f:
                        # 移动到上次读取的位置
                        f.seek(self._last_position)
                        
                        # 读取新增的行
                        new_lines = f.readlines()
                        
                        # 更新位置
                        self._last_position = f.tell()
                        
                        # 如果有新内容，触发回调
                        if new_lines:
                            self.logger.info(f"📋 检测到新告警记录 ({len(new_lines)} 条)")
                            self._handle_new_alerts(new_lines)
                
                time.sleep(poll_interval)
                
            except Exception as e:
                self.logger.error(f"监控告警文件时出错: {e}", exc_info=True)
                time.sleep(poll_interval)
    
    def _handle_new_alerts(self, new_lines: list):
        """处理新的告警记录（带去重逻辑）"""
        import json
        
        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            
            try:
                alert_record = json.loads(line)
                
                if alert_record.get('type') == 'aggregate' and alert_record.get('source') == 'monitor':
                    symbols = alert_record.get('symbols', [])
                    pending_count = alert_record.get('pending_count', 0)
                    
                    if pending_count > 0:
                        self._add_to_pending(symbols, alert_record)
                    else:
                        self.logger.debug("  → 空告警记录，跳过")
                
            except json.JSONDecodeError as e:
                self.logger.error(f"解析告警记录失败: {e}\n内容: {line}")
            except Exception as e:
                self.logger.error(f"处理告警记录时出错: {e}", exc_info=True)
    
    def _add_to_pending(self, symbols: list, alert_record: dict):
        """添加到待处理队列，并启动/重置去重定时器"""
        self.logger.debug(f"[DEBUG] _add_to_pending 开始, symbols={symbols}")
        self.logger.debug(f"[DEBUG] 尝试获取 _dedup_lock...")
        with self._dedup_lock:
            self.logger.debug(f"[DEBUG] 已获取 _dedup_lock")
            new_symbols = [s for s in symbols if s not in self._pending_symbols]
            self._pending_symbols.update(symbols)
            self._pending_alerts.append(alert_record)
            
            if new_symbols:
                self.logger.info(f"  → 新告警: {len(new_symbols)} 个币种 [{', '.join(new_symbols[:3])}{'...' if len(new_symbols) > 3 else ''}]")
            else:
                self.logger.info(f"  → 告警去重: {len(symbols)} 个币种已在队列中")
            
            now = time.time()
            time_since_last = now - self._last_trigger_time
            self.logger.debug(f"[DEBUG] now={now}, _last_trigger_time={self._last_trigger_time}, time_since_last={time_since_last}, DEDUP_WINDOW={self.DEDUP_WINDOW_SECONDS}")
            
            if time_since_last >= self.DEDUP_WINDOW_SECONDS:
                self.logger.debug(f"[DEBUG] 条件满足，准备立即触发 workflow")
                if self._dedup_timer:
                    self._dedup_timer.cancel()
                self.logger.debug(f"[DEBUG] 调用 _trigger_workflow...")
                self._trigger_workflow()
                self.logger.debug(f"[DEBUG] _trigger_workflow 返回")
            else:
                remaining = self.DEDUP_WINDOW_SECONDS - time_since_last
                if self._dedup_timer:
                    self._dedup_timer.cancel()
                self._dedup_timer = threading.Timer(remaining, self._trigger_workflow)
                self._dedup_timer.daemon = True
                self._dedup_timer.start()
                self.logger.info(f"  → 去重窗口: {remaining:.1f}秒后触发 (累计 {len(self._pending_symbols)} 个币种)")
        self.logger.debug(f"[DEBUG] _add_to_pending 结束，已释放 _dedup_lock")
    
    def _trigger_workflow(self):
        """触发 workflow 回调"""
        self.logger.debug(f"[DEBUG] _trigger_workflow 开始")
        self.logger.debug(f"[DEBUG] 尝试获取 _dedup_lock (in _trigger_workflow)...")
        with self._dedup_lock:
            self.logger.debug(f"[DEBUG] 已获取 _dedup_lock (in _trigger_workflow)")
            self.logger.debug(f"[DEBUG] _pending_symbols={self._pending_symbols}")
            if not self._pending_symbols:
                self.logger.debug(f"[DEBUG] _pending_symbols 为空，直接返回")
                return
            
            merged_record = {
                'type': 'aggregate',
                'source': 'monitor',
                'symbols': list(self._pending_symbols),
                'pending_count': len(self._pending_symbols),
                'entries': [],
            }
            
            for alert in self._pending_alerts:
                merged_record['entries'].extend(alert.get('entries', []))
            
            self.logger.info(f"🚀 触发 Workflow: {len(self._pending_symbols)} 个币种 [{', '.join(list(self._pending_symbols)[:5])}{'...' if len(self._pending_symbols) > 5 else ''}]")
            
            self._pending_symbols.clear()
            self._pending_alerts.clear()
            self._last_trigger_time = time.time()
            
            self.logger.debug(f"[DEBUG] 准备调用 callback...")
            try:
                self.callback(merged_record)
                self.logger.debug(f"[DEBUG] callback 执行完成")
            except Exception as e:
                self.logger.error(f"执行告警回调时出错: {e}", exc_info=True)
        self.logger.debug(f"[DEBUG] _trigger_workflow 结束")
