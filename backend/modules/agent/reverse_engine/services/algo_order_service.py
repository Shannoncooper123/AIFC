"""条件单服务：管理反向交易的条件单"""

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from modules.monitor.utils.logger import get_logger
from ..models import ReverseAlgoOrder, AlgoOrderStatus
from ..config import ConfigManager

logger = get_logger('reverse_engine.algo_order_service')


class AlgoOrderService:
    """条件单服务
    
    管理反向交易的条件单创建、查询、撤销等操作
    """
    
    STATE_FILE = 'agent/reverse_algo_orders.json'
    
    def __init__(self, rest_client, config_manager: ConfigManager):
        """初始化
        
        Args:
            rest_client: Binance REST 客户端
            config_manager: 配置管理器
        """
        self.rest_client = rest_client
        self.config_manager = config_manager
        self._lock = threading.RLock()
        
        self.pending_orders: Dict[str, ReverseAlgoOrder] = {}
        self._dual_mode_checked = False
        self._symbol_leverage_set: set = set()
        
        self._ensure_state_dir()
        self._load_state()
    
    def _ensure_state_dir(self):
        """确保状态目录存在"""
        state_dir = os.path.dirname(self.STATE_FILE)
        if state_dir and not os.path.exists(state_dir):
            os.makedirs(state_dir, exist_ok=True)
    
    def _load_state(self):
        """从文件加载状态"""
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for algo_id, order_data in data.get('pending_orders', {}).items():
                        self.pending_orders[algo_id] = ReverseAlgoOrder.from_dict(order_data)
                logger.info(f"已加载 {len(self.pending_orders)} 个待触发条件单")
        except Exception as e:
            logger.error(f"加载条件单状态失败: {e}")
    
    def _save_state(self):
        """保存状态到文件"""
        try:
            data = {
                'pending_orders': {
                    algo_id: order.to_dict() 
                    for algo_id, order in self.pending_orders.items()
                },
                'updated_at': datetime.now().isoformat()
            }
            with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存条件单状态失败: {e}")
    
    def _get_quantity_precision(self, symbol: str) -> int:
        """获取交易对的数量精度"""
        try:
            exchange_info = self.rest_client.get_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s['symbol'] == symbol:
                    return s.get('quantityPrecision', 3)
            return 3
        except Exception as e:
            logger.warning(f"获取 {symbol} 数量精度失败，使用默认值3: {e}")
            return 3
    
    def _get_price_precision(self, symbol: str) -> int:
        """获取交易对的价格精度"""
        try:
            exchange_info = self.rest_client.get_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s['symbol'] == symbol:
                    return s.get('pricePrecision', 2)
            return 2
        except Exception as e:
            logger.warning(f"获取 {symbol} 价格精度失败，使用默认值2: {e}")
            return 2
    
    def _ensure_dual_position_mode(self):
        """确保账户为双向持仓模式
        
        双向持仓模式允许同时持有多头和空头仓位，这对于反向交易是必需的。
        只在第一次交易时检查一次。
        """
        if self._dual_mode_checked:
            return
        
        try:
            mode_info = self.rest_client.get_position_mode()
            is_dual = mode_info.get('dualSidePosition', False)
            
            if not is_dual:
                logger.info("[反向] 当前为单向持仓模式，尝试切换为双向持仓模式...")
                try:
                    self.rest_client.change_position_mode(dual_side_position=True)
                    logger.info("[反向] 已成功切换为双向持仓模式")
                except Exception as e:
                    error_msg = str(e)
                    if 'No need to change position side' in error_msg or '-4059' in error_msg:
                        logger.info("[反向] 已经是双向持仓模式，无需切换")
                    elif 'position or open order' in error_msg.lower() or '-4068' in error_msg:
                        logger.warning("[反向] 无法切换持仓模式：存在持仓或挂单。请手动在 Binance 切换为双向持仓模式")
                    else:
                        logger.error(f"[反向] 切换持仓模式失败: {e}")
            else:
                logger.info("[反向] 已确认为双向持仓模式")
            
            self._dual_mode_checked = True
            
        except Exception as e:
            logger.error(f"[反向] 检查持仓模式失败: {e}")
    
    def _ensure_symbol_leverage(self, symbol: str, leverage: int):
        """确保指定币种的杠杆已设置
        
        每个币种只设置一次杠杆，避免重复 API 调用
        
        Args:
            symbol: 交易对
            leverage: 杠杆倍数
        """
        if symbol in self._symbol_leverage_set:
            return
        
        try:
            self.rest_client.set_leverage(symbol, leverage)
            logger.info(f"[反向] {symbol} 杠杆已设置为 {leverage}x")
            self._symbol_leverage_set.add(symbol)
        except Exception as e:
            error_msg = str(e)
            if 'No need to change leverage' in error_msg or '-4028' in error_msg:
                logger.debug(f"[反向] {symbol} 杠杆已经是 {leverage}x，无需修改")
                self._symbol_leverage_set.add(symbol)
            else:
                logger.warning(f"[反向] 设置 {symbol} 杠杆失败: {e}")
    
    def create_conditional_order(self, symbol: str, side: str, trigger_price: float,
                                  tp_price: float, sl_price: float,
                                  agent_order_id: Optional[str] = None,
                                  agent_side: Optional[str] = None) -> Optional[ReverseAlgoOrder]:
        """创建条件单
        
        使用固定配置的保证金和杠杆，不跟随 Agent 参数
        
        Args:
            symbol: 交易对
            side: 方向（BUY/SELL）
            trigger_price: 触发价格（Agent 的限价）
            tp_price: 止盈价（反转后的，即 Agent 的止损）
            sl_price: 止损价（反转后的，即 Agent 的止盈）
            agent_order_id: Agent 订单ID（用于关联）
            agent_side: Agent 原始方向
            
        Returns:
            创建的条件单对象，失败返回 None
        """
        with self._lock:
            try:
                fixed_margin = self.config_manager.fixed_margin_usdt
                fixed_leverage = self.config_manager.fixed_leverage
                expiration_days = self.config_manager.expiration_days
                
                self._ensure_dual_position_mode()
                
                self._ensure_symbol_leverage(symbol, fixed_leverage)
                
                notional = fixed_margin * fixed_leverage
                quantity = notional / trigger_price
                
                qty_precision = self._get_quantity_precision(symbol)
                price_precision = self._get_price_precision(symbol)
                quantity = round(quantity, qty_precision)
                trigger_price_formatted = round(trigger_price, price_precision)
                
                expiration_ms = int((datetime.now() + timedelta(days=expiration_days)).timestamp() * 1000)
                
                position_side = 'LONG' if side.upper() == 'BUY' else 'SHORT'
                
                logger.info(f"[反向] 创建条件单: {symbol} {side} ({position_side}) "
                           f"trigger={trigger_price_formatted} qty={quantity} "
                           f"margin={fixed_margin}U leverage={fixed_leverage}x "
                           f"expires_in={expiration_days}days")
                
                result = self.rest_client.place_algo_order(
                    symbol=symbol,
                    side=side,
                    algo_type='CONDITIONAL',
                    trigger_price=trigger_price_formatted,
                    quantity=quantity,
                    order_type='STOP_MARKET',
                    working_type='CONTRACT_PRICE',
                    good_till_date=expiration_ms,
                    position_side=position_side
                )
                
                algo_id = str(result.get('algoId'))
                
                order = ReverseAlgoOrder(
                    algo_id=algo_id,
                    symbol=symbol,
                    side=side.lower(),
                    trigger_price=trigger_price_formatted,
                    quantity=quantity,
                    status=AlgoOrderStatus.NEW,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    leverage=fixed_leverage,
                    margin_usdt=fixed_margin,
                    agent_order_id=agent_order_id,
                    agent_limit_price=trigger_price,
                    agent_side=agent_side,
                    created_at=datetime.now().isoformat(),
                    expires_at=datetime.fromtimestamp(expiration_ms / 1000).isoformat()
                )
                
                self.pending_orders[algo_id] = order
                self._save_state()
                
                logger.info(f"[反向] ✅ 条件单创建成功: algoId={algo_id}")
                logger.info(f"[反向]    - Symbol: {symbol}")
                logger.info(f"[反向]    - Side: {side} ({position_side})")
                logger.info(f"[反向]    - Trigger: {trigger_price_formatted}")
                logger.info(f"[反向]    - TP: {tp_price} | SL: {sl_price}")
                logger.info(f"[反向]    - Qty: {quantity} | Margin: {fixed_margin}U | Leverage: {fixed_leverage}x")
                return order
                
            except Exception as e:
                logger.error(f"[反向] 创建条件单失败: {e}", exc_info=True)
                return None
    
    def cancel_order(self, algo_id: str) -> bool:
        """撤销条件单
        
        Args:
            algo_id: 条件单ID
            
        Returns:
            是否成功
        """
        with self._lock:
            try:
                self.rest_client.cancel_algo_order(int(algo_id))
                
                if algo_id in self.pending_orders:
                    self.pending_orders[algo_id].status = AlgoOrderStatus.CANCELLED
                    del self.pending_orders[algo_id]
                    self._save_state()
                
                logger.info(f"[反向] 条件单已撤销: algoId={algo_id}")
                return True
                
            except Exception as e:
                logger.error(f"[反向] 撤销条件单失败: {e}")
                return False
    
    def get_order(self, algo_id: str) -> Optional[ReverseAlgoOrder]:
        """获取条件单
        
        Args:
            algo_id: 条件单ID
            
        Returns:
            条件单对象
        """
        return self.pending_orders.get(algo_id)
    
    def get_pending_orders(self) -> List[ReverseAlgoOrder]:
        """获取所有待触发条件单"""
        return list(self.pending_orders.values())
    
    def mark_order_triggered(self, algo_id: str, filled_price: Optional[float] = None):
        """标记条件单已触发
        
        Args:
            algo_id: 条件单ID
            filled_price: 成交价格
        """
        with self._lock:
            if algo_id in self.pending_orders:
                order = self.pending_orders[algo_id]
                order.status = AlgoOrderStatus.FILLED
                order.triggered_at = datetime.now().isoformat()
                order.filled_at = datetime.now().isoformat()
                order.filled_price = filled_price
                self._save_state()
                logger.info(f"[反向] 条件单已触发: algoId={algo_id} price={filled_price}")
    
    def remove_order(self, algo_id: str):
        """移除条件单（触发后或过期后）
        
        Args:
            algo_id: 条件单ID
        """
        with self._lock:
            if algo_id in self.pending_orders:
                del self.pending_orders[algo_id]
                self._save_state()
    
    def sync_from_api(self):
        """从 API 同步条件单状态"""
        try:
            api_orders = self.rest_client.get_algo_open_orders()
            api_order_ids = {str(o.get('algoId')) for o in api_orders}
            
            with self._lock:
                for algo_id in list(self.pending_orders.keys()):
                    if algo_id not in api_order_ids:
                        order = self.pending_orders[algo_id]
                        if order.status == AlgoOrderStatus.NEW:
                            logger.info(f"[反向] 条件单 {algo_id} 已不在API中，可能已触发或过期")
                
                self._save_state()
                
            logger.debug(f"[反向] 条件单同步完成: API={len(api_orders)}, 本地={len(self.pending_orders)}")
            
        except Exception as e:
            logger.error(f"[反向] 同步条件单失败: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        """获取条件单汇总"""
        with self._lock:
            return {
                'total': len(self.pending_orders),
                'orders': [o.to_dict() for o in self.pending_orders.values()]
            }
