"""K线数据缓存管理"""
from collections import deque
from typing import Dict, List, Optional
from .models import Kline


class KlineManager:
    """K线数据管理器"""
    
    def __init__(self, history_size: int = 30):
        """初始化
        
        Args:
            history_size: 保留的历史K线数量
        """
        self.history_size = history_size
        self._klines: Dict[str, deque] = {}  # symbol -> deque of Kline
        self._realtime_low: Dict[str, float] = {}  # 实时跟踪当前K线最低价
    
    def update(self, symbol: str, kline: Kline):
        """更新K线数据
        
        Args:
            symbol: 交易对符号
            kline: K线数据
        """
        if symbol not in self._klines:
            self._klines[symbol] = deque(maxlen=self.history_size)
        
        klines = self._klines[symbol]
        
        # 检查是否与最后一根K线时间戳相同
        if len(klines) > 0 and klines[-1].timestamp == kline.timestamp:
            # 同一根K线的更新，替换
            klines[-1] = kline
        else:
            # 新K线，添加
            klines.append(kline)
    
    def get_klines(self, symbol: str, count: Optional[int] = None) -> List[Kline]:
        """获取K线数据
        
        Args:
            symbol: 交易对符号
            count: 获取数量（None表示全部）
            
        Returns:
            K线列表
        """
        if symbol not in self._klines:
            return []
        
        klines = list(self._klines[symbol])
        if count is None:
            return klines
        return klines[-count:]
    
    def get_latest_kline(self, symbol: str) -> Optional[Kline]:
        """获取最新的K线
        
        Args:
            symbol: 交易对符号
            
        Returns:
            最新K线，如果不存在返回None
        """
        if symbol not in self._klines or len(self._klines[symbol]) == 0:
            return None
        return self._klines[symbol][-1]
    
    def has_enough_data(self, symbol: str, required_count: int) -> bool:
        """检查是否有足够的数据
        
        Args:
            symbol: 交易对符号
            required_count: 需要的数据量
            
        Returns:
            是否有足够数据
        """
        return symbol in self._klines and len(self._klines[symbol]) >= required_count
    
    def get_closes(self, symbol: str, count: Optional[int] = None) -> List[float]:
        """获取收盘价列表
        
        Args:
            symbol: 交易对符号
            count: 获取数量
            
        Returns:
            收盘价列表
        """
        klines = self.get_klines(symbol, count)
        return [k.close for k in klines]
    
    def get_volumes(self, symbol: str, count: Optional[int] = None) -> List[float]:
        """获取成交量列表
        
        Args:
            symbol: 交易对符号
            count: 获取数量
            
        Returns:
            成交量列表
        """
        klines = self.get_klines(symbol, count)
        return [k.volume for k in klines]
    
    def initialize_symbol(self, symbol: str, klines: List[Kline]):
        """初始化交易对的历史数据
        
        Args:
            symbol: 交易对符号
            klines: 历史K线列表
        """
        self._klines[symbol] = deque(klines[-self.history_size:], maxlen=self.history_size)
    
    def get_symbol_count(self) -> int:
        """获取管理的交易对数量"""
        return len(self._klines)
    
    def clear(self, symbol: Optional[str] = None):
        """清空数据
        
        Args:
            symbol: 交易对符号（None表示清空所有）
        """
        if symbol:
            if symbol in self._klines:
                del self._klines[symbol]
        else:
            self._klines.clear()
    
    def update_realtime_low(self, symbol: str, low: float):
        """更新实时K线的最低价
        
        Args:
            symbol: 交易对符号
            low: 当前K线最低价
        """
        self._realtime_low[symbol] = low
    
    def get_realtime_low(self, symbol: str) -> Optional[float]:
        """获取实时K线的最低价
        
        Args:
            symbol: 交易对符号
            
        Returns:
            实时最低价，如果不存在返回None
        """
        return self._realtime_low.get(symbol)
    
    def clear_realtime_low(self, symbol: str):
        """清除实时最低价（K线收盘时调用）
        
        Args:
            symbol: 交易对符号
        """
        if symbol in self._realtime_low:
            del self._realtime_low[symbol]

