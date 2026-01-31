"""回测交易引擎 - 继承TradeSimulatorEngine，使用独立的状态文件"""
from __future__ import annotations

import copy
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from modules.agent.trade_simulator.engine.simulator import TradeSimulatorEngine
from modules.agent.trade_simulator.models import Account
from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.backtest.providers.kline_provider import BacktestKlineProvider

logger = get_logger('backtest.engine.trade')


class BacktestTradeEngine(TradeSimulatorEngine):
    """回测专用交易引擎
    
    继承自 TradeSimulatorEngine，主要区别：
    1. 使用独立的状态文件路径（按 backtest_id 隔离）
    2. 不启动 WebSocket 订阅（回测不需要实时行情）
    3. 支持设置模拟价格用于开仓/平仓
    """
    
    def __init__(self, config: Dict, backtest_id: str, initial_balance: float = 10000.0):
        """初始化回测交易引擎
        
        Args:
            config: 基础配置
            backtest_id: 回测ID，用于隔离状态文件
            initial_balance: 初始资金
        """
        self.backtest_id = backtest_id
        self._simulated_prices: Dict[str, float] = {}
        
        backtest_config = self._create_backtest_config(config, backtest_id, initial_balance)
        
        super().__init__(backtest_config)
        
        self.account.balance = initial_balance
        self.account.equity = initial_balance
        
        logger.info(f"回测交易引擎初始化完成: backtest_id={backtest_id}, "
                   f"initial_balance={initial_balance}")
    
    def _create_backtest_config(
        self, 
        config: Dict, 
        backtest_id: str,
        initial_balance: float
    ) -> Dict:
        """创建回测专用配置
        
        回测步骤使用内存状态，不创建独立目录，避免产生大量临时目录。
        交易结果通过 PositionLogger 统一记录到主回测目录的 all_positions.jsonl。
        
        Args:
            config: 基础配置
            backtest_id: 回测ID
            initial_balance: 初始资金
        
        Returns:
            修改后的配置，禁用文件持久化
        """
        bt_config = copy.deepcopy(config)
        
        if 'agent' not in bt_config:
            bt_config['agent'] = {}
        
        bt_config['agent']['trade_state_path'] = None
        bt_config['agent']['position_history_path'] = None
        bt_config['agent']['state_path'] = None
        bt_config['agent']['disable_persistence'] = True
        
        if 'simulator' not in bt_config['agent']:
            bt_config['agent']['simulator'] = {}
        bt_config['agent']['simulator']['initial_balance'] = initial_balance
        
        return bt_config
    
    def start(self) -> None:
        """启动引擎 - 回测模式不需要启动WebSocket订阅"""
        self._running = True
        logger.info("回测交易引擎已启动（无WebSocket订阅）")
    
    def stop(self) -> None:
        """停止引擎"""
        self._running = False
        self.state_manager.persist()
        logger.info("回测交易引擎已停止")
    
    def _rebuild_ws(self) -> None:
        """重建WS订阅 - 回测模式不需要"""
        pass
    
    def set_simulated_price(self, symbol: str, price: float) -> None:
        """设置模拟价格
        
        Args:
            symbol: 交易对
            price: 模拟价格
        """
        self._simulated_prices[symbol.upper()] = price
    
    def get_simulated_price(self, symbol: str) -> Optional[float]:
        """获取模拟价格
        
        Args:
            symbol: 交易对
        
        Returns:
            模拟价格，如果未设置则返回None
        """
        return self._simulated_prices.get(symbol.upper())
    
    def update_mark_prices(self, prices: Dict[str, float]) -> None:
        """批量更新标记价格
        
        Args:
            prices: 交易对到价格的映射
        """
        for symbol, price in prices.items():
            self._simulated_prices[symbol.upper()] = price
            
            if symbol.upper() in self.positions:
                pos = self.positions[symbol.upper()]
                if pos.status == 'open':
                    pos.latest_mark_price = price
        
        self.risk_service.mark_account(self.positions)
    
    def open_position(
        self, 
        symbol: str, 
        side: str, 
        quote_notional_usdt: float, 
        leverage: int,
        tp_price: Optional[float] = None, 
        sl_price: Optional[float] = None,
        entry_price: Optional[float] = None,
        pre_reserved_margin: bool = False
    ) -> Dict[str, Any]:
        """开仓
        
        Args:
            symbol: 交易对
            side: 方向（long/short）
            quote_notional_usdt: 名义价值
            leverage: 杠杆倍数
            tp_price: 止盈价
            sl_price: 止损价
            entry_price: 入场价格（回测模式使用模拟价格）
            pre_reserved_margin: 是否预留保证金
        
        Returns:
            开仓结果
        """
        if entry_price is None:
            entry_price = self.get_simulated_price(symbol)
        
        if entry_price is None:
            return {"error": f"无法获取 {symbol} 的价格"}
        
        result = self.position_manager.open_position(
            symbol, side, quote_notional_usdt, leverage,
            tp_price, sl_price, entry_price, pre_reserved_margin
        )
        
        if 'error' not in result:
            self.risk_service.mark_account(self.positions)
            self.state_manager.persist()
        
        return result
    
    def close_position(
        self, 
        position_id: Optional[str] = None, 
        symbol: Optional[str] = None,
        close_reason: Optional[str] = None, 
        close_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """平仓
        
        Args:
            position_id: 持仓ID
            symbol: 交易对
            close_reason: 平仓原因
            close_price: 平仓价格（回测模式使用模拟价格）
        
        Returns:
            平仓结果
        """
        if close_price is None and symbol:
            close_price = self.get_simulated_price(symbol)
        
        result = self.position_manager.close_position(
            position_id, symbol, close_reason, close_price
        )
        
        if 'error' not in result:
            self.risk_service.mark_account(self.positions)
            self.state_manager.persist()
        
        return result
    
    def check_tp_sl(
        self, 
        symbol: str, 
        current_price: float,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
        kline_open_time: Optional[datetime] = None,
        kline_provider: Optional["BacktestKlineProvider"] = None,
    ) -> Optional[Dict[str, Any]]:
        """检查止盈止损是否触发
        
        使用K线的最高价和最低价进行检测，更准确地模拟真实交易中的止盈止损触发。
        如果同一根K线同时触发止盈和止损，使用1分钟K线精确判断哪个先触发。
        
        Args:
            symbol: 交易对
            current_price: 当前价格（K线收盘价，用于平仓价格计算）
            high_price: K线最高价（用于检测止盈/止损触发）
            low_price: K线最低价（用于检测止盈/止损触发）
            kline_open_time: K线开盘时间（用于1分钟精确判断）
            kline_provider: K线数据提供者（用于获取1分钟K线）
        
        Returns:
            如果触发了止盈止损，返回平仓结果；否则返回None
        """
        symbol = symbol.upper()
        
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        if pos.status != 'open':
            return None
        
        if high_price is None:
            high_price = current_price
        if low_price is None:
            low_price = current_price
        
        tp_triggered = False
        sl_triggered = False
        
        if pos.side == 'long':
            if pos.tp_price and high_price >= pos.tp_price:
                tp_triggered = True
            if pos.sl_price and low_price <= pos.sl_price:
                sl_triggered = True
        else:
            if pos.tp_price and low_price <= pos.tp_price:
                tp_triggered = True
            if pos.sl_price and high_price >= pos.sl_price:
                sl_triggered = True
        
        if sl_triggered and tp_triggered:
            first_trigger = self._determine_first_trigger_1m(
                symbol=symbol,
                side=pos.side,
                tp_price=pos.tp_price,
                sl_price=pos.sl_price,
                kline_open_time=kline_open_time,
                kline_provider=kline_provider,
            )
            
            if first_trigger == "tp":
                close_reason = f"止盈触发 (1分钟K线精确判断: TP先触发)"
                close_price = pos.tp_price
                logger.info(f"回测止盈止损同时触发: {symbol} - 1分钟精确判断: TP先触发 (TP={pos.tp_price})")
            else:
                close_reason = f"止损触发 (1分钟K线精确判断: SL先触发)"
                close_price = pos.sl_price
                logger.info(f"回测止盈止损同时触发: {symbol} - 1分钟精确判断: SL先触发 (SL={pos.sl_price})")
        elif sl_triggered:
            close_reason = f"止损触发 (价格触及 SL {pos.sl_price})"
            close_price = pos.sl_price
        elif tp_triggered:
            close_reason = f"止盈触发 (价格触及 TP {pos.tp_price})"
            close_price = pos.tp_price
        else:
            return None
        
        logger.info(f"回测止盈止损触发: {symbol} - {close_reason}")
        return self.close_position(symbol=symbol, close_reason=close_reason, close_price=close_price)
    
    def _determine_first_trigger_1m(
        self,
        symbol: str,
        side: str,
        tp_price: Optional[float],
        sl_price: Optional[float],
        kline_open_time: Optional[datetime],
        kline_provider: Optional["BacktestKlineProvider"],
    ) -> str:
        """使用1分钟K线精确判断TP/SL哪个先触发
        
        Args:
            symbol: 交易对
            side: 持仓方向 (long/short)
            tp_price: 止盈价
            sl_price: 止损价
            kline_open_time: 15分钟K线开盘时间
            kline_provider: K线数据提供者
        
        Returns:
            "tp" 或 "sl"，表示哪个先触发。如果无法判断，默认返回 "sl"（保守原则）
        """
        if kline_open_time is None or kline_provider is None:
            logger.debug(f"{symbol}: 无法获取1分钟K线数据，按止损处理")
            return "sl"
        
        if tp_price is None or sl_price is None:
            return "sl"
        
        kline_close_time = kline_open_time + timedelta(minutes=15)
        
        klines_1m = kline_provider.get_klines_in_range(
            symbol=symbol,
            interval="1m",
            start_time=kline_open_time,
            end_time=kline_close_time,
        )
        
        if not klines_1m:
            logger.debug(f"{symbol}: 1分钟K线数据为空，按止损处理")
            return "sl"
        
        for k in klines_1m:
            tp_hit = False
            sl_hit = False
            
            if side == 'long':
                if k.high >= tp_price:
                    tp_hit = True
                if k.low <= sl_price:
                    sl_hit = True
            else:
                if k.low <= tp_price:
                    tp_hit = True
                if k.high >= sl_price:
                    sl_hit = True
            
            if tp_hit and not sl_hit:
                kline_time = datetime.fromtimestamp(k.timestamp / 1000, tz=timezone.utc)
                logger.debug(f"{symbol}: 1分钟K线 {kline_time} 先触发TP")
                return "tp"
            elif sl_hit and not tp_hit:
                kline_time = datetime.fromtimestamp(k.timestamp / 1000, tz=timezone.utc)
                logger.debug(f"{symbol}: 1分钟K线 {kline_time} 先触发SL")
                return "sl"
            elif tp_hit and sl_hit:
                continue
        
        logger.debug(f"{symbol}: 1分钟K线无法区分TP/SL触发顺序，按止损处理")
        return "sl"
    
    def check_limit_orders(
        self, 
        symbol: str, 
        high_price: float, 
        low_price: float, 
        close_price: float
    ) -> List[Dict[str, Any]]:
        """检查限价单是否触发成交
        
        在回测模式下，手动调用此方法来检测限价单成交。
        
        Args:
            symbol: 交易对
            high_price: K线最高价
            low_price: K线最低价
            close_price: K线收盘价
        
        Returns:
            成交的订单列表
        """
        kline_data = {
            'h': high_price,
            'l': low_price,
            'c': close_price,
        }
        
        filled_orders_before = [
            o for o in self.limit_order_manager.orders.values() 
            if o.status == 'filled'
        ]
        
        self.limit_order_manager.on_kline(symbol, kline_data)
        
        filled_orders_after = [
            o for o in self.limit_order_manager.orders.values() 
            if o.status == 'filled'
        ]
        
        new_filled = [
            self.limit_order_manager._order_to_dict(o) 
            for o in filled_orders_after 
            if o not in filled_orders_before
        ]
        
        if new_filled:
            self.state_manager.persist()
            self.limit_order_manager.persist()
        
        return new_filled
    
    def get_pending_limit_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取待成交的限价单
        
        Args:
            symbol: 可选，筛选特定交易对
        
        Returns:
            待成交订单列表
        """
        pending = self.limit_order_manager.get_pending_orders_summary()
        if symbol:
            pending = [o for o in pending if o['symbol'] == symbol.upper()]
        return pending
    
    def get_backtest_summary(self) -> Dict[str, Any]:
        """获取回测交易汇总
        
        Returns:
            包含账户状态和交易统计的字典
        """
        account_summary = self.get_account_summary()
        positions_summary = self.get_positions_summary()
        pending_orders = self.limit_order_manager.get_pending_orders_summary()
        
        return {
            "backtest_id": self.backtest_id,
            "account": account_summary,
            "open_positions": positions_summary,
            "total_positions": len(self.positions),
            "open_count": len([p for p in self.positions.values() if p.status == 'open']),
            "pending_orders": pending_orders,
            "pending_orders_count": len(pending_orders),
        }
