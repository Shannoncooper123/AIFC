"""ACCOUNT_UPDATE 事件处理器"""
from typing import Dict, Any
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.account_handler')


class AccountUpdateHandler:
    """ACCOUNT_UPDATE 事件处理器
    
    职责：
    - 处理账户余额更新
    - 处理持仓状态更新
    - 检测持仓平仓并触发记录
    """
    
    def __init__(self, account_service, position_service, order_service, close_detector):
        """初始化
        
        Args:
            account_service: 账户服务
            position_service: 持仓服务
            order_service: 订单服务
            close_detector: 平仓检测服务
        """
        self.account_service = account_service
        self.position_service = position_service
        self.order_service = order_service
        self.close_detector = close_detector
    
    def handle(self, data: Dict[str, Any]):
        """处理 ACCOUNT_UPDATE 事件
        
        Args:
            data: 事件数据
        """
        # 账户服务处理余额更新
        self.account_service.on_account_update(data)
        
        # 处理持仓更新
        self._handle_position_updates(data)
    
    def _handle_position_updates(self, data: Dict[str, Any]):
        """处理持仓更新部分
        
        Args:
            data: 事件数据
        """
        try:
            update_data = data.get('a', {})
            positions_data = update_data.get('P', [])
            
            for pos_data in positions_data:
                symbol = pos_data.get('s')
                position_amt = float(pos_data.get('pa', 0))
                
                # 持仓被平掉
                if position_amt == 0:
                    if symbol in self.position_service.positions:
                        position = self.position_service.positions[symbol]
                        logger.info(f"{symbol} 持仓已平仓（ACCOUNT_UPDATE）")
                        
                        # 触发平仓检测和记录
                        if symbol in self.order_service.tpsl_orders:
                            self.close_detector.detect_and_record_close(symbol, position)
                        
                        # 清除本地持仓记录
                        del self.position_service.positions[symbol]
                        
                        # 清除订单记录
                        if symbol in self.order_service.tpsl_orders:
                            del self.order_service.tpsl_orders[symbol]
                    continue
                
                # 更新持仓信息
                self.position_service.update_position_from_event(pos_data)
            
            logger.debug(f"持仓更新完成: {len(self.position_service.positions)} 个持仓")
        
        except Exception as e:
            logger.error(f"处理持仓更新事件失败: {e}")

