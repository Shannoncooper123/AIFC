"""持仓汇总服务

基于 RecordService 提供持仓汇总视图。
本地使用 RecordRepository 作为单一数据源，每条交易记录作为独立持仓。
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.services.record_service import RecordService

logger = get_logger('live_engine.position_service')


class PositionService:
    """持仓汇总服务

    职责：
    - 提供持仓汇总查询（基于 RecordService）
    - 兼容旧接口，将调用委托给 RecordService

    注意：
    - 不再从 Binance API 同步持仓（Binance 会合并同方向持仓）
    - 本地每条 TradeRecord 作为独立持仓管理
    """

    def __init__(self, rest_client=None, record_service: 'RecordService' = None):
        """初始化

        Args:
            rest_client: REST API 客户端（保留兼容，暂未使用）
            record_service: 记录服务（主要数据源）
        """
        self.rest_client = rest_client
        self.record_service = record_service

    def get_positions_summary(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取持仓汇总

        直接委托给 RecordService.get_summary()。

        Args:
            source: 来源过滤（可选）

        Returns:
            持仓列表
        """
        if self.record_service:
            return self.record_service.get_summary(source)
        return []

    def get_open_symbols(self, source: Optional[str] = None) -> set:
        """获取当前持仓的交易对集合

        Args:
            source: 来源过滤（可选）

        Returns:
            交易对集合
        """
        if self.record_service:
            records = self.record_service.get_open_records(source)
            return {r.symbol for r in records}
        return set()

    def get_open_positions_count(self, source: Optional[str] = None) -> int:
        """获取当前持仓数量

        Args:
            source: 来源过滤（可选）

        Returns:
            持仓数量
        """
        if self.record_service:
            return len(self.record_service.get_open_records(source))
        return 0
