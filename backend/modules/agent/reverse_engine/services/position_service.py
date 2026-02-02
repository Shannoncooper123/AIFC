"""反向交易持仓服务"""

import json
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from modules.monitor.utils.logger import get_logger
from ..models import ReversePosition, ReverseAlgoOrder

logger = get_logger('reverse_engine.position_service')


class ReversePositionService:
    """反向交易持仓服务
    
    管理反向交易的持仓跟踪、TP/SL 订单等
    """
    
    STATE_FILE = 'agent/reverse_trade_state.json'
    
    def __init__(self, rest_client):
        """初始化
        
        Args:
            rest_client: Binance REST 客户端
        """
        self.rest_client = rest_client
        self._lock = threading.RLock()
        
        self.positions: Dict[str, ReversePosition] = {}
        self.tpsl_orders: Dict[str, Dict[str, Optional[int]]] = {}
        
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
                    for symbol, pos_data in data.get('positions', {}).items():
                        self.positions[symbol] = ReversePosition.from_dict(pos_data)
                    self.tpsl_orders = data.get('tpsl_orders', {})
                logger.info(f"[反向] 已加载 {len(self.positions)} 个持仓")
        except Exception as e:
            logger.error(f"[反向] 加载持仓状态失败: {e}")
    
    def _save_state(self):
        """保存状态到文件"""
        try:
            data = {
                'positions': {
                    symbol: pos.to_dict() 
                    for symbol, pos in self.positions.items()
                },
                'tpsl_orders': self.tpsl_orders,
                'updated_at': datetime.now().isoformat()
            }
            with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[反向] 保存持仓状态失败: {e}")
    
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
    
    def create_position_from_algo_order(self, algo_order: ReverseAlgoOrder, 
                                         filled_price: float) -> Optional[ReversePosition]:
        """从条件单创建持仓
        
        Args:
            algo_order: 触发的条件单
            filled_price: 成交价格
            
        Returns:
            创建的持仓对象
        """
        with self._lock:
            try:
                symbol = algo_order.symbol
                
                if symbol in self.positions:
                    logger.warning(f"[反向] {symbol} 已有持仓，跳过创建")
                    return self.positions[symbol]
                
                notional = algo_order.quantity * filled_price
                margin = notional / algo_order.leverage
                
                position = ReversePosition(
                    id=str(uuid.uuid4()),
                    symbol=symbol,
                    side=algo_order.side,
                    qty=algo_order.quantity,
                    entry_price=filled_price,
                    leverage=algo_order.leverage,
                    margin_usdt=margin,
                    notional_usdt=notional,
                    tp_price=algo_order.tp_price,
                    sl_price=algo_order.sl_price,
                    latest_mark_price=filled_price,
                    open_time=datetime.now().isoformat(),
                    algo_order_id=algo_order.algo_id,
                    agent_order_id=algo_order.agent_order_id
                )
                
                self.positions[symbol] = position
                
                self._place_tpsl_orders(position)
                
                self._save_state()
                
                logger.info(f"[反向] 持仓已创建: {symbol} {algo_order.side} "
                           f"qty={algo_order.quantity} entry={filled_price}")
                
                return position
                
            except Exception as e:
                logger.error(f"[反向] 创建持仓失败: {e}", exc_info=True)
                return None
    
    def _place_tpsl_orders(self, position: ReversePosition):
        """为持仓下 TP/SL 订单
        
        Args:
            position: 持仓对象
        """
        try:
            symbol = position.symbol
            price_precision = self._get_price_precision(symbol)
            
            close_side = 'SELL' if position.side.lower() == 'long' or position.side.lower() == 'buy' else 'BUY'
            position_side = 'LONG' if position.side.lower() in ('long', 'buy') else 'SHORT'
            
            tp_order_id = None
            sl_order_id = None
            
            if position.tp_price:
                tp_price_formatted = round(position.tp_price, price_precision)
                tp_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=close_side,
                    order_type='TAKE_PROFIT_MARKET',
                    stop_price=tp_price_formatted,
                    close_position=True,
                    working_type='MARK_PRICE',
                    position_side=position_side
                )
                tp_order_id = tp_order.get('orderId')
                position.tp_order_id = tp_order_id
                logger.info(f"[反向] {symbol} 止盈单已下: price={tp_price_formatted} positionSide={position_side}")
            
            if position.sl_price:
                sl_price_formatted = round(position.sl_price, price_precision)
                sl_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=close_side,
                    order_type='STOP_MARKET',
                    stop_price=sl_price_formatted,
                    close_position=True,
                    working_type='MARK_PRICE',
                    position_side=position_side
                )
                sl_order_id = sl_order.get('orderId')
                position.sl_order_id = sl_order_id
                logger.info(f"[反向] {symbol} 止损单已下: price={sl_price_formatted}")
            
            self.tpsl_orders[symbol] = {
                'tp_order_id': tp_order_id,
                'sl_order_id': sl_order_id
            }
            
        except Exception as e:
            logger.error(f"[反向] 下 TP/SL 订单失败: {e}", exc_info=True)
    
    def remove_position(self, symbol: str) -> Optional[ReversePosition]:
        """移除持仓
        
        Args:
            symbol: 交易对
            
        Returns:
            移除的持仓对象
        """
        with self._lock:
            if symbol in self.positions:
                position = self.positions.pop(symbol)
                self.tpsl_orders.pop(symbol, None)
                self._save_state()
                logger.info(f"[反向] 持仓已移除: {symbol}")
                return position
            return None
    
    def update_mark_price(self, symbol: str, mark_price: float):
        """更新标记价格
        
        Args:
            symbol: 交易对
            mark_price: 标记价格
        """
        with self._lock:
            if symbol in self.positions:
                self.positions[symbol].latest_mark_price = mark_price
    
    def get_position(self, symbol: str) -> Optional[ReversePosition]:
        """获取持仓
        
        Args:
            symbol: 交易对
            
        Returns:
            持仓对象
        """
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[ReversePosition]:
        """获取所有持仓"""
        return list(self.positions.values())
    
    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """获取持仓汇总（用于前端展示）"""
        with self._lock:
            result = []
            for symbol, pos in self.positions.items():
                unrealized_pnl = pos.unrealized_pnl()
                roe = pos.roe()
                
                result.append({
                    'symbol': symbol,
                    'side': pos.side.upper(),
                    'size': pos.qty,
                    'entry_price': pos.entry_price,
                    'mark_price': pos.latest_mark_price or pos.entry_price,
                    'take_profit': pos.tp_price,
                    'stop_loss': pos.sl_price,
                    'unrealized_pnl': round(unrealized_pnl, 2),
                    'roe': round(roe * 100, 2),
                    'leverage': pos.leverage,
                    'margin': round(pos.margin_usdt, 2),
                    'opened_at': pos.open_time,
                    'algo_order_id': pos.algo_order_id,
                    'agent_order_id': pos.agent_order_id
                })
            
            return result
    
    def sync_from_api(self):
        """从 API 同步持仓状态
        
        检测持仓是否被平仓（TP/SL 触发）
        """
        try:
            position_risks = self.rest_client.get_position_risk()
            
            api_positions = {}
            for pos_data in position_risks:
                symbol = pos_data['symbol']
                position_amt = float(pos_data.get('positionAmt', 0))
                if position_amt != 0:
                    api_positions[symbol] = pos_data
            
            with self._lock:
                for symbol in list(self.positions.keys()):
                    if symbol not in api_positions:
                        logger.info(f"[反向] {symbol} 持仓已被平仓（TP/SL 触发）")
                
                for symbol, pos_data in api_positions.items():
                    if symbol in self.positions:
                        pos = self.positions[symbol]
                        pos.latest_mark_price = float(pos_data.get('markPrice', pos.entry_price))
                
                self._save_state()
                
        except Exception as e:
            logger.error(f"[反向] 同步持仓失败: {e}")
    
    def cancel_tpsl_orders(self, symbol: str):
        """撤销指定币种的 TP/SL 订单
        
        Args:
            symbol: 交易对
        """
        if symbol not in self.tpsl_orders:
            return
        
        orders = self.tpsl_orders[symbol]
        
        if orders.get('tp_order_id'):
            try:
                self.rest_client.cancel_order(symbol, order_id=orders['tp_order_id'])
                logger.info(f"[反向] {symbol} 止盈单已撤销")
            except Exception as e:
                logger.warning(f"[反向] 撤销止盈单失败: {e}")
        
        if orders.get('sl_order_id'):
            try:
                self.rest_client.cancel_order(symbol, order_id=orders['sl_order_id'])
                logger.info(f"[反向] {symbol} 止损单已撤销")
            except Exception as e:
                logger.warning(f"[反向] 撤销止损单失败: {e}")
        
        self.tpsl_orders.pop(symbol, None)
