"""TP/SL 价格监控服务

职责：
- 接收标记价格更新
- 检查每个开仓记录是否触达 TP/SL
- 触发平仓操作（调用 REST API）
- 更新记录状态
"""

import threading
from typing import Dict, Optional, TYPE_CHECKING
from datetime import datetime
from modules.monitor.utils.logger import get_logger
from ..models import TradeRecordStatus

if TYPE_CHECKING:
    from .trade_record_service import TradeRecordService

logger = get_logger('reverse_engine.tpsl_monitor')


class TPSLMonitorService:
    """TP/SL 价格监控服务
    
    功能：
    - 监听标记价格更新
    - 检查每个开仓记录是否触达 TP/SL
    - 自动执行平仓操作
    - 更新记录状态并记录历史
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
        
        self._processing_records: set = set()
        
        self._price_precision_cache: Dict[str, int] = {}
        self._qty_precision_cache: Dict[str, int] = {}
    
    def on_mark_price_update(self, prices: Dict[str, float]):
        """处理标记价格更新
        
        Args:
            prices: {symbol: mark_price} 字典
        """
        open_records = self.trade_record_service.get_open_records()
        
        if not open_records:
            return
        
        for record in open_records:
            price = prices.get(record.symbol)
            if price is None:
                continue
            
            self.trade_record_service.update_mark_price(record.symbol, price)
            
            if record.id in self._processing_records:
                continue
            
            if record.is_tp_triggered(price):
                logger.info(f"[TPSLMonitor] 🎯 触发止盈: {record.symbol} {record.side} "
                           f"price={price} >= TP={record.tp_price}")
                self._execute_close(record, price, 'TP_CLOSED')
                
            elif record.is_sl_triggered(price):
                logger.info(f"[TPSLMonitor] 🛑 触发止损: {record.symbol} {record.side} "
                           f"price={price} <= SL={record.sl_price}")
                self._execute_close(record, price, 'SL_CLOSED')
    
    def _execute_close(self, record, trigger_price: float, close_reason: str):
        """执行平仓操作
        
        Args:
            record: 开仓记录
            trigger_price: 触发价格
            close_reason: 平仓原因
        """
        with self._lock:
            if record.id in self._processing_records:
                return
            self._processing_records.add(record.id)
        
        try:
            close_side = 'SELL' if record.side.upper() in ('LONG', 'BUY') else 'BUY'
            position_side = 'LONG' if record.side.upper() in ('LONG', 'BUY') else 'SHORT'
            
            qty_precision = self._get_qty_precision(record.symbol)
            qty = round(record.qty, qty_precision)
            
            logger.info(f"[TPSLMonitor] 📤 执行平仓: {record.symbol} {close_side} "
                       f"qty={qty} positionSide={position_side}")
            
            order_result = self.rest_client.place_order(
                symbol=record.symbol,
                side=close_side,
                order_type='MARKET',
                quantity=qty,
                position_side=position_side
            )
            
            if order_result and order_result.get('orderId'):
                filled_price = float(order_result.get('avgPrice', trigger_price))
                
                self.trade_record_service.close_record(
                    record_id=record.id,
                    close_price=filled_price,
                    close_reason=close_reason
                )
                
                logger.info(f"[TPSLMonitor] ✅ 平仓成功: {record.symbol} "
                           f"orderId={order_result.get('orderId')} "
                           f"avgPrice={filled_price}")
            else:
                logger.error(f"[TPSLMonitor] ❌ 平仓失败: {record.symbol} "
                            f"result={order_result}")
                
        except Exception as e:
            logger.error(f"[TPSLMonitor] ❌ 平仓异常: {record.symbol} error={e}", exc_info=True)
            
        finally:
            with self._lock:
                self._processing_records.discard(record.id)
    
    def _get_qty_precision(self, symbol: str) -> int:
        """获取交易对的数量精度
        
        Args:
            symbol: 交易对
            
        Returns:
            数量精度
        """
        if symbol in self._qty_precision_cache:
            return self._qty_precision_cache[symbol]
        
        try:
            exchange_info = self.rest_client.get_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s['symbol'] == symbol:
                    precision = s.get('quantityPrecision', 3)
                    self._qty_precision_cache[symbol] = precision
                    return precision
        except Exception as e:
            logger.warning(f"[TPSLMonitor] 获取 {symbol} 数量精度失败: {e}")
        
        return 3
    
    def _get_price_precision(self, symbol: str) -> int:
        """获取交易对的价格精度
        
        Args:
            symbol: 交易对
            
        Returns:
            价格精度
        """
        if symbol in self._price_precision_cache:
            return self._price_precision_cache[symbol]
        
        try:
            exchange_info = self.rest_client.get_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s['symbol'] == symbol:
                    precision = s.get('pricePrecision', 2)
                    self._price_precision_cache[symbol] = precision
                    return precision
        except Exception as e:
            logger.warning(f"[TPSLMonitor] 获取 {symbol} 价格精度失败: {e}")
        
        return 2
    
    def manual_close(self, record_id: str, close_reason: str = 'MANUAL_CLOSED') -> bool:
        """手动关闭指定记录
        
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
            ticker = self.rest_client.get_ticker_price(record.symbol)
            current_price = float(ticker.get('price', record.latest_mark_price or record.entry_price))
        except:
            current_price = record.latest_mark_price or record.entry_price
        
        self._execute_close(record, current_price, close_reason)
        return True
    
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
        
        return {
            'open_records_count': len(open_records),
            'watched_symbols': list(watched_symbols),
            'processing_count': len(self._processing_records)
        }
