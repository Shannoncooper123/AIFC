"""回测K线数据提供者 - 从Binance API预加载历史数据并按时间切片返回"""
import contextvars
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from modules.config.settings import get_config
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.providers.kline')

_current_backtest_time: contextvars.ContextVar[Optional[datetime]] = contextvars.ContextVar(
    'current_backtest_time', default=None
)


def set_backtest_time(t: datetime) -> contextvars.Token:
    """设置当前回测时间（全局，支持 asyncio 上下文传播）
    
    Args:
        t: 当前模拟时间点
    
    Returns:
        Token 用于后续恢复上下文
    """
    return _current_backtest_time.set(t)


def get_backtest_time() -> Optional[datetime]:
    """获取当前回测时间
    
    Returns:
        当前模拟时间点，如果未设置则返回 None
    """
    return _current_backtest_time.get()


def reset_backtest_time(token: contextvars.Token) -> None:
    """重置回测时间到之前的值
    
    Args:
        token: set_backtest_time 返回的 token
    """
    _current_backtest_time.reset(token)


def _get_kline_open_time(kline: Kline) -> datetime:
    """获取K线开盘时间（datetime格式）"""
    return datetime.fromtimestamp(kline.timestamp / 1000, tz=timezone.utc)


def _get_kline_close_time(kline: Kline, interval_minutes: int) -> datetime:
    """获取K线收盘时间（datetime格式）"""
    open_time = datetime.fromtimestamp(kline.timestamp / 1000, tz=timezone.utc)
    return open_time + timedelta(minutes=interval_minutes)


