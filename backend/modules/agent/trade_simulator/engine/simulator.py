"""实盘模拟引擎（主协调器）"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from modules.agent.trade_simulator.engine.limit_order_manager import LimitOrderManager
from modules.agent.trade_simulator.engine.market_subscription import MarketSubscriptionService
from modules.agent.trade_simulator.engine.position_manager import PositionManager
from modules.agent.trade_simulator.engine.risk_service import RiskService
from modules.agent.trade_simulator.engine.state_manager import StateManager
from modules.agent.trade_simulator.engine.tpsl_manager import TPSLManager
from modules.agent.trade_simulator.models import Account, Position
from modules.agent.trade_simulator.utils.file_utils import WriteQueue
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.trade_engine')


class TradeSimulatorEngine:
    """交易模拟引擎：协调各服务模块"""
    def __init__(self, config: Dict):
        self.config = config
        sim_cfg = config.get('agent', {}).get('simulator', {})

        # 线程锁
        self._lock = threading.RLock()
        self._running = False

        # 核心数据
        self.account = Account(balance=float(sim_cfg.get('initial_balance', 10000.0)))
        self.positions: Dict[str, Position] = {}

        # 初始化各服务
        self.state_manager = StateManager(config, self.account, self.positions)
        self.risk_service = RiskService(config, self.account)
        self.position_manager = PositionManager(
            config, self.account, self.positions,
            self.risk_service, self.state_manager, self._lock
        )
        self.tpsl_manager = TPSLManager(
            config, self.account, self.positions,
            self.risk_service, self.state_manager, self.position_manager, self._lock
        )
        self.limit_order_manager = LimitOrderManager(
            config, self.account, self.positions,
            self.position_manager, self._lock
        )
        self.market_service = MarketSubscriptionService(config, self._on_kline_wrapper)

        # 恢复状态
        self.state_manager.restore()
        self.limit_order_manager.restore()

    def _on_kline_wrapper(self, symbol: str, kline_data: Dict[str, Any]) -> None:
        """K线回调包装器：先检查限价单成交，再检查TP/SL触发，最后更新权益并持久化"""
        # 1. 检查限价单成交
        self.limit_order_manager.on_kline(symbol, kline_data)

        # 2. 检查TP/SL触发
        self.tpsl_manager.on_kline(symbol, kline_data)

        # 3. 更新账户权益并持久化
        with self._lock:
            self.risk_service.mark_account(self.positions)
            self.state_manager.persist()
            self.limit_order_manager.persist()

    def start(self) -> None:
        """启动引擎"""
        with self._lock:
            if self._running:
                return
            self._running = True
            logger.info("TradeSimulatorEngine.start: 引擎启动，准备订阅有持仓和挂单的交易对")
            # 收集持仓和挂单的币种
            position_symbols = [s for s, p in self.positions.items() if p.status == 'open']
            pending_symbols = [
                o.symbol for o in self.limit_order_manager.orders.values()
                if o.status == 'pending'
            ]
            all_symbols = list(set(position_symbols + pending_symbols))
            logger.info(f"订阅币种: 持仓{len(position_symbols)}个, 挂单{len(pending_symbols)}个, 合计{len(all_symbols)}个")
            self.market_service.start(all_symbols)

    def stop(self) -> None:
        """停止引擎（优雅关闭，确保所有数据写入完成）"""
        with self._lock:
            self._running = False
            try:
                # 先停止市场服务
                self.market_service.stop()
                logger.info("TradeSimulatorEngine.stop: 市场服务已停止")

                # 最后一次持久化当前状态
                self.state_manager.persist()
                logger.info("TradeSimulatorEngine.stop: 最后一次状态持久化已提交")

            except Exception as e:
                logger.error(f"TradeSimulatorEngine.stop: 关闭服务失败 - {e}")

        # 优雅关闭写入队列（等待所有写入任务完成）
        try:
            write_queue = WriteQueue.get_instance()
            success = write_queue.shutdown(timeout=5.0)
            if success:
                logger.info("TradeSimulatorEngine.stop: 写入队列已优雅关闭，所有数据已写入")
            else:
                logger.warning("TradeSimulatorEngine.stop: 写入队列关闭超时，可能有数据未完全写入")
        except Exception as e:
            logger.error(f"TradeSimulatorEngine.stop: 关闭写入队列失败 - {e}")

        logger.info("TradeSimulatorEngine.stop: 引擎已完全停止")

    def _rebuild_ws(self) -> None:
        """重建WS订阅（包含持仓和挂单）"""
        position_symbols = [s for s, p in self.positions.items() if p.status == 'open']
        pending_symbols = [
            o.symbol for o in self.limit_order_manager.orders.values()
            if o.status == 'pending'
        ]
        all_symbols = list(set(position_symbols + pending_symbols))
        self.market_service.rebuild(all_symbols)

    def get_account_summary(self) -> Dict[str, Any]:
        """获取账户汇总"""
        with self._lock:
            self.risk_service.mark_account(self.positions)
            summary = self.account.to_dict()

            # 计算保证金利用率
            margin_usage_rate = 0.0
            if summary['balance'] > 0:
                margin_usage_rate = (summary['reserved_margin_sum'] / summary['balance']) * 100

            summary['margin_usage_rate'] = round(margin_usage_rate, 2)
            return summary

    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """获取持仓汇总"""
        return self.position_manager.get_positions_summary()

    def open_position(self, symbol: str, side: str, quote_notional_usdt: float, leverage: int,
                      tp_price: Optional[float] = None, sl_price: Optional[float] = None,
                      entry_price: Optional[float] = None, pre_reserved_margin: bool = False,
                      run_id: Optional[str] = None) -> Dict[str, Any]:
        """开仓
        
        Args:
            symbol: 交易对
            side: 方向（long/short）
            quote_notional_usdt: 名义价值（由工具层传入：保证金 × 杠杆）
            leverage: 杠杆倍数
            tp_price: 止盈价
            sl_price: 止损价
            run_id: workflow run_id（用于关联开仓与workflow trace）
        
        Note:
            为保持与实盘工具调用一致，参数名保持为 quote_notional_usdt（名义价值）
            实际上工具层已经将 margin × leverage 计算完成后传入
        """
        result = self.position_manager.open_position(
            symbol, side, quote_notional_usdt, leverage,
            tp_price, sl_price, entry_price, pre_reserved_margin, run_id
        )

        if 'error' not in result:
            # 成功开仓，重建WS订阅并持久化
            self._rebuild_ws()
            self.risk_service.mark_account(self.positions)
            self.state_manager.persist()

        return result

    def close_position(self, position_id: Optional[str] = None, symbol: Optional[str] = None,
                       close_reason: Optional[str] = None, close_price: Optional[float] = None,
                       run_id: Optional[str] = None) -> Dict[str, Any]:
        """平仓（全平）
        
        Args:
            position_id: 持仓ID（可选）
            symbol: 交易对（可选）
            close_reason: 平仓原因（可选）
            close_price: 指定平仓价格（可选），如果提供则使用此价格，否则使用当前市场价格
            run_id: workflow run_id（Agent主动平仓时传入，止盈止损自动触发时为None）
        """
        result = self.position_manager.close_position(
            position_id, symbol, close_reason, close_price, run_id
        )

        if 'error' not in result:
            # 成功平仓，重建WS订阅并持久化
            self._rebuild_ws()
            self.risk_service.mark_account(self.positions)
            self.state_manager.persist()

        return result

    def update_tp_sl(self, symbol: str,
                     tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        """更新TP/SL（通过交易对）"""
        result = self.tpsl_manager.update_tp_sl(symbol, tp_price, sl_price)

        if 'error' not in result:
            # 成功更新，持久化
            self.state_manager.persist()

        return result

    def create_limit_order(self, symbol: str, side: str, limit_price: float,
                          margin_usdt: float, leverage: int,
                          tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        """创建限价单
        
        Args:
            symbol: 交易对
            side: 方向（long/short）
            limit_price: 挂单价格
            margin_usdt: 保证金金额
            leverage: 杠杆倍数
            tp_price: 止盈价
            sl_price: 止损价
        """
        result = self.limit_order_manager.create_limit_order(
            symbol, side, limit_price, margin_usdt, leverage, tp_price, sl_price
        )

        if 'error' not in result:
            # 成功创建，重建WS订阅并持久化
            self._rebuild_ws()
            self.limit_order_manager.persist()

        return result

    def cancel_limit_order(self, order_id: str) -> Dict[str, Any]:
        """取消单个限价单
        
        Args:
            order_id: 订单ID
        """
        result = self.limit_order_manager.cancel_order(order_id)

        if 'error' not in result:
            # 成功取消，重建WS订阅并持久化
            self._rebuild_ws()
            self.limit_order_manager.persist()

        return result

    def cancel_limit_orders_by_symbol(self, symbol: str) -> Dict[str, Any]:
        """取消指定交易对的所有待成交限价单
        
        Args:
            symbol: 交易对
        """
        result = self.limit_order_manager.cancel_orders_by_symbol(symbol)

        if 'error' not in result and result.get('cancelled_count', 0) > 0:
            # 成功取消，重建WS订阅并持久化
            self._rebuild_ws()
            self.limit_order_manager.persist()

        return result

    def get_pending_orders_summary(self) -> List[Dict[str, Any]]:
        """获取待成交订单摘要"""
        return self.limit_order_manager.get_pending_orders_summary()
