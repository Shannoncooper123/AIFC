"""实盘交易引擎配置管理

统一管理实盘交易和反向交易的配置，支持动态更新。
配置存储在 JSON 文件中，由前端动态管理。
"""

import json
import os
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.config')


@dataclass
class TradingConfig:
    """交易配置
    
    包含实盘交易和反向交易的所有配置项。
    """
    # 通用配置
    fixed_margin_usdt: float = 50.0
    fixed_leverage: int = 10
    expiration_days: int = 10
    max_positions: int = 10
    
    # 反向交易配置
    reverse_enabled: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradingConfig':
        """从字典创建"""
        return cls(
            fixed_margin_usdt=data.get('fixed_margin_usdt', 50.0),
            fixed_leverage=data.get('fixed_leverage', 10),
            expiration_days=data.get('expiration_days', 10),
            max_positions=data.get('max_positions', 10),
            reverse_enabled=data.get('reverse_enabled', data.get('enabled', False)),
        )


class TradingConfigManager:
    """交易配置管理器
    
    配置完全由前端动态管理，存储在 JSON 文件中。
    路径从 config.yaml 读取，支持向后兼容旧的 reverse_config.json。
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
        
        self._config = TradingConfig()
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
        支持向后兼容旧的 reverse_config.json 格式。
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._config = TradingConfig.from_dict(data)
                    logger.info(f"交易配置已加载: reverse_enabled={self._config.reverse_enabled}, "
                               f"margin={self._config.fixed_margin_usdt}U, "
                               f"leverage={self._config.fixed_leverage}x")
            else:
                logger.info("交易配置文件不存在，使用默认配置")
                self._save_config()
        except Exception as e:
            logger.error(f"加载交易配置失败: {e}")
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"交易配置已保存到 {self.config_path}")
        except Exception as e:
            logger.error(f"保存交易配置失败: {e}")
    
    @property
    def config(self) -> TradingConfig:
        """获取当前配置"""
        with self._lock:
            return self._config
    
    @property
    def reverse_enabled(self) -> bool:
        """是否启用反向交易"""
        return self._config.reverse_enabled
    
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
    
    def update(self, **kwargs) -> TradingConfig:
        """更新配置
        
        Args:
            **kwargs: 要更新的配置项
            
        Returns:
            更新后的配置
        """
        with self._lock:
            current = self._config.to_dict()
            
            for key, value in kwargs.items():
                if key == 'enabled':
                    current['reverse_enabled'] = bool(value)
                elif key in current:
                    if key == 'reverse_enabled':
                        current[key] = bool(value)
                    elif key == 'fixed_margin_usdt':
                        current[key] = max(1.0, min(float(value), 100000.0))
                    elif key == 'fixed_leverage':
                        current[key] = max(1, min(int(value), 125))
                    elif key == 'expiration_days':
                        current[key] = max(1, min(int(value), 30))
                    elif key == 'max_positions':
                        current[key] = max(1, min(int(value), 100))
            
            self._config = TradingConfig.from_dict(current)
            self._save_config()
            
            logger.info(f"交易配置已更新: {self._config.to_dict()}")
            return self._config
    
    def get_dict(self) -> Dict[str, Any]:
        """获取配置字典"""
        with self._lock:
            return self._config.to_dict()
    
    def get_reverse_config_dict(self) -> Dict[str, Any]:
        """获取反向交易配置字典（向后兼容）"""
        with self._lock:
            return {
                'enabled': self._config.reverse_enabled,
                'fixed_margin_usdt': self._config.fixed_margin_usdt,
                'fixed_leverage': self._config.fixed_leverage,
                'expiration_days': self._config.expiration_days,
                'max_positions': self._config.max_positions,
            }


_trading_config_manager: Optional[TradingConfigManager] = None
_config_lock = threading.RLock()


def get_trading_config_manager() -> TradingConfigManager:
    """获取交易配置管理器单例"""
    global _trading_config_manager
    with _config_lock:
        if _trading_config_manager is None:
            _trading_config_manager = TradingConfigManager()
        return _trading_config_manager
