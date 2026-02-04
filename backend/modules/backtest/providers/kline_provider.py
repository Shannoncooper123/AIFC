"""回测K线数据提供者 - 支持本地缓存和按时间切片返回"""
import contextvars
import os
import bisect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.config.settings import get_config
from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import get_logger

from .kline_storage import KlineStorage
from .kline_fetcher import KlineFetcher, get_interval_minutes

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
    支持本地缓存，避免重复从API获取数据。
    
    实现 KlineProviderProtocol 接口，可注入到 tool_utils 中替换实盘数据源。
    
    注意：使用 contextvars 来支持并发执行和 asyncio 上下文传播。
    """
    
    def __init__(
        self,
        symbols: List[str],
        start_time: datetime,
        end_time: datetime,
        interval: str = "15m",
        use_cache: bool = True
    ):
        """初始化回测K线提供者
        
        Args:
            symbols: 需要回测的交易对列表
            start_time: 回测开始时间
            end_time: 回测结束时间
            interval: K线周期，默认15m
            use_cache: 是否使用本地缓存，默认True
        """
        self.symbols = [s.upper() for s in symbols]
        
        if 'BTCUSDT' not in self.symbols:
            self.symbols.append('BTCUSDT')
            logger.info("自动添加 BTCUSDT 用于趋势对比分析")
        
        self.start_time = start_time
        self.end_time = end_time
        self.interval = interval
        self.use_cache = use_cache
        
        self._default_time = start_time
        
        self._kline_cache: Dict[str, Dict[str, List[Kline]]] = {}
        self._kline_index: Dict[str, Dict[str, List[int]]] = {}
        
        cfg = get_config()
        cache_dir = cfg.get('backtest', {}).get('kline_cache_dir', 'modules/data/kline_cache')
        
        if not os.path.isabs(cache_dir):
            backend_dir = Path(__file__).parent.parent.parent.parent
            cache_dir = str(backend_dir / cache_dir)
        
        self._storage = KlineStorage(cache_dir) if use_cache else None
        self._fetcher: Optional[KlineFetcher] = None
        
        self._load_historical_data()
    
    def _get_interval_minutes(self, interval: str) -> int:
        """将K线周期转换为分钟数"""
        return get_interval_minutes(interval)
    
    def _ensure_fetcher(self) -> KlineFetcher:
        """确保fetcher已初始化"""
        if self._fetcher is None:
            self._fetcher = KlineFetcher()
        return self._fetcher
    
    def _load_klines_with_cache(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        buffer_bars: int = 100
    ) -> List[Kline]:
        """加载K线数据（优先使用本地缓存）
        
        Args:
            symbol: 交易对
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
            buffer_bars: 缓冲K线数量
        
        Returns:
            K线数据列表
        """
        interval_minutes = self._get_interval_minutes(interval)
        buffer_td = timedelta(minutes=buffer_bars * interval_minutes)
        actual_start = start_time - buffer_td
        
        if not self.use_cache or self._storage is None:
            fetcher = self._ensure_fetcher()
            return fetcher.fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time=actual_start,
                end_time=end_time,
                include_buffer=False
            )
        
        missing_ranges = self._storage.get_missing_ranges(
            symbol=symbol,
            interval=interval,
            start_time=actual_start,
            end_time=end_time,
            interval_minutes=interval_minutes
        )
        
        if missing_ranges:
            logger.info(f"  {symbol} {interval}: 需要从API获取 {len(missing_ranges)} 个时间段")
            fetcher = self._ensure_fetcher()
            
            for range_start, range_end in missing_ranges:
                logger.info(f"    获取: {range_start} -> {range_end}")
                new_klines = fetcher.fetch_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=range_start,
                    end_time=range_end,
                    include_buffer=False
                )
                
                if new_klines:
                    self._storage.save_klines(symbol, interval, new_klines)
        
        klines = self._storage.load_klines(symbol, interval, actual_start, end_time)
        logger.info(f"  {symbol} {interval}: 从缓存加载 {len(klines)} 根K线")
        
        return klines
    
    def _load_historical_data(self) -> None:
        """预加载历史K线数据（支持本地缓存）
        
        支持长时间范围（最多2年）的数据加载。
        优先从本地缓存读取，缺失部分从API获取并保存。
        """
        total_days = (self.end_time - self.start_time).days
        logger.info(f"开始加载历史K线数据: symbols={self.symbols}, "
                   f"start={self.start_time}, end={self.end_time}, 共 {total_days} 天")
        
        if self.use_cache:
            logger.info(f"本地缓存已启用: {self._storage.cache_dir if self._storage else 'N/A'}")
        else:
            logger.info("本地缓存已禁用，将从API获取所有数据")
        
        intervals_to_load = ["1m", "15m", "1h", "4h", "1d"]
        if self.interval not in intervals_to_load:
            intervals_to_load.append(self.interval)
        
        for symbol in self.symbols:
            self._kline_cache[symbol] = {}
            self._kline_index[symbol] = {}
            logger.info(f"加载 {symbol} 的历史数据...")
            
            for interval in intervals_to_load:
                try:
                    klines = self._load_klines_with_cache(
                        symbol=symbol,
                        interval=interval,
                        start_time=self.start_time,
                        end_time=self.end_time,
                        buffer_bars=250
                    )
                    
                    self._kline_cache[symbol][interval] = klines
                    self._kline_index[symbol][interval] = [k.timestamp for k in klines]
                    logger.info(f"  {symbol} {interval}: 加载完成 - {len(klines)} 根K线")
                    
                except Exception as e:
                    logger.error(f"加载K线数据失败: {symbol} {interval} - {e}")
                    self._kline_cache[symbol][interval] = []
                    self._kline_index[symbol][interval] = []
        
        if self._fetcher:
            self._fetcher.close()
            self._fetcher = None
        
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
        all_timestamps = self._kline_index.get(symbol, {}).get(interval, [])
        interval_minutes = self._get_interval_minutes(interval)
        
        current_time_ms = int(current_time.timestamp() * 1000)
        cutoff_ms = current_time_ms - interval_minutes * 60 * 1000
        end_index = bisect.bisect_right(all_timestamps, cutoff_ms)
        if end_index <= 0:
            return []
        start_index = max(0, end_index - limit)
        return all_klines[start_index:end_index]
    
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
        all_timestamps = self._kline_index.get(symbol, {}).get(interval, [])
        interval_minutes = self._get_interval_minutes(interval)
        target_time_ms = int(target_time.timestamp() * 1000)
        index = bisect.bisect_right(all_timestamps, target_time_ms) - 1
        if index < 0:
            return None
        kline = all_klines[index]
        open_time_ms = kline.timestamp
        close_time_ms = open_time_ms + interval_minutes * 60 * 1000
        if open_time_ms <= target_time_ms < close_time_ms:
            return kline
        return None
    
    def get_klines_in_range(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Kline]:
        """获取指定时间范围内的K线数据
        
        用于精确判断TP/SL触发顺序时获取1分钟K线。
        
        Args:
            symbol: 交易对
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            时间范围内的K线数据列表，按时间升序排列
        """
        symbol = symbol.upper()
        
        if symbol not in self._kline_cache or interval not in self._kline_cache[symbol]:
            logger.warning(f"未找到 {symbol} {interval} 的缓存数据")
            return []
        
        all_klines = self._kline_cache[symbol][interval]
        all_timestamps = self._kline_index.get(symbol, {}).get(interval, [])
        
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        start_index = bisect.bisect_left(all_timestamps, start_ms)
        end_index = bisect.bisect_left(all_timestamps, end_ms)
        return all_klines[start_index:end_index]
