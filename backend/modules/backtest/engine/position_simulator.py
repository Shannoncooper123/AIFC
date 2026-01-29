"""仓位模拟器 - 负责模拟止盈止损和限价单成交

职责：
- 模拟市价单开仓后的止盈止损
- 模拟限价单成交及后续止盈止损
- 生成交易结果记录
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from modules.backtest.engine.backtest_trade_engine import BacktestTradeEngine
from modules.backtest.models import BacktestConfig, BacktestTradeResult
from modules.backtest.providers.kline_provider import BacktestKlineProvider
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.backtest.engine.position_logger import PositionLogger

logger = get_logger('backtest.position_simulator')


INTERVAL_MINUTES_MAP = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440,
}


def get_interval_minutes(interval: str) -> int:
    """将K线周期转换为分钟数"""
    return INTERVAL_MINUTES_MAP.get(interval, 15)


class PositionSimulator:
    """仓位模拟器
    
    负责模拟仓位的止盈止损触发和限价单成交。
    """
    
    def __init__(
        self,
        config: BacktestConfig,
        kline_provider: BacktestKlineProvider,
        backtest_id: str,
        position_logger: Optional["PositionLogger"] = None,
    ):
        self.config = config
        self.kline_provider = kline_provider
        self.backtest_id = backtest_id
        self._position_logger = position_logger
        self._interval_minutes = get_interval_minutes(config.interval)
        self._step_delta = timedelta(minutes=self._interval_minutes)
    
    def simulate_position_outcome(
        self,
        trade_engine: BacktestTradeEngine,
        symbol: str,
        entry_time: datetime,
        workflow_run_id: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        filled_time: Optional[datetime] = None,
    ) -> Optional[BacktestTradeResult]:
        """模拟仓位的止盈止损结果
        
        Args:
            trade_engine: 回测交易引擎
            symbol: 交易对
            entry_time: 入场时间（对于限价单，这是订单创建时间）
            workflow_run_id: workflow运行ID
            order_type: 订单类型 (market/limit)
            limit_price: 限价单挂单价格（仅限价单有效）
            filled_time: 限价单成交时间（仅限价单有效，市价单为 None）
        
        Returns:
            交易结果，如果没有触发止盈止损则返回 None
        """
        if symbol not in trade_engine.positions:
            return None
        
        pos = trade_engine.positions[symbol]
        if pos.status != 'open':
            return None
        
        saved_pos_data = self._save_position_data(pos)
        
        actual_entry_time = filled_time if filled_time else entry_time
        order_created_time = entry_time if filled_time else None
        
        current_time = actual_entry_time + self._step_delta
        holding_bars = 0
        max_bars = 1000
        
        while current_time <= self.config.end_time and holding_bars < max_bars:
            kline = self.kline_provider.get_kline_at_time(
                symbol, self.config.interval, current_time
            )
            
            if kline:
                holding_bars += 1
                
                result = trade_engine.check_tp_sl(
                    symbol,
                    current_price=kline.close,
                    high_price=kline.high,
                    low_price=kline.low
                )
                
                if result and 'error' not in result:
                    return self._create_trade_result(
                        result=result,
                        saved_data=saved_pos_data,
                        entry_time=actual_entry_time,
                        exit_time=current_time,
                        holding_bars=holding_bars,
                        workflow_run_id=workflow_run_id,
                        order_type=order_type,
                        limit_price=limit_price,
                        order_created_time=order_created_time,
                    )
            
            current_time += self._step_delta
        
        return self._handle_timeout_close(
            trade_engine=trade_engine,
            symbol=symbol,
            saved_data=saved_pos_data,
            entry_time=actual_entry_time,
            holding_bars=holding_bars,
            workflow_run_id=workflow_run_id,
            order_type=order_type,
            limit_price=limit_price,
            order_created_time=order_created_time,
        )
    
    def simulate_limit_order_outcome(
        self,
        trade_engine: BacktestTradeEngine,
        order: Dict[str, Any],
        entry_time: datetime,
        workflow_run_id: str
    ) -> Optional[BacktestTradeResult]:
        """模拟限价单的成交和后续止盈止损
        
        限价单成交后，会继续模拟仓位的止盈止损结果，
        并在交易记录中标记 order_type='limit' 和 limit_price。
        
        Args:
            trade_engine: 回测交易引擎
            order: 限价单信息
            entry_time: 入场时间
            workflow_run_id: workflow运行ID
        
        Returns:
            交易结果，如果限价单未成交则返回 None
        """
        symbol = order['symbol']
        limit_price = order.get('limit_price', 0)
        
        current_time = entry_time + self._step_delta
        max_bars = 1000
        bars_checked = 0
        
        while current_time <= self.config.end_time and bars_checked < max_bars:
            kline = self.kline_provider.get_kline_at_time(
                symbol, self.config.interval, current_time
            )
            
            if kline:
                bars_checked += 1
                
                filled_orders = trade_engine.check_limit_orders(
                    symbol,
                    high_price=kline.high,
                    low_price=kline.low,
                    close_price=kline.close
                )
                
                if filled_orders:
                    for filled in filled_orders:
                        if filled['id'] == order['id']:
                            logger.debug(f"限价单成交: {symbol} @ {filled['filled_price']} (创建于 {entry_time}, 成交于 {current_time})")
                            
                            if symbol in trade_engine.positions and \
                               trade_engine.positions[symbol].status == 'open':
                                return self.simulate_position_outcome(
                                    trade_engine, 
                                    symbol, 
                                    entry_time,
                                    workflow_run_id,
                                    order_type="limit",
                                    limit_price=limit_price,
                                    filled_time=current_time,
                                )
            
            current_time += self._step_delta
        
        pending = trade_engine.get_pending_limit_orders(symbol)
        if pending:
            for p in pending:
                if p['id'] == order['id']:
                    trade_engine.cancel_limit_order(order['id'])
                    logger.debug(f"限价单超时取消: {symbol} order_id={order['id']}")
        
        return None
    
    def _save_position_data(self, pos) -> Dict[str, Any]:
        """保存仓位数据用于后续生成交易记录"""
        original_tp = pos.original_tp_price or pos.tp_price
        original_sl = pos.original_sl_price or pos.sl_price
        
        tp_distance_pct = 0.0
        sl_distance_pct = 0.0
        if pos.entry_price > 0:
            if original_tp:
                tp_distance_pct = abs(original_tp - pos.entry_price) / pos.entry_price * 100
            if original_sl:
                sl_distance_pct = abs(original_sl - pos.entry_price) / pos.entry_price * 100
        
        return {
            "symbol": pos.symbol if hasattr(pos, 'symbol') else "",
            "margin_used": pos.margin_used,
            "notional_usdt": pos.notional_usdt,
            "leverage": pos.leverage,
            "entry_price": pos.entry_price,
            "side": pos.side,
            "qty": pos.qty,
            "fees_open": pos.fees_open,
            "original_tp": original_tp,
            "original_sl": original_sl,
            "tp_distance_pct": tp_distance_pct,
            "sl_distance_pct": sl_distance_pct,
        }
    
    def _create_trade_result(
        self,
        result: Dict[str, Any],
        saved_data: Dict[str, Any],
        entry_time: datetime,
        exit_time: datetime,
        holding_bars: int,
        workflow_run_id: str,
        order_type: str,
        limit_price: Optional[float],
        order_created_time: Optional[datetime] = None,
    ) -> BacktestTradeResult:
        """根据平仓结果创建交易记录
        
        Args:
            order_created_time: 限价单创建时间（仅限价单有效）
        """
        close_reason = result.get('close_reason', '')
        exit_type = "tp" if "止盈" in close_reason else "sl"
        realized_pnl = result.get('realized_pnl', 0)
        exit_price = result.get('close_price', 0)
        
        pnl_percent = (realized_pnl / self.config.initial_balance) * 100
        
        r_multiple = self._calculate_r_multiple(
            saved_data, exit_price, realized_pnl
        )
        
        fees_total = saved_data["fees_open"] + result.get('fees_close', 0)
        
        trade_result = BacktestTradeResult(
            trade_id=f"{self.backtest_id}_{uuid.uuid4().hex[:8]}",
            kline_time=entry_time,
            symbol=saved_data.get("symbol", ""),
            side=saved_data["side"],
            entry_price=saved_data["entry_price"],
            exit_price=exit_price,
            tp_price=saved_data["original_tp"] or 0,
            sl_price=saved_data["original_sl"] or 0,
            size=saved_data["qty"],
            exit_time=exit_time,
            exit_type=exit_type,
            realized_pnl=realized_pnl,
            pnl_percent=pnl_percent,
            holding_bars=holding_bars,
            workflow_run_id=workflow_run_id,
            order_type=order_type,
            margin_usdt=saved_data["margin_used"],
            leverage=saved_data["leverage"],
            notional_usdt=saved_data["notional_usdt"],
            original_tp_price=saved_data["original_tp"],
            original_sl_price=saved_data["original_sl"],
            limit_price=limit_price,
            fees_total=fees_total,
            r_multiple=r_multiple,
            tp_distance_percent=saved_data["tp_distance_pct"],
            sl_distance_percent=saved_data["sl_distance_pct"],
            close_reason=close_reason,
            order_created_time=order_created_time,
        )
        
        if self._position_logger:
            self._position_logger.log_trade_from_result(trade_result)
        
        return trade_result
    
    def _handle_timeout_close(
        self,
        trade_engine: BacktestTradeEngine,
        symbol: str,
        saved_data: Dict[str, Any],
        entry_time: datetime,
        holding_bars: int,
        workflow_run_id: str,
        order_type: str,
        limit_price: Optional[float],
        order_created_time: Optional[datetime] = None,
    ) -> Optional[BacktestTradeResult]:
        """处理回测结束时的强制平仓
        
        Args:
            order_created_time: 限价单创建时间（仅限价单有效）
        """
        if symbol not in trade_engine.positions:
            return None
        if trade_engine.positions[symbol].status != 'open':
            return None
        
        final_kline = self.kline_provider.get_kline_at_time(
            symbol, self.config.interval, self.config.end_time
        )
        if not final_kline:
            return None
        
        close_reason = "回测结束强制平仓"
        close_result = trade_engine.close_position(
            symbol=symbol,
            close_reason=close_reason,
            close_price=final_kline.close
        )
        
        if not close_result or 'error' in close_result:
            return None
        
        realized_pnl = close_result.get('realized_pnl', 0)
        pnl_percent = (realized_pnl / self.config.initial_balance) * 100
        
        r_multiple = self._calculate_r_multiple(
            saved_data, final_kline.close, realized_pnl
        )
        
        fees_total = saved_data["fees_open"] + close_result.get('fees_close', 0)
        
        trade_result = BacktestTradeResult(
            trade_id=f"{self.backtest_id}_{uuid.uuid4().hex[:8]}",
            kline_time=entry_time,
            symbol=symbol,
            side=saved_data["side"],
            entry_price=saved_data["entry_price"],
            exit_price=final_kline.close,
            tp_price=saved_data["original_tp"] or 0,
            sl_price=saved_data["original_sl"] or 0,
            size=saved_data["qty"],
            exit_time=self.config.end_time,
            exit_type="timeout",
            realized_pnl=realized_pnl,
            pnl_percent=pnl_percent,
            holding_bars=holding_bars,
            workflow_run_id=workflow_run_id,
            order_type=order_type,
            margin_usdt=saved_data["margin_used"],
            leverage=saved_data["leverage"],
            notional_usdt=saved_data["notional_usdt"],
            original_tp_price=saved_data["original_tp"],
            original_sl_price=saved_data["original_sl"],
            limit_price=limit_price,
            fees_total=fees_total,
            r_multiple=r_multiple,
            tp_distance_percent=saved_data["tp_distance_pct"],
            sl_distance_percent=saved_data["sl_distance_pct"],
            close_reason=close_reason,
            order_created_time=order_created_time,
        )
        
        if self._position_logger:
            self._position_logger.log_trade_from_result(trade_result)
        
        return trade_result
    
    def _calculate_r_multiple(
        self,
        saved_data: Dict[str, Any],
        exit_price: float,
        realized_pnl: float,
    ) -> Optional[float]:
        """计算 R 值（风险回报比）"""
        original_sl = saved_data["original_sl"]
        entry_price = saved_data["entry_price"]
        
        if not original_sl or entry_price <= 0:
            return None
        
        risk_per_unit = abs(entry_price - original_sl)
        if risk_per_unit <= 0:
            return None
        
        reward_per_unit = abs(exit_price - entry_price)
        r_multiple = reward_per_unit / risk_per_unit
        
        if realized_pnl < 0:
            r_multiple = -r_multiple
        
        return r_multiple
