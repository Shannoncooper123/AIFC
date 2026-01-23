"""持仓服务：管理持仓状态和数据"""
from typing import Dict, List, Optional, Any
import threading
import uuid
from agent.trade_simulator.models import Position
from monitor_module.utils.logger import get_logger

logger = get_logger('live_engine.position_service')


class PositionService:
    """持仓服务
    
    职责：
    - 管理持仓数据（positions 字典）
    - 从 API 同步持仓信息
    - 提供持仓汇总查询
    """
    
    def __init__(self, rest_client):
        """初始化
        
        Args:
            rest_client: REST API 客户端
        """
        self.rest_client = rest_client
        self._lock = threading.RLock()
        
        # 持仓数据：{symbol: Position}
        self.positions: Dict[str, Position] = {}
    
    def sync_from_api(self):
        """从API同步持仓信息"""
        try:
            position_risks = self.rest_client.get_position_risk()
            
            with self._lock:
                active_symbols = set()
                
                for pos_data in position_risks:
                    symbol = pos_data['symbol']
                    position_amt = float(pos_data.get('positionAmt', 0))
                    
                    # 跳过无持仓的
                    if position_amt == 0:
                        continue
                    
                    active_symbols.add(symbol)
                    
                    # 解析持仓信息
                    entry_price = float(pos_data.get('entryPrice', 0))
                    mark_price = float(pos_data.get('markPrice', 0))
                    unrealized_pnl = float(pos_data.get('unRealizedProfit', 0))
                    leverage = int(pos_data.get('leverage', 10))
                    
                    side = 'long' if position_amt > 0 else 'short'
                    qty = abs(position_amt)
                    notional = qty * mark_price
                    margin_used = notional / leverage
                    
                    # 创建或更新 Position 对象
                    if symbol not in self.positions:
                        self.positions[symbol] = Position(
                            id=str(uuid.uuid4()),
                            symbol=symbol,
                            side=side,
                            qty=qty,
                            entry_price=entry_price,
                            leverage=leverage,
                            notional_usdt=notional,
                            margin_used=margin_used,
                            latest_mark_price=mark_price
                        )
                    else:
                        # 更新现有持仓
                        pos = self.positions[symbol]
                        pos.qty = qty
                        pos.entry_price = entry_price
                        pos.latest_mark_price = mark_price
                        pos.notional_usdt = notional
                        pos.margin_used = margin_used
                
                # 移除已平仓的
                closed_symbols = set(self.positions.keys()) - active_symbols
                for symbol in closed_symbols:
                    del self.positions[symbol]
                
                logger.info(f"持仓信息已同步: {len(self.positions)} 个持仓")
        
        except Exception as e:
            logger.error(f"同步持仓信息失败: {e}")
    
    def update_position_from_event(self, pos_data: Dict[str, Any]):
        """从事件数据更新持仓信息
        
        Args:
            pos_data: 持仓数据（来自 ACCOUNT_UPDATE 事件）
        """
        with self._lock:
            symbol = pos_data.get('s')
            position_amt = float(pos_data.get('pa', 0))
            
            # 持仓被平掉
            if position_amt == 0:
                if symbol in self.positions:
                    del self.positions[symbol]
                return
            
            # 更新持仓信息
            entry_price = float(pos_data.get('ep', 0))
            mark_price = float(pos_data.get('mp', 0))
            side = 'long' if position_amt > 0 else 'short'
            qty = abs(position_amt)
            
            if symbol in self.positions:
                pos = self.positions[symbol]
                pos.qty = qty
                pos.entry_price = entry_price
                pos.latest_mark_price = mark_price
            else:
                # 新持仓（可能在别处开的）
                leverage = 10  # 默认杠杆，后续从API获取
                notional = qty * mark_price
                self.positions[symbol] = Position(
                    id=str(uuid.uuid4()),
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    entry_price=entry_price,
                    leverage=leverage,
                    notional_usdt=notional,
                    margin_used=notional / leverage,
                    latest_mark_price=mark_price
                )
    
    def get_positions_summary(self, order_service) -> List[Dict[str, Any]]:
        """获取持仓汇总（兼容模拟器格式）
        
        Args:
            order_service: 订单服务实例（用于获取 TP/SL 价格）
            
        Returns:
            持仓列表
        """
        with self._lock:
            result = []
            # 预先查询所有挂单的 TP/SL 价格
            try:
                prices_map = order_service.get_tpsl_prices()
            except Exception as e:
                logger.warning(f"批量获取 TP/SL 价格失败: {e}")
                prices_map = {}
            
            for symbol, pos in self.positions.items():
                # 基于 Position 对象的默认 TP/SL
                tp_price: Optional[float] = pos.tp_price
                sl_price: Optional[float] = pos.sl_price
                
                # 从订单服务获取真实 TP/SL 触发价
                prices = prices_map.get(symbol, {})
                if prices:
                    if prices.get('tp_price') is not None:
                        tp_price = prices['tp_price']
                    if prices.get('sl_price') is not None:
                        sl_price = prices['sl_price']
                
                unrealized_pnl = pos.unrealized_pnl(pos.latest_mark_price)
                roe = pos.roe(pos.latest_mark_price)
                
                result.append({
                    'symbol': symbol,
                    'side': pos.side,
                    'qty': pos.qty,
                    'entry_price': pos.entry_price,
                    'mark_price': pos.latest_mark_price or pos.entry_price,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'unrealized_pnl': round(unrealized_pnl, 2),
                    'roe': round(roe * 100, 2),
                    'leverage': pos.leverage,
                    'notional_usdt': round(pos.notional_usdt, 2),
                    'opened_at': pos.open_time
                })
            
            return result

