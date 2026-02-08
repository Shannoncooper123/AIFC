"""ACCOUNT_UPDATE 事件处理器"""
from typing import Any, Dict, TYPE_CHECKING

from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.manager import PositionManager

logger = get_logger('live_engine.account_handler')

class AccountUpdateHandler:
    """ACCOUNT_UPDATE 事件处理器

    职责：
    - 处理账户余额更新
    - 检测持仓平仓并更新记录

    注意：
    - 持仓信息现在完全基于 RecordService
    - Binance 的持仓合并不影响本地独立记录
    """

    def __init__(
        self,
        account_service,
        position_manager: 'PositionManager'
    ):
        """初始化

        Args:
            account_service: 账户服务
            position_manager: 仓位管理器
        """
        self.account_service = account_service
        self.position_manager = position_manager

    def handle(self, data: Dict[str, Any]):
        """处理 ACCOUNT_UPDATE 事件

        Args:
            data: 事件数据
        """
        self.account_service.on_account_update(data)
        self._handle_position_updates(data)

    def _handle_position_updates(self, data: Dict[str, Any]):
        """处理持仓更新部分

        检测 Binance 侧的持仓归零事件。
        注意：由于 Binance 会合并同方向持仓，这里的持仓归零
        可能代表多个本地记录的平仓，需要逐个检查。

        Args:
            data: 事件数据
        """
        try:
            update_data = data.get('a', {})
            positions_data = update_data.get('P', [])

            for pos_data in positions_data:
                symbol = pos_data.get('s')
                position_amt = float(pos_data.get('pa', 0))

                if position_amt == 0:
                    records = self.position_manager.get_open_records_by_symbol(symbol)
                    if records:
                        logger.info(f"{symbol} Binance 持仓归零，检测到 {len(records)} 个本地记录待处理")

                    if symbol in self.position_manager.tpsl_orders:
                        del self.position_manager.tpsl_orders[symbol]

            open_count = len(self.position_manager.get_open_records())
            logger.debug(f"持仓更新完成: {open_count} 个活跃记录")

        except Exception as e:
            logger.error(f"处理持仓更新事件失败: {e}")
