"""状态写入器：将引擎状态持久化到 trade_state.json

使用 shared/persistence/JsonStateManager 进行 JSON 读写。
"""
from typing import Dict, Any
from datetime import datetime, timezone
from modules.agent.shared.persistence import JsonStateManager
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.state_writer')


class StateWriter:
    """状态写入器
    
    职责：
    - 将账户、持仓、订单状态持久化到 trade_state.json
    - 提供同步和异步两种写入方式
    """
    
    def __init__(self, config: Dict, account_service, position_service, order_service):
        """初始化
        
        Args:
            config: 配置字典
            account_service: 账户服务
            position_service: 持仓服务
            order_service: 订单服务
        """
        self.config = config
        self.account_service = account_service
        self.position_service = position_service
        self.order_service = order_service
        
        agent_cfg = config.get('agent', {})
        state_path = agent_cfg.get('trade_state_path', 'agent/trade_state.json')
        self._state_manager = JsonStateManager(state_path)
    
    def _build_state_data(self) -> Dict[str, Any]:
        """构建状态数据"""
        account_summary = self.account_service.get_summary()
        
        positions_dict = {}
        for symbol, pos in self.position_service.positions.items():
            tpsl_orders = self.order_service.tpsl_orders.get(symbol, {})
            
            positions_dict[symbol] = {
                'id': pos.id,
                'symbol': pos.symbol,
                'side': pos.side,
                'qty': pos.qty,
                'entry_price': pos.entry_price,
                'tp_price': pos.tp_price,
                'sl_price': pos.sl_price,
                'tp_order_id': tpsl_orders.get('tp_order_id'),
                'sl_order_id': tpsl_orders.get('sl_order_id'),
                'open_time': pos.open_time,
                'status': pos.status,
                'leverage': pos.leverage,
                'notional_usdt': pos.notional_usdt,
                'margin_used': pos.margin_used,
                'latest_mark_price': pos.latest_mark_price,
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
