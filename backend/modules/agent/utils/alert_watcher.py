"""告警文件监控器 - 监控 alerts.jsonl 文件变化并触发工作流"""
import os
import time
import threading
from typing import Callable, Optional
from modules.monitor.utils.logger import setup_logger


class AlertFileWatcher:
    """监控 alerts.jsonl 文件的变化，当有新告警写入时触发回调"""
    
    def __init__(self, alerts_file_path: str, callback: Callable):
        """
        初始化告警文件监控器
        
        Args:
            alerts_file_path: alerts.jsonl 文件的绝对路径
            callback: 当检测到新告警时的回调函数
        """
        self.alerts_file_path = alerts_file_path
        self.callback = callback
        self.logger = setup_logger()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_position = 0  # 记录上次读取的文件位置
        self._last_mtime = 0  # 记录上次修改时间
        
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
        """处理新的告警记录"""
        import json
        
        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            
            try:
                alert_record = json.loads(line)
                
                # 检查是否是聚合告警记录
                if alert_record.get('type') == 'aggregate' and alert_record.get('source') == 'monitor':
                    symbols = alert_record.get('symbols', [])
                    pending_count = alert_record.get('pending_count', 0)
                    
                    if pending_count > 0:
                        self.logger.info(f"  → 新告警: {pending_count} 个币种 [{', '.join(symbols[:3])}...]")
                        
                        # 触发回调
                        try:
                            self.callback(alert_record)
                        except Exception as e:
                            self.logger.error(f"执行告警回调时出错: {e}", exc_info=True)
                    else:
                        self.logger.debug("  → 空告警记录，跳过")
                
            except json.JSONDecodeError as e:
                self.logger.error(f"解析告警记录失败: {e}\n内容: {line}")
            except Exception as e:
                self.logger.error(f"处理告警记录时出错: {e}", exc_info=True)