class BacktestKlineProvider:
    """回测K线数据提供者
    
    预加载指定时间范围内的历史K线数据，并根据模拟时间返回对应的数据切片。
    实现 KlineProviderProtocol 接口，可注入到 tool_utils 中替换实盘数据源。
    
    注意：使用 contextvars 来支持并发执行和 asyncio 上下文传播。
    """
    
    def __init__(
        self,
        symbols: List[str],
        start_time: datetime,
        end_time: datetime,
        interval: str = "15m"
    ):
        """初始化回测K线提供者
        
        Args:
            symbols: 需要回测的交易对列表
            start_time: 回测开始时间
            end_time: 回测结束时间
            interval: K线周期，默认15m
        """
        self.symbols = [s.upper() for s in symbols]
        self.start_time = start_time
        self.end_time = end_time
        self.interval = interval
        
        self._default_time = start_time
        
        self._kline_cache: Dict[str, Dict[str, List[Kline]]] = {}
        
        self._load_historical_data()
    
    def _get_interval_minutes(self, interval: str) -> int:
        """将K线周期转换为分钟数"""
        mapping = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440,
        }
        return mapping.get(interval, 15)
    
    def _load_historical_data(self) -> None:
        """从Binance API预加载历史K线数据
        
        支持长时间范围（最多2年）的数据加载，通过分批请求实现。
        """
        total_days = (self.end_time - self.start_time).days
        logger.info(f"开始加载历史K线数据: symbols={self.symbols}, "
                   f"start={self.start_time}, end={self.end_time}, 共 {total_days} 天")
        
        cfg = get_config()
        client = BinanceRestClient(cfg)
        
        start_ms = int(self.start_time.timestamp() * 1000)
        end_ms = int(self.end_time.timestamp() * 1000)
        
        intervals_to_load = ["15m", "1h", "4h", "1d"]
        if self.interval not in intervals_to_load:
            intervals_to_load.append(self.interval)
        
        for symbol in self.symbols:
            self._kline_cache[symbol] = {}
            logger.info(f"加载 {symbol} 的历史数据...")
            
            for interval in intervals_to_load:
                try:
                    all_klines: List[Kline] = []
                    current_start = start_ms
                    interval_minutes = self._get_interval_minutes(interval)
                    buffer_bars = 100
                    buffer_ms = buffer_bars * interval_minutes * 60 * 1000
                    actual_start = current_start - buffer_ms
                    
                    batch_count = 0
                    while current_start < end_ms:
                        raw = client.get_klines(
                            symbol=symbol,
                            interval=interval,
                            limit=1500,
                            start_time=actual_start if current_start == start_ms else current_start,
                            end_time=end_ms
                        )
                        
                        if not raw:
                            break
                        
                        klines = [Kline.from_rest_api(k) for k in raw]
                        all_klines.extend(klines)
                        batch_count += 1
                        
                        if len(raw) < 1500:
                            break
                        
                        last_kline = klines[-1]
                        last_close_time = _get_kline_close_time(last_kline, interval_minutes)
                        current_start = int(last_close_time.timestamp() * 1000) + 1
                        
                        if batch_count % 10 == 0:
                            progress = (current_start - start_ms) / (end_ms - start_ms) * 100
                            logger.info(f"  {symbol} {interval}: 已加载 {len(all_klines)} 根K线 ({progress:.1f}%)")
                    
                    seen_times = set()
                    unique_klines = []
                    for k in all_klines:
                        if k.timestamp not in seen_times:
                            seen_times.add(k.timestamp)
                            unique_klines.append(k)
                    
                    unique_klines.sort(key=lambda k: k.timestamp)
                    self._kline_cache[symbol][interval] = unique_klines
                    
                    logger.info(f"  {symbol} {interval}: 加载完成 - {len(unique_klines)} 根K线 (共 {batch_count} 批)")
                    
                except Exception as e:
                    logger.error(f"加载K线数据失败: {symbol} {interval} - {e}")
                    self._kline_cache[symbol][interval] = []
        
        client.close()
        logger.info("历史K线数据加载完成")
    
    def set_current_time(self, t: datetime) -> None:
        """设置当前模拟时间（使用 contextvars，支持 asyncio）
        
        Args:
            t: 当前模拟时间点
        """
        set_backtest_time(t)
    
    def get_current_time(self) -> datetime:
        """获取当前模拟时间
        
            优先从 LangGraph config 中获取（支持跨线程），
        其次从 contextvars 获取，最后使用默认时间。
        
        Returns:
            当前模拟时间点
        """
        try:
            from langgraph.config import get_config as get_langgraph_config
            config = get_langgraph_config()
            if config:
                configurable = config.get("configurable", {})
                backtest_time_str = configurable.get("backtest_time")
                if backtest_time_str:
                    return datetime.fromisoformat(backtest_time_str)
        except Exception:
            pass
        
        t = get_backtest_time()
        return t if t is not None else self._default_time
    
    def get_klines(self, symbol: str, interval: str, limit: int) -> List[Kline]:
        """获取截止到当前模拟时间的K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期
            limit: 返回数量
        
        Returns:
            K线数据列表，按时间升序排列
        """
        symbol = symbol.upper()
        current_time = self.get_current_time()
        
        if symbol not in self._kline_cache:
            logger.warning(f"未找到 {symbol} 的缓存数据")
            return []
        
        if interval not in self._kline_cache[symbol]:
            logger.warning(f"未找到 {symbol} {interval} 的缓存数据，尝试使用15m")
            interval = "15m"
            if interval not in self._kline_cache[symbol]:
                return []
        
        all_klines = self._kline_cache[symbol][interval]
        interval_minutes = self._get_interval_minutes(interval)
        
        current_time_ms = int(current_time.timestamp() * 1000)
        filtered = [k for k in all_klines 
                   if k.timestamp + interval_minutes * 60 * 1000 <= current_time_ms]
        
        result = filtered[-limit:] if len(filtered) > limit else filtered
        
        return result
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前模拟时间的价格
        
        Args:
            symbol: 交易对
        
        Returns:
            当前收盘价，如果没有数据则返回None
        """
        klines = self.get_klines(symbol, self.interval, 1)
        if klines:
            return klines[-1].close
        return None
    
    def get_kline_at_time(self, symbol: str, interval: str, target_time: datetime) -> Optional[Kline]:
        """获取指定时间点的K线
        
        Args:
            symbol: 交易对
            interval: K线周期
            target_time: 目标时间
        
        Returns:
            对应时间的K线，如果没有则返回None
        """
        symbol = symbol.upper()
        
        if symbol not in self._kline_cache or interval not in self._kline_cache[symbol]:
            return None
        
        all_klines = self._kline_cache[symbol][interval]
        interval_minutes = self._get_interval_minutes(interval)
        target_time_ms = int(target_time.timestamp() * 1000)
        
        for k in all_klines:
            open_time_ms = k.timestamp
            close_time_ms = k.timestamp + interval_minutes * 60 * 1000
            if open_time_ms <= target_time_ms < close_time_ms:
                return k
        
        return None
