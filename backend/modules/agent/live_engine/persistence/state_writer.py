"""状态写入器：将引擎状态持久化到 trade_state.json

使用 shared/persistence/JsonStateManager 进行 JSON 读写。
"""
from datetime import datetime, timezone
from typing import Any, Dict, TYPE_CHECKING

from modules.agent.live_engine.core.persistence import JsonStateManager
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.manager import PositionManager

logger = get_logger('live_engine.state_writer')


class StateWriter:
    """状态写入器

    职责：
    - 将账户、记录、订单状态持久化到 trade_state.json
    - 提供同步和异步两种写入方式
    """

    def __init__(self, config: Dict, account_service, position_manager: 'PositionManager'):
        """初始化

        Args:
            config: 配置字典
            account_service: 账户服务
            position_manager: 仓位管理器
        """
        self.config = config
        self.account_service = account_service
        self.position_manager = position_manager

        agent_cfg = config.get('agent', {})
        state_path = agent_cfg.get('trade_state_path', 'agent/trade_state.json')
        self._state_manager = JsonStateManager(state_path)

    def _build_state_data(self) -> Dict[str, Any]:
        """构建状态数据"""
        account_summary = self.account_service.get_summary()

        positions_dict = {}
        for record in self.position_manager.get_open_records():
            tpsl_orders = self.position_manager.tpsl_orders.get(record.symbol, {})

            positions_dict[record.id] = {
                'id': record.id,
                'symbol': record.symbol,
                'side': record.side,
                'qty': record.qty,
                'entry_price': record.entry_price,
                'tp_price': record.tp_price,
                'sl_price': record.sl_price,
                'tp_order_id': record.tp_order_id or tpsl_orders.get('tp_order_id'),
                'tp_algo_id': record.tp_algo_id,
                'sl_algo_id': record.sl_algo_id or tpsl_orders.get('sl_order_id'),
                'open_time': record.open_time,
                'status': record.status.value if hasattr(record.status, 'value') else str(record.status),
                'leverage': record.leverage,
                'notional_usdt': record.notional_usdt,
                'margin_usdt': record.margin_usdt,
                'latest_mark_price': record.latest_mark_price,
                'source': record.source
            }

        return {
            'account': account_summary,
            'positions': positions_dict,
            'last_update': datetime.now(timezone.utc).isoformat()
        }

    def persist(self):
        """持久化当前状态到JSON文件"""
        try:
            state_data = self._build_state_data()
            self._state_manager.save(state_data)
        except Exception as e:
            logger.error(f"持久化状态失败: {e}")

    def persist_sync(self):
        """同步持久化（等待写入完成）"""
        try:
            state_data = self._build_state_data()
            if self._state_manager.save(state_data):
                logger.info("状态已同步持久化")
        except Exception as e:
            logger.error(f"同步持久化失败: {e}")

    def load(self) -> Dict[str, Any]:
        """加载状态"""
        return self._state_manager.load(default={'account': {}, 'positions': {}})
