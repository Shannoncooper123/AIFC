"""账户与风控计算服务"""
from __future__ import annotations
from typing import Dict, Optional

from agent.trade_simulator.models import Position, Account
from agent.trade_simulator.storage import ConfigFacade
from monitor_module.utils.logger import get_logger

logger = get_logger('agent.trade_engine.risk_service')


class RiskService:
    """账户与风控计算服务"""
    def __init__(self, config: Dict, account: Account):
        self.cfg = ConfigFacade(config)
        self.account = account
    
    @staticmethod
    def norm_pct(p: Optional[float]) -> Optional[float]:
        """归一化百分比：支持传入8或0.08（百分数或小数）"""
        if p is None:
            return None
        try:
            p = float(p)
        except Exception:
            return None
        return (p / 100.0) if p > 1 else p
    
    def can_open(self, required_margin: float) -> bool:
        """检查是否有足够保证金开仓"""
        free_bal = self.account.balance - self.account.reserved_margin_sum
        return free_bal >= required_margin
    
    def charge_open_fee(self, notional: float) -> float:
        """收取开仓手续费"""
        fee = notional * self.cfg.taker_fee_rate
        self.account.balance -= fee
        self.account.total_fees += fee  # 累加手续费
        return fee
    
    def charge_close_fee(self, notional: float) -> float:
        """收取平仓手续费"""
        fee = notional * self.cfg.taker_fee_rate
        self.account.balance -= fee
        self.account.total_fees += fee  # 累加手续费
        return fee
    
    def release_margin(self, margin: float) -> None:
        """释放保证金"""
        self.account.reserved_margin_sum -= margin
    
    def mark_account(self, positions: Dict[str, Position]) -> None:
        """标记账户：计算未实现盈亏和权益"""
        unreal = 0.0
        for p in positions.values():
            if p.status == 'open':
                unreal += p.unrealized_pnl()
        self.account.unrealized_pnl = unreal
        self.account.equity = self.account.balance + self.account.unrealized_pnl
        self.account.positions_count = sum(1 for p in positions.values() if p.status == 'open')

