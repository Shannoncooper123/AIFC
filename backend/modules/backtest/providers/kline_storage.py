"""K线本地存储管理器 - 负责K线数据的本地缓存读写

文件结构：
kline_cache_dir/
├── BTCUSDT/
│   ├── 1m.parquet
│   ├── 15m.parquet
│   ├── 1h.parquet
│   └── 4h.parquet
└── ETHUSDT/
    ├── 1m.parquet
    └── ...
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.providers.kline_storage')


class KlineStorage:
    """K线本地存储管理器
    
    使用 Parquet 格式存储K线数据，支持高效的列式压缩和快速读取。
    """
    
    def __init__(self, cache_dir: str):
        """初始化存储管理器
        
        Args:
            cache_dir: K线缓存目录路径
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"K线存储管理器初始化: cache_dir={self.cache_dir}")
    
    def _get_cache_path(self, symbol: str, interval: str) -> Path:
        """获取缓存文件路径
        
        Args:
            symbol: 交易对
            interval: K线周期
        
        Returns:
            缓存文件路径
        """
        symbol_dir = self.cache_dir / symbol.upper()
        symbol_dir.mkdir(parents=True, exist_ok=True)
        return symbol_dir / f"{interval}.parquet"
    
    def get_cached_range(self, symbol: str, interval: str) -> Optional[Tuple[datetime, datetime]]:
        """获取本地缓存的时间范围
        
        Args:
            symbol: 交易对
            interval: K线周期
        
        Returns:
            (开始时间, 结束时间) 元组，如果没有缓存则返回 None
        """
        cache_path = self._get_cache_path(symbol, interval)
        
        if not cache_path.exists():
            return None
        
        try:
            df = pd.read_parquet(cache_path, columns=['timestamp'])
            if df.empty:
                return None
            
            min_ts = df['timestamp'].min()
            max_ts = df['timestamp'].max()
            
            start_time = datetime.fromtimestamp(min_ts / 1000, tz=timezone.utc)
            end_time = datetime.fromtimestamp(max_ts / 1000, tz=timezone.utc)
            
            return (start_time, end_time)
        except Exception as e:
            logger.warning(f"读取缓存范围失败: {symbol} {interval} - {e}")
            return None
    
    def load_klines(self, symbol: str, interval: str,
                    start_time: datetime, end_time: datetime) -> List[Kline]:
        """从本地加载K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            K线数据列表，按时间升序排列
        """
        cache_path = self._get_cache_path(symbol, interval)
        
        if not cache_path.exists():
            return []
        
        try:
            df = pd.read_parquet(cache_path)
            if df.empty:
                return []
            
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)
            
            filtered = df[(df['timestamp'] >= start_ms) & (df['timestamp'] <= end_ms)]
            filtered = filtered.sort_values('timestamp')
            
            klines = []
            for _, row in filtered.iterrows():
                kline = Kline(
                    timestamp=int(row['timestamp']),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']),
                    is_closed=True
                )
                klines.append(kline)
            
            logger.debug(f"从缓存加载K线: {symbol} {interval} - {len(klines)} 根")
            return klines
            
        except Exception as e:
            logger.warning(f"加载缓存失败: {symbol} {interval} - {e}")
            return []
    
    def save_klines(self, symbol: str, interval: str, klines: List[Kline]) -> None:
        """保存K线数据到本地（增量追加，自动去重）
        
        Args:
            symbol: 交易对
            interval: K线周期
            klines: K线数据列表
        """
        if not klines:
            return
        
        cache_path = self._get_cache_path(symbol, interval)
        
        new_data = []
        for k in klines:
            new_data.append({
                'timestamp': k.timestamp,
                'open': k.open,
                'high': k.high,
                'low': k.low,
                'close': k.close,
                'volume': k.volume
            })
        
        new_df = pd.DataFrame(new_data)
        
        try:
            if cache_path.exists():
                existing_df = pd.read_parquet(cache_path)
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                combined_df = new_df
            
            combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='last')
            combined_df = combined_df.sort_values('timestamp')
            
            combined_df.to_parquet(cache_path, index=False, compression='snappy')
            
            logger.info(f"保存K线到缓存: {symbol} {interval} - {len(klines)} 根新数据, "
                       f"总计 {len(combined_df)} 根")
            
        except Exception as e:
            logger.error(f"保存缓存失败: {symbol} {interval} - {e}")
    
    def get_missing_ranges(self, symbol: str, interval: str,
                           start_time: datetime, end_time: datetime,
                           interval_minutes: int) -> List[Tuple[datetime, datetime]]:
        """计算需要从API获取的时间范围
        
        Args:
            symbol: 交易对
            interval: K线周期
            start_time: 需要的开始时间
            end_time: 需要的结束时间
            interval_minutes: K线周期对应的分钟数
        
        Returns:
            缺失的时间范围列表 [(start1, end1), (start2, end2), ...]
        """
        cached_range = self.get_cached_range(symbol, interval)
        
        if cached_range is None:
            return [(start_time, end_time)]
        
        cached_start, cached_end = cached_range
        missing_ranges = []
        
        if start_time < cached_start:
            missing_ranges.append((start_time, cached_start))
        
        if end_time > cached_end:
            missing_ranges.append((cached_end, end_time))
        
        return missing_ranges
    
    def clear_cache(self, symbol: Optional[str] = None, interval: Optional[str] = None) -> None:
        """清除缓存
        
        Args:
            symbol: 交易对（可选，为空则清除所有）
            interval: K线周期（可选，为空则清除该交易对所有周期）
        """
        if symbol is None:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("已清除所有K线缓存")
        elif interval is None:
            symbol_dir = self.cache_dir / symbol.upper()
            if symbol_dir.exists():
                import shutil
                shutil.rmtree(symbol_dir)
            logger.info(f"已清除 {symbol} 的所有K线缓存")
        else:
            cache_path = self._get_cache_path(symbol, interval)
            if cache_path.exists():
                cache_path.unlink()
            logger.info(f"已清除 {symbol} {interval} 的K线缓存")
