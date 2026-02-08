"""币安实盘交易引擎

职责：
- 初始化各服务层
- 协调各层交互
- 对外提供统一接口（符合 EngineProtocol）
- 为其他模块（如 reverse_engine）提供基础设施服务
"""
import threading
import time
from typing import Any, Dict, List, Optional

from app.core.events import emit_mark_price_update
from modules.agent.live_engine.config import get_trading_config_manager
from modules.agent.live_engine.core import ExchangeInfoCache
from modules.agent.live_engine.core.repositories import LinkedOrderRepository
from modules.agent.live_engine.events.account_handler import AccountUpdateHandler
from modules.agent.live_engine.events.algo_order_handler import AlgoOrderHandler
from modules.agent.live_engine.events.dispatcher import EventDispatcher
from modules.agent.live_engine.events.order_handler import OrderUpdateHandler
from modules.agent.live_engine.persistence.history_writer import HistoryWriter
from modules.agent.live_engine.persistence.state_writer import StateWriter
from modules.agent.live_engine.manager import OrderExecutor, OrderManager, PositionManager
from modules.agent.live_engine.services.account_service import AccountService
from modules.agent.live_engine.services.commission_service import CommissionService
from modules.agent.live_engine.services.price_service import PriceService
from modules.agent.live_engine.services.sync_service import SyncService
from modules.agent.live_engine.services.trade_info_service import TradeInfoService
from modules.agent.live_engine.services.trade_service import TradeService
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.clients.binance_ws import BinanceMarkPriceWSClient, BinanceUserDataWSClient
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine')


