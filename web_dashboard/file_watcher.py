"""文件监控器：监控 JSON 文件变化并触发回调"""
import os
import json
import time
import sys
from typing import Callable, Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from monitor_module.utils.logger import setup_logger

logger = setup_logger()


class JSONFileHandler(FileSystemEventHandler):
    """JSON 文件变化处理器"""
    
    def __init__(self, file_path: str, callback: Callable[[str, Dict[str, Any]], None], file_type: str, debounce_delay: float = 2.0):
        super().__init__()
        self.file_path = os.path.abspath(file_path)
        self.callback = callback
        self.file_type = file_type
        self.last_modified = 0
        self._debounce_delay = debounce_delay
    
    def on_modified(self, event):
        """文件修改事件"""
        if isinstance(event, FileModifiedEvent):
            # 只处理目标文件的修改事件
            if os.path.abspath(event.src_path) == self.file_path:
                # 防抖
                current_time = time.time()
                if current_time - self.last_modified < self._debounce_delay:
                    return
                
                self.last_modified = current_time
                
                # 重试读取，避免读到正在写入的文件
                max_retries = 3
                retry_delay = 0.1
                
                for attempt in range(max_retries):
                    try:
                        # 等待写入完成
                        if attempt > 0:
                            time.sleep(retry_delay * attempt)
                        
                        # 读取文件内容
                        with open(self.file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 触发回调
                        self.callback(self.file_type, data)
                        break
                        
                    except json.JSONDecodeError as e:
                        if attempt < max_retries - 1:
                            # 继续重试
                            continue
                        else:
                            logger.error(f"✗ JSON decode error in {self.file_type} after {max_retries} attempts: {e}")
                    except Exception as e:
                        logger.error(f"✗ Error reading {self.file_type}: {e}")
                        break


class FileWatcher:
    """文件监控器：监控多个 JSON 文件变化"""
    
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.observers = []
        self.callbacks = []
        
        # 监控的文件路径
        self.watched_files = {
            'trade_state': os.path.join(base_dir, 'agent', 'trade_state.json'),
            'position_history': os.path.join(base_dir, 'logs', 'position_history.json'),
            'agent_reports': os.path.join(base_dir, 'logs', 'agent_reports.json'),
            'pending_orders': os.path.join(base_dir, 'agent', 'pending_orders.json'),
            'asset_timeline': os.path.join(base_dir, 'logs', 'asset_timeline.json'),
        }
        
        # 不同文件类型的防抖时间（秒）
        self.debounce_delays = {
            'trade_state': 1.0,          # 交易状态：1秒
            'position_history': 2.0,      # 持仓历史：2秒
            'agent_reports': 2.0,         # Agent报告：2秒
            'pending_orders': 5.0,        # 待处理订单：5秒（最频繁，需要更长防抖）
            'asset_timeline': 2.0,        # 资产时间线：2秒
        }
    
    def register_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        self.callbacks.append(callback)
    
    def _trigger_callbacks(self, file_type: str, data: Dict[str, Any]):
        """触发回调"""
        for callback in self.callbacks:
            try:
                callback(file_type, data)
            except Exception as e:
                logger.error(f"Error in callback for {file_type}: {e}")
    
    def start(self):
        """启动"""
        for file_type, file_path in self.watched_files.items():
            # 文件存在校验
            if not os.path.exists(file_path):
                logger.warning(f"Warning: {file_path} does not exist")
                continue
            
            # 观察者
            observer = Observer()
            
            # 获取该文件类型的防抖时间
            debounce_delay = self.debounce_delays.get(file_type, 2.0)
            
            # 事件处理器
            event_handler = JSONFileHandler(
                file_path=file_path,
                callback=self._trigger_callbacks,
                file_type=file_type,
                debounce_delay=debounce_delay
            )
            
            # 监控文件所在目录
            watch_dir = os.path.dirname(file_path)
            observer.schedule(event_handler, watch_dir, recursive=False)
            observer.start()
            
            self.observers.append(observer)
            logger.info(f"Started watching: {file_path} (debounce: {debounce_delay}s)")
    
    def stop(self):
        """停止"""
        for observer in self.observers:
            observer.stop()
            observer.join()
        
        self.observers.clear()
        logger.info("File watcher stopped")
    
    def load_initial_data(self) -> Dict[str, Any]:
        """加载初始数据"""
        initial_data = {}
        
        for file_type, file_path in self.watched_files.items():
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        initial_data[file_type] = json.load(f)
                else:
                    initial_data[file_type] = None
            except Exception as e:
                logger.error(f"Error loading {file_type}: {e}")
                initial_data[file_type] = None
        
        return initial_data

