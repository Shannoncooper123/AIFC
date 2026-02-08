"""交易所工具类

提供：
1. ExchangeInfoCache - 交易所信息缓存，用于格式化价格和数量精度
2. 实时价格获取 - 通过 WebSocket API 获取最新价格
"""

import threading
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('agent.shared.exchange_utils')


def _count_decimal_places(value_str: str) -> int:
    """计算字符串表示的小数位数（有效位数）"""
    try:
        value_str = value_str.strip()
        if '.' not in value_str:
            return 0
        decimal_part = value_str.split('.')[1].rstrip('0')
        return len(decimal_part) if decimal_part else 0
    except Exception:
        return 0


class ExchangeInfoCache:
    """交易所信息缓存

    单例模式，缓存 exchange_info 数据，避免频繁 API 调用。
    使用 filters 中的 tickSize/stepSize 来计算精度。
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
    def _get_symbol_info(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """获取交易对信息"""
        if not cls._ensure_cache():
            return None

        for s in cls._cache.get('symbols', []):
            if s.get('symbol') == symbol:
                return s
        return None

    @classmethod
    def _get_filter(cls, symbol: str, filter_type: str) -> Optional[Dict[str, Any]]:
        """获取指定类型的 filter"""
        info = cls._get_symbol_info(symbol)
        if not info:
            return None

        for f in info.get('filters', []):
            if f.get('filterType') == filter_type:
                return f
        return None

    @classmethod
    def _get_tick_size(cls, symbol: str) -> Optional[float]:
        """获取价格最小变动单位"""
        price_filter = cls._get_filter(symbol, 'PRICE_FILTER')
        if price_filter:
            tick_size = price_filter.get('tickSize')
            if tick_size:
                return float(tick_size)
        return None

    @classmethod
    def _get_step_size(cls, symbol: str) -> Optional[float]:
        """获取数量最小变动单位"""
        lot_filter = cls._get_filter(symbol, 'LOT_SIZE')
        if lot_filter:
            step_size = lot_filter.get('stepSize')
            if step_size:
                return float(step_size)
        return None

    @classmethod
    def _get_price_precision(cls, symbol: str, default: int = 2) -> int:
        """获取价格精度"""
        price_filter = cls._get_filter(symbol, 'PRICE_FILTER')
        if price_filter:
            tick_size = price_filter.get('tickSize')
            if tick_size:
                precision = _count_decimal_places(tick_size)
                if precision > 0:
                    return precision

        info = cls._get_symbol_info(symbol)
        if info:
            return info.get('pricePrecision', default)
        return default

    @classmethod
    def _get_quantity_precision(cls, symbol: str, default: int = 3) -> int:
        """获取数量精度"""
        lot_filter = cls._get_filter(symbol, 'LOT_SIZE')
        if lot_filter:
            step_size = lot_filter.get('stepSize')
            if step_size:
                return _count_decimal_places(step_size)

        info = cls._get_symbol_info(symbol)
        if info:
            return info.get('quantityPrecision', default)
        return default

    @classmethod
    def format_price(cls, symbol: str, price: float) -> float:
        """格式化价格到正确精度
        
        使用 tickSize 或 pricePrecision 进行舍入。
        """
        tick_size = cls._get_tick_size(symbol)
        if tick_size and tick_size > 0:
            price_filter = cls._get_filter(symbol, 'PRICE_FILTER')
            tick_str = price_filter.get('tickSize', str(tick_size)) if price_filter else str(tick_size)
            tick_decimal = Decimal(tick_str)
            return float(Decimal(str(price)).quantize(tick_decimal))

        precision = cls._get_price_precision(symbol)
        return round(price, precision)

    @classmethod
    def format_quantity(cls, symbol: str, quantity: float) -> float:
        """格式化数量到正确精度
        
        使用 stepSize 或 quantityPrecision 进行舍入。
        注意：stepSize 可能是整数（如 '1'）需要正确处理。
        """
        step_size = cls._get_step_size(symbol)
        if step_size and step_size > 0:
            lot_filter = cls._get_filter(symbol, 'LOT_SIZE')
            step_str = lot_filter.get('stepSize', '1') if lot_filter else str(step_size)
            step_decimal = Decimal(step_str)
            return float(Decimal(str(quantity)).quantize(step_decimal))

        precision = cls._get_quantity_precision(symbol)
        return round(quantity, precision)


_price_client = None
_price_client_lock = threading.Lock()


def _get_price_client():
    """获取价格客户端单例"""
    global _price_client
    with _price_client_lock:
        if _price_client is None:
            from modules.monitor.clients.binance_ws import BinancePriceWSClient
            _price_client = BinancePriceWSClient()
        return _price_client


def get_latest_price(symbol: str) -> Optional[float]:
    """获取最新价格

    通过 WebSocket API 获取，连接复用。

    Args:
        symbol: 交易对（如 BTCUSDT）

    Returns:
        最新价格，失败返回 None
    """
    client = _get_price_client()
    return client.get_price(symbol)


def get_all_prices() -> Dict[str, float]:
    """获取所有交易对的最新价格"""
    client = _get_price_client()
    return client.get_all_prices()


def disconnect_price_client():
    """断开价格客户端连接"""
    global _price_client
    with _price_client_lock:
        if _price_client is not None:
            _price_client.disconnect()
            _price_client = None
