"""价格服务：统一价格获取

消除多处重复的价格获取代码，提供统一的价格查询接口。
"""
from typing import TYPE_CHECKING, Optional

from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('live_engine.price_service')


class PriceService:
    """价格服务
    
    统一管理所有价格获取操作，支持：
    - 标记价格（Mark Price）
    - 最新成交价（Last Price）
    - 带回退的价格获取
    """

    def __init__(self, rest_client: 'BinanceRestClient'):
        """初始化
        
        Args:
            rest_client: Binance REST 客户端
        """
        self.rest_client = rest_client

    def get_mark_price(self, symbol: str) -> Optional[float]:
        """获取标记价格
        
        Args:
            symbol: 交易对
            
        Returns:
            标记价格，失败返回 None
        """
        try:
            data = self.rest_client.get_mark_price(symbol)
            price = float(data.get('markPrice', 0))
            if price > 0:
                return price
            return None
        except Exception as e:
            logger.warning(f"获取 {symbol} 标记价格失败: {e}")
            return None

    def get_last_price(self, symbol: str) -> Optional[float]:
        """获取最新成交价格
        
        优先使用 WebSocket API（连接复用，权重低），
        失败时回退到 REST API。
        
        Args:
            symbol: 交易对
            
        Returns:
            最新价格，失败返回 None
        """
        try:
            from modules.agent.live_engine.core.exchange_utils import get_latest_price
            price = get_latest_price(symbol)
            if price:
                return price
        except Exception as e:
            logger.debug(f"WebSocket API 获取价格失败，回退到 REST: {e}")

        try:
            ticker = self.rest_client.get_ticker_price(symbol)
            if isinstance(ticker, list) and len(ticker) > 0:
                ticker = ticker[0]
            price = float(ticker.get('price', 0))
            if price > 0:
                return price
            return None
        except Exception as e:
            logger.warning(f"获取 {symbol} 最新价格失败: {e}")
            return None

    def get_mark_price_with_fallback(self, symbol: str, fallback: float) -> float:
        """获取标记价格，失败时返回回退值
        
        Args:
            symbol: 交易对
            fallback: 回退价格
            
        Returns:
            标记价格或回退值
        """
        price = self.get_mark_price(symbol)
        return price if price is not None else fallback

    def get_last_price_with_fallback(self, symbol: str, fallback: float) -> float:
        """获取最新价格，失败时返回回退值
        
        Args:
            symbol: 交易对
            fallback: 回退价格
            
        Returns:
            最新价格或回退值
        """
        price = self.get_last_price(symbol)
        return price if price is not None else fallback

    def get_best_price(self, symbol: str) -> Optional[float]:
        """获取最佳价格（优先标记价格，回退到最新价格）
        
        Args:
            symbol: 交易对
            
        Returns:
            价格，失败返回 None
        """
        price = self.get_mark_price(symbol)
        if price is not None:
            return price
        return self.get_last_price(symbol)
