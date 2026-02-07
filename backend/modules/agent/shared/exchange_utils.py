"""交易所工具类

提供交易所信息缓存，避免重复 API 调用。
"""

import time
import threading
from typing import Dict, Any, Optional, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('agent.shared.exchange_utils')


class ExchangeInfoCache:
    """交易所信息缓存
    
    单例模式，缓存 exchange_info 数据，避免频繁 API 调用。
    支持自动过期和按需刷新。
    """
    
    _instance: Optional['ExchangeInfoCache'] = None
    _lock = threading.Lock()
    
    _cache: Dict[str, Any] = {}
    _cache_time: float = 0
    _cache_ttl: float = 300
    _rest_client: Optional['BinanceRestClient'] = None
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def set_rest_client(cls, rest_client: 'BinanceRestClient'):
        """设置 REST 客户端（应在引擎启动时调用）"""
        cls._rest_client = rest_client
        logger.debug("ExchangeInfoCache: REST 客户端已设置")
    
    @classmethod
    def _refresh_cache(cls) -> bool:
        """刷新缓存"""
        if cls._rest_client is None:
            logger.warning("ExchangeInfoCache: REST 客户端未设置")
            return False
        
        try:
            cls._cache = cls._rest_client.get_exchange_info()
            cls._cache_time = time.time()
            logger.debug(f"ExchangeInfoCache: 缓存已刷新，包含 {len(cls._cache.get('symbols', []))} 个交易对")
            return True
        except Exception as e:
            logger.error(f"ExchangeInfoCache: 刷新缓存失败: {e}")
            return False
    
    @classmethod
    def _ensure_cache(cls) -> bool:
        """确保缓存有效"""
        if not cls._cache or (time.time() - cls._cache_time > cls._cache_ttl):
            return cls._refresh_cache()
        return True
    
    @classmethod
    def get_symbol_info(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """获取交易对信息"""
        if not cls._ensure_cache():
            return None
        
        for s in cls._cache.get('symbols', []):
            if s.get('symbol') == symbol:
                return s
        return None
    
    @classmethod
    def get_price_precision(cls, symbol: str, default: int = 2) -> int:
        """获取价格精度
        
        Args:
            symbol: 交易对
            default: 默认精度
            
        Returns:
            价格精度（小数位数）
        """
        info = cls.get_symbol_info(symbol)
        if info:
            return info.get('pricePrecision', default)
        
        logger.warning(f"ExchangeInfoCache: 未找到 {symbol} 的价格精度，使用默认值 {default}")
        return default
    
    @classmethod
    def get_quantity_precision(cls, symbol: str, default: int = 3) -> int:
        """获取数量精度
        
        Args:
            symbol: 交易对
            default: 默认精度
            
        Returns:
            数量精度（小数位数）
        """
        info = cls.get_symbol_info(symbol)
        if info:
            return info.get('quantityPrecision', default)
        
        logger.warning(f"ExchangeInfoCache: 未找到 {symbol} 的数量精度，使用默认值 {default}")
        return default
    
    @classmethod
    def format_price(cls, symbol: str, price: float) -> float:
        """格式化价格到正确精度"""
        precision = cls.get_price_precision(symbol)
        return round(price, precision)
    
    @classmethod
    def format_quantity(cls, symbol: str, quantity: float) -> float:
        """格式化数量到正确精度"""
        precision = cls.get_quantity_precision(symbol)
        return round(quantity, precision)
    
    @classmethod
    def clear_cache(cls):
        """清除缓存"""
        cls._cache = {}
        cls._cache_time = 0
        logger.debug("ExchangeInfoCache: 缓存已清除")
