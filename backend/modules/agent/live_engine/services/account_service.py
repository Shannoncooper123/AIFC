"""账户服务：管理账户余额和保证金信息"""
from typing import Dict, Any
import threading
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.account_service')


class AccountService:
    """账户服务"""
    
    def __init__(self, rest_client):
        """初始化
        
        Args:
            rest_client: REST API 客户端
        """
        self.rest_client = rest_client
        self._lock = threading.RLock()
        
        # 账户数据
        self.balance = 0.0
        self.available_balance = 0.0
        self.total_margin_balance = 0.0
        self.total_unrealized_pnl = 0.0
        self.total_position_initial_margin = 0.0
    
    def sync_from_api(self):
        """从API同步账户信息"""
        try:
            account_data = self.rest_client.get_account()
            
            with self._lock:
                self.balance = float(account_data.get('totalWalletBalance', 0))
                self.available_balance = float(account_data.get('availableBalance', 0))
                self.total_margin_balance = float(account_data.get('totalMarginBalance', 0))
                self.total_unrealized_pnl = float(account_data.get('totalUnrealizedProfit', 0))
                self.total_position_initial_margin = float(account_data.get('totalPositionInitialMargin', 0))
            
            logger.info(f"账户信息已同步: 余额=${self.balance:.2f}, 未实现盈亏=${self.total_unrealized_pnl:.2f}")
        
        except Exception as e:
            logger.error(f"同步账户信息失败: {e}")
    
    def on_account_update(self, data: Dict[str, Any]):
        """处理 ACCOUNT_UPDATE 事件
        
        Args:
            data: 账户更新事件数据
        """
        try:
            update_data = data.get('a', {})
            
            with self._lock:
                # 更新余额
                balances = update_data.get('B', [])
                for bal in balances:
                    if bal.get('a') == 'USDT':
                        self.balance = float(bal.get('wb', 0))  # 钱包余额
                        self.available_balance = float(bal.get('cw', 0))  # 可用余额
                
                # 更新持仓相关
                positions = update_data.get('P', [])
                total_unrealized = 0.0
                total_margin = 0.0
                
                for pos in positions:
                    unrealized_pnl = float(pos.get('up', 0))
                    initial_margin = float(pos.get('iw', 0))
                    total_unrealized += unrealized_pnl
                    total_margin += initial_margin
                
                self.total_unrealized_pnl = total_unrealized
                self.total_position_initial_margin = total_margin
            
            logger.debug(f"账户更新: 余额=${self.balance:.2f}, 未实现=${self.total_unrealized_pnl:.2f}")
        
        except Exception as e:
            logger.error(f"处理账户更新事件失败: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        """获取账户汇总（兼容模拟器格式）
        
        Returns:
            账户汇总字典
        """
        with self._lock:
            equity = self.balance + self.total_unrealized_pnl
            
            # 计算保证金利用率
            margin_usage_rate = 0.0
            if self.balance > 0:
                margin_usage_rate = (self.total_position_initial_margin / self.balance) * 100
            
            return {
                'balance': round(self.balance, 2),
                'equity': round(equity, 2),
                'unrealized_pnl': round(self.total_unrealized_pnl, 2),
                'realized_pnl': 0.0,  # 实盘不单独跟踪已实现盈亏
                'reserved_margin_sum': round(self.total_position_initial_margin, 2),
                'positions_count': 0,  # 由外部填充
                'margin_usage_rate': round(margin_usage_rate, 2)
            }

