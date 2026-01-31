"""K线数据获取器 - 负责从Binance API获取K线数据

支持批量获取、自动分页、速率限制处理等功能。
"""
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from modules.config.settings import get_config
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.providers.kline_fetcher')


INTERVAL_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440,
}


def get_interval_minutes(interval: str) -> int:
    """将K线周期转换为分钟数
    
    Args:
        interval: K线周期字符串 (如 "1m", "15m", "1h", "4h")
    
    Returns:
        对应的分钟数
    """
    return INTERVAL_MINUTES.get(interval, 15)


class KlineFetcher:
    """K线数据获取器
    
    从Binance API获取K线数据，支持：
    - 批量获取（自动分页处理）
    - 速率限制处理
    - 自动重试
    """
    
    def __init__(self, client: Optional[BinanceRestClient] = None):
        """初始化获取器
        
        Args:
            client: Binance REST客户端，如果不提供则自动创建
        """
        if client is not None:
            self._client = client
            self._own_client = False
        else:
            cfg = get_config()
            self._client = BinanceRestClient(cfg)
            self._own_client = True
        
        self._request_count = 0
        self._last_request_time = 0.0
        self._min_request_interval = 0.05
    
    def close(self) -> None:
        """关闭获取器（释放资源）"""
        if self._own_client and self._client:
            self._client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def _rate_limit(self) -> None:
        """速率限制控制"""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        
        self._last_request_time = time.time()
        self._request_count += 1
    
    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        include_buffer: bool = True,
        buffer_bars: int = 100
    ) -> List[Kline]:
        """获取指定时间范围的K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
            include_buffer: 是否在开始时间前包含缓冲K线
            buffer_bars: 缓冲K线数量
        
        Returns:
            K线数据列表，按时间升序排列
        """
        symbol = symbol.upper()
        interval_minutes = get_interval_minutes(interval)
        
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        if include_buffer:
            buffer_ms = buffer_bars * interval_minutes * 60 * 1000
            actual_start_ms = start_ms - buffer_ms
        else:
            actual_start_ms = start_ms
        
        logger.debug(f"开始获取K线: {symbol} {interval}, "
                    f"start={datetime.fromtimestamp(actual_start_ms/1000, tz=timezone.utc)}, "
                    f"end={datetime.fromtimestamp(end_ms/1000, tz=timezone.utc)}")
        
        all_klines: List[Kline] = []
        current_start = actual_start_ms
        batch_count = 0
        
        while current_start < end_ms:
            self._rate_limit()
            
            try:
                raw = self._client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=1500,
                    start_time=current_start,
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
                last_close_time_ms = last_kline.timestamp + interval_minutes * 60 * 1000
                current_start = last_close_time_ms + 1
                
                if batch_count % 10 == 0:
                    progress = (current_start - actual_start_ms) / (end_ms - actual_start_ms) * 100
                    logger.info(f"  {symbol} {interval}: 已获取 {len(all_klines)} 根K线 ({progress:.1f}%)")
                    
            except Exception as e:
                logger.error(f"获取K线失败: {symbol} {interval} - {e}")
                raise
        
        seen_times = set()
        unique_klines = []
        for k in all_klines:
            if k.timestamp not in seen_times:
                seen_times.add(k.timestamp)
                unique_klines.append(k)
        
        unique_klines.sort(key=lambda k: k.timestamp)
        
        logger.debug(f"获取完成: {symbol} {interval} - {len(unique_klines)} 根K线 (共 {batch_count} 批)")
        
        return unique_klines
    
    def fetch_klines_for_ranges(
        self,
        symbol: str,
        interval: str,
        ranges: List[Tuple[datetime, datetime]]
    ) -> List[Kline]:
        """获取多个时间范围的K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期
            ranges: 时间范围列表 [(start1, end1), (start2, end2), ...]
        
        Returns:
            合并后的K线数据列表，按时间升序排列
        """
        if not ranges:
            return []
        
        all_klines: List[Kline] = []
        
        for start_time, end_time in ranges:
            klines = self.fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                include_buffer=False
            )
            all_klines.extend(klines)
        
        seen_times = set()
        unique_klines = []
        for k in all_klines:
            if k.timestamp not in seen_times:
                seen_times.add(k.timestamp)
                unique_klines.append(k)
        
        unique_klines.sort(key=lambda k: k.timestamp)
        
        return unique_klines
    
    def fetch_single_kline(
        self,
        symbol: str,
        interval: str,
        target_time: datetime
    ) -> Optional[Kline]:
        """获取指定时间点的单根K线
        
        Args:
            symbol: 交易对
            interval: K线周期
            target_time: 目标时间
        
        Returns:
            对应时间的K线，如果没有则返回None
        """
        symbol = symbol.upper()
        interval_minutes = get_interval_minutes(interval)
        
        target_ms = int(target_time.timestamp() * 1000)
        kline_start_ms = (target_ms // (interval_minutes * 60 * 1000)) * (interval_minutes * 60 * 1000)
        
        self._rate_limit()
        
        try:
            raw = self._client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=1,
                start_time=kline_start_ms
            )
            
            if raw:
                return Kline.from_rest_api(raw[0])
            return None
            
        except Exception as e:
            logger.error(f"获取单根K线失败: {symbol} {interval} {target_time} - {e}")
            return None
    
    @property
    def request_count(self) -> int:
        """获取已发送的请求数量"""
        return self._request_count
