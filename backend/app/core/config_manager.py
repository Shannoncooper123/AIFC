"""配置管理器：支持热重载和变更检测"""
import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import yaml

from app.core.events import Event, EventType, event_bus


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ConfigManager:
    """
    配置管理器单例
    
    功能：
    1. 配置加载与缓存
    2. 变更检测（基于文件hash）
    3. 热重载通知（通过事件总线）
    4. 配置订阅机制（服务可订阅特定配置节的变更）
    """
    _instance: Optional["ConfigManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._config: Dict[str, Any] = {}
        self._config_hash: str = ""
        self._config_path = BASE_DIR / "config.yaml"
        self._subscribers: Dict[str, List[Callable[[str, Dict[str, Any]], None]]] = {}
        self._async_subscribers: Dict[str, List[Callable[[str, Dict[str, Any]], Any]]] = {}
        self._lock = asyncio.Lock()
        
        self._load_config()
    
    def _compute_hash(self, content: str) -> str:
        """计算配置内容的hash"""
        return hashlib.md5(content.encode()).hexdigest()
    
    def _load_config(self) -> None:
        """加载配置文件"""
        if not self._config_path.exists():
            logger.error(f"配置文件不存在: {self._config_path}")
            return
        
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            self._config = yaml.safe_load(content) or {}
            self._config_hash = self._compute_hash(content)
            logger.info(f"配置已加载，hash: {self._config_hash[:8]}...")
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
    
    def get_config(self, section: Optional[str] = None) -> Any:
        """
        获取配置
        
        Args:
            section: 配置节名称。为 None 时返回全部配置。
        
        Returns:
            配置字典或指定节的配置
        """
        if section is None:
            return self._config.copy()
        return self._config.get(section, {})
    
    def get_value(self, section: str, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            section: 配置节名称
            key: 配置键名
            default: 默认值
        
        Returns:
            配置值
        """
        section_config = self._config.get(section, {})
        return section_config.get(key, default)
    
    async def update_section(self, section: str, data: Dict[str, Any]) -> bool:
        """
        更新配置节（支持热重载）
        
        Args:
            section: 配置节名称
            data: 要更新的数据（会与现有配置合并）
        
        Returns:
            是否更新成功
        """
        async with self._lock:
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    full_config = yaml.safe_load(content) or {}
                
                if section not in full_config:
                    logger.error(f"配置节不存在: {section}")
                    return False
                
                old_section = full_config[section].copy()
                full_config[section].update(data)
                new_section = full_config[section]
                
                with open(self._config_path, "w", encoding="utf-8") as f:
                    yaml.dump(full_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                
                self._config = full_config
                new_content = yaml.dump(full_config, allow_unicode=True, default_flow_style=False)
                self._config_hash = self._compute_hash(new_content)
                
                changed_keys = self._detect_changes(old_section, new_section)
                if changed_keys:
                    logger.info(f"配置节 {section} 已更新，变更的键: {changed_keys}")
                    await self._notify_subscribers(section, new_section, changed_keys)
                
                return True
                
            except Exception as e:
                logger.error(f"更新配置失败: {e}")
                return False
    
    def _detect_changes(self, old: Dict[str, Any], new: Dict[str, Any]) -> Set[str]:
        """检测配置变更"""
        changed = set()
        all_keys = set(old.keys()) | set(new.keys())
        
        for key in all_keys:
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val != new_val:
                changed.add(key)
        
        return changed
    
    async def reload(self) -> bool:
        """
        重新加载配置文件
        
        Returns:
            是否有配置变更
        """
        async with self._lock:
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                new_hash = self._compute_hash(content)
                if new_hash == self._config_hash:
                    logger.info("配置文件无变更")
                    return False
                
                old_config = self._config.copy()
                new_config = yaml.safe_load(content) or {}
                
                self._config = new_config
                self._config_hash = new_hash
                
                for section in set(old_config.keys()) | set(new_config.keys()):
                    old_section = old_config.get(section, {})
                    new_section = new_config.get(section, {})
                    
                    if isinstance(old_section, dict) and isinstance(new_section, dict):
                        changed_keys = self._detect_changes(old_section, new_section)
                        if changed_keys:
                            logger.info(f"配置节 {section} 有变更: {changed_keys}")
                            await self._notify_subscribers(section, new_section, changed_keys)
                
                logger.info(f"配置已重新加载，新hash: {new_hash[:8]}...")
                return True
                
            except Exception as e:
                logger.error(f"重新加载配置失败: {e}")
                return False
    
    def subscribe(self, section: str, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        订阅配置节变更（同步回调）
        
        Args:
            section: 配置节名称，使用 "*" 订阅所有变更
            callback: 回调函数，接收 (section_name, new_config) 参数
        """
        if section not in self._subscribers:
            self._subscribers[section] = []
        self._subscribers[section].append(callback)
        logger.debug(f"已订阅配置节 {section} 的变更")
    
    def subscribe_async(self, section: str, callback: Callable[[str, Dict[str, Any]], Any]) -> None:
        """
        订阅配置节变更（异步回调）
        
        Args:
            section: 配置节名称，使用 "*" 订阅所有变更
            callback: 异步回调函数，接收 (section_name, new_config) 参数
        """
        if section not in self._async_subscribers:
            self._async_subscribers[section] = []
        self._async_subscribers[section].append(callback)
        logger.debug(f"已订阅配置节 {section} 的异步变更")
    
    def unsubscribe(self, section: str, callback: Callable) -> None:
        """取消订阅"""
        if section in self._subscribers:
            self._subscribers[section] = [cb for cb in self._subscribers[section] if cb != callback]
        if section in self._async_subscribers:
            self._async_subscribers[section] = [cb for cb in self._async_subscribers[section] if cb != callback]
    
    async def _notify_subscribers(self, section: str, config: Dict[str, Any], changed_keys: Set[str]) -> None:
        """通知订阅者配置变更"""
        callbacks_to_call = []
        async_callbacks_to_call = []
        
        if section in self._subscribers:
            callbacks_to_call.extend(self._subscribers[section])
        if "*" in self._subscribers:
            callbacks_to_call.extend(self._subscribers["*"])
        
        if section in self._async_subscribers:
            async_callbacks_to_call.extend(self._async_subscribers[section])
        if "*" in self._async_subscribers:
            async_callbacks_to_call.extend(self._async_subscribers["*"])
        
        for callback in callbacks_to_call:
            try:
                callback(section, config)
            except Exception as e:
                logger.error(f"配置变更回调执行失败: {e}")
        
        for callback in async_callbacks_to_call:
            try:
                await callback(section, config)
            except Exception as e:
                logger.error(f"配置变更异步回调执行失败: {e}")
        
        await event_bus.publish(Event(
            type=EventType.CONFIG_UPDATED,
            data={
                "section": section,
                "changed_keys": list(changed_keys),
                "config": config,
            }
        ))


config_manager = ConfigManager()


def get_config(section: Optional[str] = None) -> Any:
    """获取配置（便捷函数）"""
    return config_manager.get_config(section)


def get_value(section: str, key: str, default: Any = None) -> Any:
    """获取配置值（便捷函数）"""
    return config_manager.get_value(section, key, default)
