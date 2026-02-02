"""反向交易引擎配置管理"""

import json
import os
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from modules.monitor.utils.logger import get_logger

logger = get_logger('reverse_engine.config')


@dataclass
class ReverseEngineConfig:
    """反向交易引擎配置
    
    所有参数都是固定值，不跟随 Agent 的参数
    """
    enabled: bool = False
    fixed_margin_usdt: float = 50.0
    fixed_leverage: int = 10
    expiration_days: int = 10
    max_positions: int = 10
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReverseEngineConfig':
        """从字典创建"""
        return cls(
            enabled=data.get('enabled', False),
            fixed_margin_usdt=data.get('fixed_margin_usdt', 50.0),
            fixed_leverage=data.get('fixed_leverage', 10),
            expiration_days=data.get('expiration_days', 10),
            max_positions=data.get('max_positions', 10)
        )


class ConfigManager:
    """配置管理器
    
    配置完全由前端动态管理，存储在 JSON 文件中。
    路径从 config.yaml 读取。
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化
        
        Args:
            config_path: 配置文件路径，如果为 None 则从 config.yaml 读取
        """
        if config_path:
            self.config_path = config_path
        else:
            self.config_path = self._get_config_path_from_settings()
        
        self._config = ReverseEngineConfig()
        self._lock = threading.RLock()
        
        self._ensure_config_dir()
        self._load_config()
    
    def _get_config_path_from_settings(self) -> str:
        """从 settings.py 获取配置路径"""
        try:
            from modules.config.settings import get_config
            config = get_config()
            reverse_cfg = config.get('agent', {}).get('reverse', {})
            return reverse_cfg.get('config_path', 'modules/data/reverse_config.json')
        except Exception as e:
            logger.warning(f"从 settings 获取配置路径失败，使用默认路径: {e}")
            return 'modules/data/reverse_config.json'
    
    def _ensure_config_dir(self):
        """确保配置目录存在"""
        config_dir = os.path.dirname(self.config_path)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
    
    def _load_config(self):
        """从文件加载配置
        
        配置完全由前端动态管理，存储在 JSON 文件中。
        如果文件不存在，使用默认值并保存。
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._config = ReverseEngineConfig.from_dict(data)
                    logger.info(f"反向交易配置已加载: enabled={self._config.enabled}, "
                               f"margin={self._config.fixed_margin_usdt}U, "
                               f"leverage={self._config.fixed_leverage}x")
            else:
                logger.info("反向交易配置文件不存在，使用默认配置")
                self._save_config()
        except Exception as e:
            logger.error(f"加载反向交易配置失败: {e}")
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"反向交易配置已保存到 {self.config_path}")
        except Exception as e:
            logger.error(f"保存反向交易配置失败: {e}")
    
    @property
    def config(self) -> ReverseEngineConfig:
        """获取当前配置"""
        with self._lock:
            return self._config
    
    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._config.enabled
    
    @property
    def fixed_margin_usdt(self) -> float:
        """固定保证金"""
        return self._config.fixed_margin_usdt
    
    @property
    def fixed_leverage(self) -> int:
        """固定杠杆"""
        return self._config.fixed_leverage
    
    @property
    def expiration_days(self) -> int:
        """条件单过期天数"""
        return self._config.expiration_days
    
    @property
    def max_positions(self) -> int:
        """最大持仓数"""
        return self._config.max_positions
    
    def update(self, **kwargs) -> ReverseEngineConfig:
        """更新配置
        
        Args:
            **kwargs: 要更新的配置项
            
        Returns:
            更新后的配置
        """
        with self._lock:
            current = self._config.to_dict()
            
            for key, value in kwargs.items():
                if key in current:
                    if key == 'enabled':
                        current[key] = bool(value)
                    elif key == 'fixed_margin_usdt':
                        current[key] = max(1.0, min(float(value), 100000.0))
                    elif key == 'fixed_leverage':
                        current[key] = max(1, min(int(value), 125))
                    elif key == 'expiration_days':
                        current[key] = max(1, min(int(value), 30))
                    elif key == 'max_positions':
                        current[key] = max(1, min(int(value), 100))
            
            self._config = ReverseEngineConfig.from_dict(current)
            self._save_config()
            
            logger.info(f"反向交易配置已更新: {self._config.to_dict()}")
            return self._config
    
    def get_dict(self) -> Dict[str, Any]:
        """获取配置字典"""
        with self._lock:
            return self._config.to_dict()