class BinanceLiveEngine:
    """币安实盘交易引擎（接口兼容 TradeSimulatorEngine）"""

    def __init__(self, config: Dict):
        """初始化

        Args:
            config: 配置字典
        """
        self.config = config
        self._lock = threading.RLock()
        self._running = False
        self._sync_thread = None

        # 初始化 REST 客户端
        self.rest_client = BinanceRestClient(config)

        if not self.rest_client.api_key or not self.rest_client.api_secret:
            raise ValueError(
                "API key is missing. Please set BINANCE_API_KEY and BINANCE_API_SECRET in .env file. "
                f"API Key: {'configured' if self.rest_client.api_key else 'not configured'}, "
                f"API Secret: {'configured' if self.rest_client.api_secret else 'not configured'}"
            )
        logger.info(f"API 密钥已加载: Key长度={len(self.rest_client.api_key)}, Secret长度={len(self.rest_client.api_secret)}")

        ExchangeInfoCache.set_rest_client(self.rest_client)

        self.account_service = AccountService(self.rest_client)

        # 初始化新服务架构
        self.price_service = PriceService(self.rest_client)
        self.order_executor = OrderExecutor(self.rest_client, self.price_service)
        self.trade_info_service = TradeInfoService(self.rest_client)

        self.linked_order_repo = LinkedOrderRepository()

        self.commission_service = CommissionService(
            rest_client=self.rest_client,
            linked_order_repo=self.linked_order_repo
        )

        from modules.agent.live_engine.core import OrderRepository
        self.order_repository = OrderRepository()

        self.position_manager = PositionManager(
            order_executor=self.order_executor,
            config=config,
            price_service=self.price_service,
            rest_client=self.rest_client,
            linked_order_repo=self.linked_order_repo,
            commission_service=self.commission_service
        )

        self.sync_service = SyncService(
            rest_client=self.rest_client,
            price_service=self.price_service,
            trade_info_service=self.trade_info_service,
            position_manager=self.position_manager
        )

        self.history_writer = HistoryWriter(config)
        self.state_writer = StateWriter(config, self.account_service, self.position_manager)

        self.order_manager = OrderManager(
            order_executor=self.order_executor,
            order_repository=self.order_repository
        )

        self.trade_service = TradeService(
            position_manager=self.position_manager,
            order_manager=self.order_manager,
            linked_order_repo=self.linked_order_repo,
            commission_service=self.commission_service
        )

        account_handler = AccountUpdateHandler(
            self.account_service, self.position_manager
        )
        order_handler = OrderUpdateHandler(
            trade_service=self.trade_service,
            order_repository=self.order_repository
        )
        algo_order_handler = AlgoOrderHandler(
            trade_service=self.trade_service,
            order_repository=self.order_repository
        )
        self.algo_order_handler = algo_order_handler
        self.event_dispatcher = EventDispatcher(account_handler, order_handler, algo_order_handler)

        # 用户数据流 WebSocket
        self.user_data_ws: Optional[BinanceUserDataWSClient] = None

        # 标记价格 WebSocket（用于实时推送价格给前端）
        self.mark_price_ws: Optional[BinanceMarkPriceWSClient] = None

        # 持仓模式标记（启动时会设置为双向持仓）
        self._dual_side_position = False

    def start(self):
        """启动引擎"""
        with self._lock:
            if self._running:
                logger.warning("引擎已在运行")
                return

            self._running = True
            logger.info("=" * 60)
            logger.info("实盘交易引擎启动")
            logger.info("=" * 60)

            try:
                # 1. 检查并设置持仓模式为双向持仓（Hedge Mode）
                # 双向持仓模式允许同一币种同时持有多空两个方向的仓位
                # 这对于反向交易功能是必需的
                logger.info("1. 检查持仓模式...")
                try:
                    position_mode = self.rest_client.get_position_mode()
                    dual_side = position_mode.get('dualSidePosition', False)
                    if not dual_side:
                        logger.warning("当前为单向持仓模式，正在切换为双向持仓模式...")
                        self.rest_client.set_position_mode(dual_side=True)
                        logger.info("✅ 已切换为双向持仓模式（Hedge Mode）")
                    else:
                        logger.info("✅ 当前已是双向持仓模式")
                    self._dual_side_position = True
                except Exception as e:
                    logger.error(f"设置持仓模式失败: {e}")
                    logger.warning("将继续启动，但下单可能失败")
                    self._dual_side_position = False

                logger.info("2. 同步账户信息...")
                if not self.account_service.sync_from_api():
                    raise RuntimeError("同步账户信息失败")

                logger.info("3. 同步 TP/SL 订单...")
                self.position_manager.sync_tpsl_orders()

                logger.info("4. 启动用户数据流...")
                self.user_data_ws = BinanceUserDataWSClient(
                    self.config,
                    self.rest_client,
                    self.event_dispatcher.handle_event
                )
                self.user_data_ws.start()

                logger.info("5. 启动标记价格 WebSocket...")
                self.mark_price_ws = BinanceMarkPriceWSClient(
                    on_price_update=emit_mark_price_update
                )
                self.mark_price_ws.start()

                logger.info("6. 持久化初始状态...")
                self.state_writer.persist()

                logger.info("7. 启动定时同步线程...")
                self._sync_thread = threading.Thread(target=self._periodic_sync_loop, daemon=True)
                self._sync_thread.start()

                logger.info("=" * 60)
                logger.info("实盘交易引擎启动完成")
                logger.info(f"账户余额: ${self.account_service.balance:.2f}")
                logger.info(f"持仓数量: {len(self.position_manager.get_open_records())}")
                logger.info("=" * 60)

            except Exception as e:
                logger.error(f"启动引擎失败: {e}", exc_info=True)
                if self.mark_price_ws is not None:
                    try:
                        self.mark_price_ws.stop()
                    except Exception:
                        pass
                    self.mark_price_ws = None
                if self.user_data_ws is not None:
                    try:
                        self.user_data_ws.stop()
                    except Exception:
                        pass
                    self.user_data_ws = None
                self._running = False
                raise

    def _periodic_sync_loop(self):
        """定时同步线程（兜底机制）

        Note:
            - 主要机制是 WebSocket User Data Stream（事件驱动，实时推送）
            - 定时轮询作为兜底，防止 WebSocket 丢失事件或重连期间的状态不一致
            - 间隔10秒足够，因为 WebSocket 会立即处理大部分变化
        """
        sync_interval = 10
        logger.info(f"定时同步线程已启动（兜底机制，间隔={sync_interval}秒）")

        while self._running:
            try:
                time.sleep(sync_interval)

                if not self._running:
                    break

                logger.debug("开始定时同步...")
                self.position_manager.sync_tpsl_orders()
                self.account_service.sync_from_api()

                self.sync_service.sync_tpsl_orders()

                active_symbols = self.position_manager.get_open_symbols()
                cleaned = self.position_manager.cleanup_orphan_orders(active_symbols)
                if cleaned > 0:
                    logger.info(f"定时清理: 已清除 {cleaned} 个币种的孤儿订单")

                # 持久化
                self.state_writer.persist()

                logger.debug("定时同步完成")

            except Exception as e:
                logger.error(f"定时同步失败: {e}", exc_info=True)

        logger.info("定时同步线程已退出")

    def stop(self):
        """停止引擎"""
        with self._lock:
            if not self._running:
                return

            logger.info("正在停止实盘交易引擎...")
            self._running = False

            try:
                # 等待定时同步线程退出
                if self._sync_thread and self._sync_thread.is_alive():
                    logger.info("等待定时同步线程退出...")
                    time.sleep(0.5)

                # 停止用户数据流
                if self.user_data_ws:
                    self.user_data_ws.stop()

                # 停止标记价格 WebSocket
                if self.mark_price_ws:
                    self.mark_price_ws.stop()

                self.state_writer.persist_sync()

                if self.rest_client:
                    self.rest_client.close()

                logger.info("实盘交易引擎已停止")

            except Exception as e:
                logger.error(f"停止引擎时出错: {e}")

    def get_account_summary(self) -> Dict[str, Any]:
        """获取账户汇总"""
        with self._lock:
            summary = self.account_service.get_summary()
            summary['positions_count'] = len(self.position_manager.get_open_records())
            return summary

    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """获取持仓汇总"""
        with self._lock:
            return self.position_manager.get_summary()

    def open_position(self, symbol: str, side: str, quote_notional_usdt: float, leverage: int,
                      tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        """开仓"""
        result = self.position_manager.open_position(symbol, side, quote_notional_usdt, leverage, tp_price, sl_price)
        self.state_writer.persist()
        return result

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        limit_price: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        source: str = 'live',
        agent_side: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建限价单（信号模式）"""
        return self.order_manager.create_limit_order(symbol, side, limit_price, tp_price, sl_price, source, agent_side)

    def close_position(self, position_id: Optional[str] = None, symbol: Optional[str] = None,
                       close_reason: Optional[str] = None, close_price: Optional[float] = None) -> Dict[str, Any]:
        """平仓"""
        with self._lock:
            result = self.position_manager.close_position(position_id, symbol, close_reason)
            self.state_writer.persist()
            return result

    def update_tp_sl(self, symbol: str,
                     tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        """更新止盈止损"""
        with self._lock:
            result = self.position_manager.update_tp_sl(symbol, tp_price, sl_price)
            self.state_writer.persist()
            return result

    def get_trading_config(self) -> Dict[str, Any]:
        """获取交易配置"""
        return get_trading_config_manager().get_dict()

    def update_trading_config(self, **kwargs) -> Dict[str, Any]:
        """更新交易配置"""
        config = get_trading_config_manager().update(**kwargs)
        return config.to_dict()

    def is_reverse_enabled(self) -> bool:
        """检查是否启用反向交易模式"""
        return get_trading_config_manager().reverse_enabled

    def cancel_pending_order(self, order_id: str, source: Optional[str] = None) -> bool:
        """撤销待触发订单"""
        return self.order_manager.cancel_pending_order(order_id, source)

    def close_record(self, record_id: str, source: Optional[str] = None) -> bool:
        """手动关闭指定开仓记录"""
        return self.position_manager.close_record(record_id, source)

    def close_all_records_by_symbol(self, symbol: str, source: Optional[str] = None) -> int:
        """关闭指定交易对的所有开仓记录"""
        return self.position_manager.close_all_by_symbol(symbol, source)

    def get_positions_summary_by_source(self, source: str) -> List[Dict[str, Any]]:
        """获取指定来源的开仓记录汇总"""
        return self.position_manager.get_summary(source=source)

    def get_pending_orders_summary(self, source: Optional[str] = None) -> Dict[str, Any]:
        """获取待触发订单汇总"""
        return self.position_manager.get_pending_orders_summary(self.order_repository, source)

    def get_history_by_source(self, source: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取指定来源的历史记录"""
        return self.position_manager.get_history(source=source, limit=limit)

    def get_statistics_by_source(self, source: str) -> Dict[str, Any]:
        """获取指定来源的统计信息"""
        return self.position_manager.get_statistics(source=source)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取所有来源的历史记录"""
        return self.position_manager.get_history(limit=limit)

    def get_statistics(self) -> Dict[str, Any]:
        """获取所有来源的统计信息"""
        return self.position_manager.get_statistics()
