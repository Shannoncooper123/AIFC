"""状态写入器：将引擎状态持久化到 trade_state.json"""
from typing import Dict, Any
import json
import os
from datetime import datetime, timezone
from modules.agent.trade_simulator.utils.file_utils import WriteQueue, TaskType
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.state_writer')


class StateWriter:
    """状态写入器"""
    
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
        
        # 状态文件路径
        agent_cfg = config.get('agent', {})
        self.state_path = agent_cfg.get('trade_state_path', 'agent/trade_state.json')
        self.write_queue = WriteQueue.get_instance()
    
    def persist(self):
        """持久化当前状态到JSON文件"""
        try:
            # 构造状态数据（兼容模拟器格式）
            account_summary = self.account_service.get_summary()
            
            positions_dict = {}
            for symbol, pos in self.position_service.positions.items():
                # 获取该持仓对应的订单 ID
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
            
            state_data = {
                'account': account_summary,
                'positions': positions_dict,
                'last_update': datetime.now(timezone.utc).isoformat()
            }
            
            # 使用 WriteQueue 异步写入
            self.write_queue.enqueue(
                TaskType.STATE,
                self.state_path,
                state_data,
                indent=2,
                ensure_ascii=False
            )
        
        except Exception as e:
            logger.error(f"持久化状态失败: {e}")
    
    def persist_sync(self):
        """同步持久化（等待写入完成）"""
        self.persist()
        # 强制刷新写入队列
        try:
            content = None
            account_summary = self.account_service.get_summary()
            positions_dict = {}
            for symbol, pos in self.position_service.positions.items():
                # 获取该持仓对应的订单 ID
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
            
            state_data = {
                'account': account_summary,
                'positions': positions_dict,
                'last_update': datetime.now(timezone.utc).isoformat()
            }
            
            content = json.dumps(state_data, indent=2, ensure_ascii=False)
            
            # 直接写入（同步）
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info("状态已同步持久化")
        
        except Exception as e:
            logger.error(f"同步持久化失败: {e}")

