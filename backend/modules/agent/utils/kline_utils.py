"""K-line 数据获取工具库
 
提供统一的 K-line 数据获取接口，支持回测模式和实盘模式的透明切换。
"""
import contextvars
import threading
from datetime import datetime
from typing import List, Optional, Protocol, Tuple, runtime_checkable

from modules.config.settings import get_config
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.utils.kline')

_binance_client: Optional[BinanceRestClient] = None
_binance_client_lock = threading.Lock()


@runtime_checkable
class KlineProviderProtocol(Protocol):
    """K线数据提供者协议 - 支持实盘和回测模式切换"""
    
    def get_klines(self, symbol: str, interval: str, limit: int) -> List[Kline]:
        """获取K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期
            limit: 获取数量
        
        Returns:
            K线数据列表
        """
        ...
    
    def get_current_time(self) -> datetime:
        """获取当前时间（实盘为真实时间，回测为模拟时间）"""
        ...


_kline_provider: Optional[KlineProviderProtocol] = None
_kline_provider_lock = threading.Lock()

_context_kline_provider: contextvars.ContextVar[Optional[KlineProviderProtocol]] = contextvars.ContextVar(
    'context_kline_provider', default=None
)


def set_kline_provider(
    provider: Optional[KlineProviderProtocol], 
    context_local: bool = False
) -> Optional[contextvars.Token]:
    """设置K线数据提供者（用于回测模式注入）
    
    Args:
        provider: K线提供者实例，传入None则恢复默认行为
        context_local: 是否设置为上下文本地（回测并发模式使用）
    
    Returns:
        如果 context_local=True，返回 Token 用于后续恢复；否则返回 None
    """
    if context_local:
        return _context_kline_provider.set(provider)
    else:
        global _kline_provider
        with _kline_provider_lock:
            _kline_provider = provider
            if provider is not None:
                logger.info(f"KlineProvider 已设置: {type(provider).__name__}")
            else:
                logger.info("KlineProvider 已清除，恢复默认模式")
        return None


def get_kline_provider() -> Optional[KlineProviderProtocol]:
    """获取当前K线数据提供者
    
    优先返回上下文本地提供者（回测并发模式），否则返回全局提供者。
    使用 contextvars 支持 asyncio 上下文传播。
    
    Returns:
        当前设置的K线提供者，如果未设置则返回None
    """
    context_provider = _context_kline_provider.get()
    if context_provider is not None:
        return context_provider
    
    with _kline_provider_lock:
        return _kline_provider


def clear_context_kline_provider() -> None:
    """清除当前上下文的本地 KlineProvider"""
    _context_kline_provider.set(None)


def reset_context_kline_provider(token: contextvars.Token) -> None:
    """重置上下文 KlineProvider 到之前的值
    
    Args:
        token: set_kline_provider 返回的 token
    """
    _context_kline_provider.reset(token)


def get_binance_client() -> BinanceRestClient:
    """获取Binance REST客户端单例实例（线程安全）
    
    Returns:
        BinanceRestClient单例实例
    """
    global _binance_client
    if _binance_client is None:
        with _binance_client_lock:
            if _binance_client is None:
                cfg = get_config()
                _binance_client = BinanceRestClient(cfg)
                logger.info("BinanceRestClient 单例已创建")
    return _binance_client


def reset_binance_client() -> None:
    """重置 BinanceRestClient 单例（用于配置变更或测试）"""
    global _binance_client
    with _binance_client_lock:
        if _binance_client is not None:
            _binance_client.close()
            _binance_client = None
            logger.info("BinanceRestClient 单例已重置")


def _fetch_klines_from_api(symbol: str, interval: str, limit: int) -> List[Kline]:
    """从 Binance REST API 获取 K-line 数据（内部函数）
    
    Args:
        symbol: 交易对
        interval: K线周期
        limit: 获取数量
    
    Returns:
        K线数据列表，失败返回空列表
    """
    try:
        client = get_binance_client()
        raw = client.get_klines(symbol, interval, limit)
        if not raw:
            logger.warning(f"未获取到 {symbol} {interval} K-line 数据")
            return []
        return [Kline.from_rest_api(item) for item in raw]
    except Exception as e:
        logger.error(f"从 API 获取 K-line 失败: {e}")
        return []


def fetch_klines(
    symbol: str,
    interval: str,
    limit: int = 50
) -> Tuple[Optional[List[Kline]], Optional[str]]:
    """获取K线数据
    
    统一的 K-line 数据获取入口：
    1. 回测模式：使用注入的 BacktestKlineProvider（从本地缓存获取历史数据切片）
    2. 实盘/模拟盘模式：直接从 Binance REST API 获取
    
    Args:
        symbol: 交易对
        interval: K线周期
        limit: 获取数量
    
    Returns:
        (klines列表, 错误信息)，成功时错误信息为None，失败时klines为None
    """
    try:
        provider = get_kline_provider()
        if provider is not None:
            klines = provider.get_klines(symbol, interval, limit)
        else:
            klines = _fetch_klines_from_api(symbol, interval, limit)
        
        if not klines:
            return None, "未获取到K线数据，请检查 symbol/interval 或稍后重试"
        return klines, None
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return None, f"获取K线数据失败 - {str(e)}"


def get_current_price(symbol: str) -> Optional[float]:
    """获取币种当前价格
    
    统一的价格获取入口，自动适配不同运行模式：
    - 回测模式：使用 BacktestKlineProvider.get_current_price（返回回测周期的收盘价）
    - 实盘/模拟盘模式：从 Binance REST API 获取 1m K线的收盘价
    
    注意：回测模式下返回的是回测周期（如15m）的收盘价，与交易引擎保持一致
    
    Args:
        symbol: 交易对，如 "BTCUSDT"
    
    Returns:
        当前价格，获取失败返回 None
    """
    try:
        provider = get_kline_provider()
        
        if provider is not None and hasattr(provider, 'get_current_price'):
            price = provider.get_current_price(symbol)
            if price is not None:
                return price
        
        klines, error = fetch_klines(symbol, "1m", 1)
        if klines and len(klines) > 0:
            return klines[-1].close
        return None
    except Exception as e:
        logger.error(f"获取 {symbol} 当前价格失败: {e}")
        return None


def format_price(price: float) -> str:
    """根据价格大小自动格式化小数位数
    
    适配不同价格范围的币种显示：
    - 价格 >= 1000: 2位小数（如 BTC）
    - 价格 >= 1: 4位小数（如 ETH）
    - 价格 >= 0.01: 6位小数（如 DOGE）
    - 价格 < 0.01: 8位小数（适配 meme 币）
    
    Args:
        price: 价格
    
    Returns:
        格式化后的价格字符串
    """
    if price >= 1000:
        return f"{price:.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    elif price >= 0.01:
        return f"{price:.6f}"
    else:
        return f"{price:.8f}"
