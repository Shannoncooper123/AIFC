"""TP/SL 管理服务

职责（v3 - 使用 Binance 条件单）：
- 提供手动平仓功能
- 管理止盈止损条件单的取消
- 不再进行本地价格监控（由 Binance 条件单自动触发）

注意：
- 止盈止损由 Binance 的 TAKE_PROFIT_MARKET 和 STOP_MARKET 条件单管理
- 条件单触发后由 order_handler.py 处理
"""

import threading
from typing import Dict, Optional, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger
from ..models import TradeRecordStatus

if TYPE_CHECKING:
    from .trade_record_service import TradeRecordService

logger = get_logger('reverse_engine.tpsl_monitor')


class TPSLMonitorService:
    """TP/SL 管理服务
    
    功能：
    - 手动平仓功能
    - 取消止盈止损条件单
    - 获取监控状态
    
    注意：
    - 不再进行本地价格监控
    - 止盈止损由 Binance 条件单自动触发
    """
    
    def __init__(self, trade_record_service: 'TradeRecordService', rest_client):
        """初始化
        
        Args:
            trade_record_service: 开仓记录服务
            rest_client: Binance REST 客户端
        """
        self.trade_record_service = trade_record_service
        self.rest_client = rest_client
        self._lock = threading.RLock()
    
    def manual_close(self, record_id: str, close_reason: str = 'MANUAL_CLOSED') -> bool:
        """手动关闭指定记录
        
        会取消关联的止盈止损条件单，然后执行市价平仓。
        
        Args:
            record_id: 记录ID
            close_reason: 关闭原因
            
        Returns:
            是否成功
        """
        record = self.trade_record_service.get_record(record_id)
        if not record:
            logger.warning(f"[TPSLMonitor] 未找到记录: {record_id}")
            return False
        
        if record.status != TradeRecordStatus.OPEN:
            logger.warning(f"[TPSLMonitor] 记录已关闭: {record_id}")
            return False
        
        try:
            if record.tp_algo_id:
                self.rest_client.cancel_algo_order(record.symbol, record.tp_algo_id)
                logger.info(f"[TPSLMonitor] 取消止盈单: {record.symbol} algoId={record.tp_algo_id}")
            
            if record.sl_algo_id:
                self.rest_client.cancel_algo_order(record.symbol, record.sl_algo_id)
                logger.info(f"[TPSLMonitor] 取消止损单: {record.symbol} algoId={record.sl_algo_id}")
        except Exception as e:
            logger.error(f"[TPSLMonitor] 取消条件单失败: {e}")
        
        try:
            current_price = self._get_current_price(record.symbol, record.entry_price)
            
            self._execute_market_close(record, current_price, close_reason)
            return True
            
        except Exception as e:
            logger.error(f"[TPSLMonitor] 手动平仓失败: {record.symbol} error={e}", exc_info=True)
            return False
    
    def _get_current_price(self, symbol: str, fallback_price: float) -> float:
        """获取当前价格"""
        try:
            ticker = self.rest_client.get_ticker_price(symbol)
            return float(ticker.get('price', fallback_price))
        except:
            return fallback_price
    
    def _execute_market_close(self, record, close_price: float, close_reason: str):
        """执行市价平仓
        
        Args:
            record: 开仓记录
            close_price: 平仓价格（预估）
            close_reason: 平仓原因
        """
        close_side = 'BUY' if record.side.upper() in ('SELL', 'SHORT') else 'SELL'
        position_side = 'SHORT' if record.side.upper() in ('SELL', 'SHORT') else 'LONG'
        
        logger.info(f"[TPSLMonitor] 📤 执行市价平仓: {record.symbol} {close_side} "
                   f"qty={record.qty} positionSide={position_side}")
        
        order_result = self.rest_client.place_order(
            symbol=record.symbol,
            side=close_side,
            order_type='MARKET',
            quantity=record.qty,
            position_side=position_side
        )
        
        if order_result and order_result.get('orderId'):
            filled_price = float(order_result.get('avgPrice', close_price))
            
            self.trade_record_service.close_record(
                record_id=record.id,
                close_price=filled_price,
                close_reason=close_reason
            )
            
            logger.info(f"[TPSLMonitor] ✅ 手动平仓成功: {record.symbol} "
                       f"orderId={order_result.get('orderId')} avgPrice={filled_price}")
        else:
            logger.error(f"[TPSLMonitor] ❌ 手动平仓失败: {record.symbol} result={order_result}")
    
    def close_all_by_symbol(self, symbol: str, close_reason: str = 'MANUAL_CLOSED') -> int:
        """关闭指定交易对的所有开仓记录
        
        Args:
            symbol: 交易对
            close_reason: 关闭原因
            
        Returns:
            关闭的记录数量
        """
        records = self.trade_record_service.get_open_records_by_symbol(symbol)
        closed_count = 0
        
        for record in records:
            if self.manual_close(record.id, close_reason):
                closed_count += 1
        
        return closed_count
    
    def get_status(self) -> Dict:
        """获取监控服务状态"""
        open_records = self.trade_record_service.get_open_records()
        watched_symbols = self.trade_record_service.get_watched_symbols()
        
        tp_sl_count = sum(1 for r in open_records if r.tp_algo_id or r.sl_algo_id)
        
        return {
            'open_records_count': len(open_records),
            'watched_symbols': list(watched_symbols),
            'records_with_tp_sl': tp_sl_count,
            'mode': 'binance_algo_orders'
        }
