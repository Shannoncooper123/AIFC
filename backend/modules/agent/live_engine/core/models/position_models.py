"""持仓数据模型

提供简化的持仓模型，用于跟踪当前持仓状态和计算未实现盈亏。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Position:
    """持仓模型

    用于跟踪当前持仓状态，包括入场价格、止盈止损价格等。

    Attributes:
        id: 持仓唯一标识
        symbol: 交易对
        side: 持仓方向（long/short）
        qty: 持仓数量
        entry_price: 入场价格
        tp_price: 止盈价格
        sl_price: 止损价格
        leverage: 杠杆倍数
        notional_usdt: 名义价值（USDT）
        margin_used: 占用保证金
        latest_mark_price: 最新标记价格
        open_time: 开仓时间
    """
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float

    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    leverage: int = 10
    notional_usdt: float = 0.0
    margin_used: float = 0.0
    latest_mark_price: Optional[float] = None
    open_time: str = field(default_factory=lambda: datetime.now().isoformat())

    def unrealized_pnl(self, mark_price: float) -> float:
        """计算未实现盈亏

        Args:
            mark_price: 当前标记价格

        Returns:
            未实现盈亏（USDT）
        """
        if self.side == 'long':
            return (mark_price - self.entry_price) * self.qty
        else:
            return (self.entry_price - mark_price) * self.qty

    def roe(self, mark_price: float) -> float:
        """计算收益率（ROE）

        Args:
            mark_price: 当前标记价格

        Returns:
            收益率（百分比形式，如 0.1 表示 10%）
        """
        if self.margin_used <= 0:
            margin = self.entry_price * self.qty / self.leverage
        else:
            margin = self.margin_used

        if margin <= 0:
            return 0.0

        pnl = self.unrealized_pnl(mark_price)
        return pnl / margin
