"""内部服务协议定义

定义各服务层之间的接口，实现依赖倒置和解耦。
"""
from typing import Protocol, Dict, List, Optional, Any
from agent.trade_simulator.models import Position


class AccountServiceProtocol(Protocol):
    """账户服务协议"""
    
    def sync_from_api(self) -> None:
        """从API同步账户信息"""
        ...
    
    def get_summary(self) -> Dict[str, Any]:
        """获取账户摘要"""
        ...
    
    def on_account_update(self, data: Dict[str, Any]) -> None:
        """处理账户更新事件"""
        ...


class OrderServiceProtocol(Protocol):
    """订单服务协议"""
    
    tpsl_orders: Dict[str, Dict[str, Optional[int]]]
    
    def sync_tpsl_orders(self) -> None:
        """同步止盈止损订单状态"""
        ...
    
    def open_position_with_tpsl(
        self, symbol: str, side: str, quantity: float,
        leverage: int, tp_price: Optional[float], sl_price: Optional[float]
    ) -> Dict[str, Any]:
        """开仓并设置止盈止损"""
        ...
    
    def close_position_market(
        self, symbol: str, side: str, quantity: float,
        position_obj: Any, close_reason: str
    ) -> Dict[str, Any]:
        """市价平仓"""
        ...
    
    def update_tpsl(
        self, symbol: str, tp_price: Optional[float], sl_price: Optional[float], side: str
    ) -> Dict[str, Any]:
        """更新止盈止损"""
        ...
    
    def get_tpsl_prices(self, symbol: Optional[str] = None) -> Dict[str, Dict[str, Optional[float]]]:
        """获取止盈止损价格"""
        ...


class PositionServiceProtocol(Protocol):
    """持仓服务协议"""
    
    positions: Dict[str, Position]
    
    def sync_from_api(self) -> None:
        """从API同步持仓信息"""
        ...
    
    def get_positions_summary(self, tpsl_orders: Dict) -> List[Dict[str, Any]]:
        """获取持仓汇总"""
        ...


class HistoryWriterProtocol(Protocol):
    """历史记录协议"""
    
    def record_closed_position(
        self, position: Any, close_reason: str, 
        close_price: float, close_order_id: Optional[int]
    ) -> None:
        """记录已平仓的仓位"""
        ...


class CloseDetectorProtocol(Protocol):
    """平仓检测服务协议"""
    
    def detect_and_record_close(self, symbol: str, position: Position) -> None:
        """检测平仓并记录历史"""
        ...

