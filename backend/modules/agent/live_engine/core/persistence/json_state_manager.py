"""JSON 状态管理器

提供通用的 JSON 文件状态持久化功能。
"""

import json
import os
import threading
from typing import Dict, Any, Optional
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.shared.persistence')


class JsonStateManager:
    """JSON 状态管理器
    
    提供线程安全的 JSON 状态文件读写功能。
    支持自动创建目录和原子写入。
    """
    
    def __init__(self, file_path: str, auto_ensure_dir: bool = True):
        """初始化
        
        Args:
            file_path: 状态文件路径
            auto_ensure_dir: 是否自动创建目录
        """
        self.file_path = file_path
        self._lock = threading.RLock()
        
        if auto_ensure_dir:
            self._ensure_dir()
    
    def _ensure_dir(self):
        """确保目录存在"""
        state_dir = os.path.dirname(self.file_path)
        if state_dir and not os.path.exists(state_dir):
            os.makedirs(state_dir, exist_ok=True)
            logger.debug(f"JsonStateManager: 创建目录 {state_dir}")
    
    def load(self, default: Optional[Dict] = None) -> Dict[str, Any]:
        """加载状态
        
        Args:
            default: 文件不存在时返回的默认值
            
        Returns:
            状态字典
        """
        with self._lock:
            try:
                if os.path.exists(self.file_path):
                    with open(self.file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        logger.debug(f"JsonStateManager: 已加载状态 {self.file_path}")
                        return data
                else:
                    logger.debug(f"JsonStateManager: 文件不存在 {self.file_path}")
                    return default if default is not None else {}
            except json.JSONDecodeError as e:
                logger.error(f"JsonStateManager: JSON 解析失败 {self.file_path}: {e}")
                return default if default is not None else {}
            except Exception as e:
                logger.error(f"JsonStateManager: 加载状态失败 {self.file_path}: {e}")
                return default if default is not None else {}
    
    def save(self, data: Dict[str, Any]) -> bool:
        """保存状态
        
        Args:
            data: 状态字典
            
        Returns:
            是否成功
        """
        with self._lock:
            try:
                self._ensure_dir()
                
                temp_path = f"{self.file_path}.tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                os.replace(temp_path, self.file_path)
                logger.debug(f"JsonStateManager: 已保存状态 {self.file_path}")
                return True
            except Exception as e:
                logger.error(f"JsonStateManager: 保存状态失败 {self.file_path}: {e}")
                return False
    
    def exists(self) -> bool:
        """检查状态文件是否存在"""
        return os.path.exists(self.file_path)
    
    def delete(self) -> bool:
        """删除状态文件"""
        with self._lock:
            try:
                if os.path.exists(self.file_path):
                    os.remove(self.file_path)
                    logger.debug(f"JsonStateManager: 已删除 {self.file_path}")
                return True
            except Exception as e:
                logger.error(f"JsonStateManager: 删除失败 {self.file_path}: {e}")
                return False
