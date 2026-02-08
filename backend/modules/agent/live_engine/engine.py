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
from modules.agent.live_engine.services.account_service import AccountService
from modules.agent.live_engine.services.close_detector import CloseDetectorService
from modules.agent.live_engine.services.commission_service import CommissionService
from modules.agent.live_engine.services.order_manager import OrderManager
from modules.agent.live_engine.services.order_service import OrderService
from modules.agent.live_engine.services.position_service import PositionService
from modules.agent.live_engine.services.record_service import RecordService
from modules.agent.live_engine.sync import SyncManager
from modules.agent.live_engine.sync.order_sync_service import OrderSyncService
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
        self.order_service = OrderService(self.rest_client, config)
        self.order_manager = OrderManager(self.rest_client)

        self.linked_order_repo = LinkedOrderRepository()

        self.commission_service = CommissionService(
            rest_client=self.rest_client,
            linked_order_repo=self.linked_order_repo
        )

        self.record_service = RecordService(
            rest_client=self.rest_client,
            order_manager=self.order_manager,
            linked_order_repo=self.linked_order_repo,
            commission_service=self.commission_service
        )

        self.order_sync_service = OrderSyncService(
            rest_client=self.rest_client,
            linked_order_repo=self.linked_order_repo,
            commission_service=self.commission_service,
            record_service=self.record_service
        )

        self.sync_manager = SyncManager(
            rest_client=self.rest_client,
            record_service=self.record_service
        )

        self.position_service = PositionService(
            rest_client=self.rest_client,
            record_service=self.record_service
        )

        self.history_writer = HistoryWriter(config)
        self.state_writer = StateWriter(config, self.account_service, self.record_service, self.order_service)

        # 初始化平仓检测服务
        self.close_detector = CloseDetectorService(self.rest_client, self.order_service, self.history_writer)

        # 初始化订单仓库（用于存储 pending orders）
        from modules.agent.live_engine.core import OrderRepository
        self.order_repository = OrderRepository()

        # 初始化事件层
        account_handler = AccountUpdateHandler(
            self.account_service, self.record_service, self.order_service, self.close_detector
        )
        order_handler = OrderUpdateHandler(
            order_service=self.order_service,
            order_repository=self.order_repository,
            record_service=self.record_service,
            linked_order_repo=self.linked_order_repo,
            commission_service=self.commission_service
        )
        algo_order_handler = AlgoOrderHandler(
            record_service=self.record_service,
            order_manager=self.order_manager,
            order_repository=self.order_repository,
            linked_order_repo=self.linked_order_repo,
            commission_service=self.commission_service
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
                self.order_service.sync_tpsl_orders()

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
                logger.info(f"持仓数量: {self.position_service.get_open_positions_count()}")
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
                self.order_service.sync_tpsl_orders()
                self.account_service.sync_from_api()

                sync_result = self.order_sync_service.sync()
                if sync_result.get('filled_orders', 0) > 0:
                    logger.info(f"定时同步: 检测到 {sync_result['filled_orders']} 个订单状态变化")

                active_symbols = self.position_service.get_open_symbols()
                cleaned = self.order_service.cleanup_orphan_orders(active_symbols)
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
        """获取账户汇总（兼容模拟器接口）"""
        with self._lock:
            summary = self.account_service.get_summary()
            summary['positions_count'] = self.position_service.get_open_positions_count()
            return summary

    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """获取持仓汇总（兼容模拟器接口）

        从 RecordRepository 获取持仓汇总。
        """
        with self._lock:
            return self.position_service.get_positions_summary()

    def open_position(self, symbol: str, side: str, quote_notional_usdt: float, leverage: int,
                      tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        """开仓（兼容模拟器接口）"""
        try:
            # 获取当前价格计算数量
            ticker = self.rest_client.get_24hr_ticker(symbol)
            if isinstance(ticker, list) and len(ticker) > 0:
                ticker = ticker[0]

            current_price = float(ticker.get('lastPrice', 0))
            if current_price == 0:
                return {'error': f'无法获取 {symbol} 当前价格'}

            # 计算数量
            quantity = quote_notional_usdt / current_price

            # 获取交易规则（精度）
            exchange_info = self.rest_client.get_exchange_info()
            quantity_precision = 3
            for s in exchange_info.get('symbols', []):
                if s['symbol'] == symbol:
                    quantity_precision = s.get('quantityPrecision', 3)
                    break

            quantity = round(quantity, quantity_precision)

            logger.info(f"开仓: {symbol} {side} 名义=${quote_notional_usdt} 杠杆={leverage}x 数量={quantity}")

            # 调用订单服务开仓
            result = self.order_service.open_position_with_tpsl(
                symbol, side, quantity, leverage, tp_price, sl_price
            )

            if 'error' not in result:
                market_order = result.get('market_order', {})
                entry_price = float(market_order.get('avgPrice', 0))
                filled_qty = float(market_order.get('executedQty', quantity))
                notional_usdt = entry_price * filled_qty
                margin_used = notional_usdt / leverage
                
                result = {
                    'success': True,
                    'id': str(market_order.get('orderId', '')),
                    'symbol': symbol,
                    'side': side,
                    'qty': filled_qty,
                    'entry_price': entry_price,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'leverage': leverage,
                    'notional_usdt': notional_usdt,
                    'margin_used': margin_used,
                    'market_order': market_order,
                    'tp_order_id': result.get('tp_order_id'),
                    'sl_order_id': result.get('sl_order_id')
                }
                
                if entry_price == 0:
                    logger.warning(f"{symbol} 开仓成功但 avgPrice 为 0，可能需要等待成交确认")
                    result = {
                        'success': True,
                        'symbol': symbol,
                        'side': side,
                        'message': '开仓成功，但持仓信息尚未同步'
                    }

                # 持久化
                self.state_writer.persist()

            return result

        except Exception as e:
            logger.error(f"开仓失败: {e}", exc_info=True)
            return {'error': str(e)}

    def _get_trading_config(self) -> Dict[str, Any]:
        """获取交易配置（固定金额和杠杆）"""
        trading_config = self.config.get('trading', {})
        return {
            'fixed_margin_usdt': trading_config.get('fixed_margin_usdt', 50.0),
            'max_leverage': trading_config.get('max_leverage', 10),
        }

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
        """创建限价单（信号模式，智能选择限价单/条件单）

        Agent 只提供开仓信号，实际金额和杠杆由配置决定。
        会根据当前价格自动选择使用限价单（Maker）或条件单（Taker）。

        Args:
            symbol: 交易对
            side: 方向（long/short）
            limit_price: 挂单/触发价格
            tp_price: 止盈价
            sl_price: 止损价
            source: 订单来源（'live'/'reverse'/'agent'）
            agent_side: Agent 原始方向（反向模式时使用）

        Returns:
            订单信息字典
        """
        try:
            config_mgr = get_trading_config_manager()
            margin_usdt = config_mgr.fixed_margin_usdt
            leverage = config_mgr.fixed_leverage

            notional = margin_usdt * leverage
            quantity = notional / limit_price
            quantity = ExchangeInfoCache.format_quantity(symbol, quantity)

            logger.info(f"创建限价单: {symbol} {side} @ {limit_price}, margin={margin_usdt}, leverage={leverage}x, qty={quantity}")

            self.order_manager.ensure_dual_position_mode()
            self.order_manager.ensure_leverage(symbol, leverage)

            result = self.order_service.create_smart_limit_order(
                symbol=symbol,
                side=side,
                limit_price=limit_price,
                quantity=quantity,
                tp_price=tp_price,
                sl_price=sl_price,
                source=source,
                expiration_days=config_mgr.expiration_days
            )

            if 'error' in result:
                return result

            result['margin_usdt'] = margin_usdt
            result['leverage'] = leverage
            result['agent_side'] = agent_side

            from modules.agent.live_engine.core.models import AlgoOrderStatus, OrderKind, PendingOrder

            is_conditional = result.get('order_kind') == 'CONDITIONAL'
            order_id_key = 'algo_id' if is_conditional else 'order_id'
            order_id_val = result.get(order_id_key)

            if order_id_val:
                pending_order = PendingOrder(
                    id=str(order_id_val),
                    symbol=symbol,
                    side=result.get('side', side),
                    trigger_price=result.get('trigger_price') or result.get('price', limit_price),
                    quantity=result.get('quantity', quantity),
                    status=AlgoOrderStatus.NEW,
                    order_kind=OrderKind.CONDITIONAL_ORDER if is_conditional else OrderKind.LIMIT_ORDER,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    leverage=leverage,
                    margin_usdt=margin_usdt,
                    order_id=None if is_conditional else int(order_id_val),
                    algo_id=str(order_id_val) if is_conditional else None,
                    source=source,
                    agent_side=agent_side,
                    agent_limit_price=limit_price
                )
                self.order_repository.save(pending_order)
                logger.info(f"[Engine] 订单已保存到 pending_orders: {pending_order.id}")

            return result

        except Exception as e:
            logger.error(f"创建限价单失败: {e}", exc_info=True)
            return {'error': str(e)}

    def close_position(self, position_id: Optional[str] = None, symbol: Optional[str] = None,
                       close_reason: Optional[str] = None, close_price: Optional[float] = None) -> Dict[str, Any]:
        """平仓（兼容模拟器接口）"""
        with self._lock:
            record = None
            if position_id:
                record = self.record_service.get_record(position_id)
            elif symbol:
                records = self.record_service.get_open_records_by_symbol(symbol)
                if records:
                    record = records[0]

            if not record:
                return {'error': '未找到持仓'}

            logger.info(f"平仓: {record.symbol} 原因={close_reason}")

            result = self.order_service.close_position_market(
                record.symbol, record.side, record.qty,
                close_reason=close_reason or 'Agent主动平仓'
            )

            if 'error' not in result:
                order_data = result.get('order', {})
                avg_price = float(order_data.get('avgPrice', record.latest_mark_price or record.entry_price))
                order_id = order_data.get('orderId')

                exit_info = {}
                if order_id:
                    exit_info = self.record_service.fetch_exit_info(record.symbol, order_id)

                self.record_service.close_record(
                    record.id,
                    close_price=exit_info.get('close_price') or avg_price,
                    close_reason=close_reason or 'Agent主动平仓',
                    exit_commission=exit_info.get('exit_commission', 0),
                    realized_pnl=exit_info.get('realized_pnl')
                )

                self.state_writer.persist()

            return result

    def update_tp_sl(self, symbol: str,
                     tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        """更新止盈止损（兼容模拟器接口）"""
        with self._lock:
            records = self.record_service.get_open_records_by_symbol(symbol)
            if not records:
                return {'error': f'{symbol} 无持仓'}

            record = records[0]

            logger.info(f"更新 TP/SL: {symbol} TP={tp_price} SL={sl_price}")

            result = self.order_service.update_tpsl(symbol, tp_price, sl_price, record.side)

            if 'error' not in result:
                self.record_service.update_tpsl_ids(
                    record.id,
                    tp_order_id=result.get('tp_order_id'),
                    sl_algo_id=result.get('sl_order_id')
                )
                self.record_service._repository.update(record.id, tp_price=tp_price, sl_price=sl_price)

                self.state_writer.persist()

                return {
                    'success': True,
                    'id': record.id,
                    'symbol': symbol,
                    'side': record.side,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'tp_order_id': result.get('tp_order_id'),
                    'sl_order_id': result.get('sl_order_id')
                }

            return result

    def get_trading_config(self) -> Dict[str, Any]:
        """获取交易配置（统一配置）"""
        return get_trading_config_manager().get_dict()

    def update_trading_config(self, **kwargs) -> Dict[str, Any]:
        """更新交易配置"""
        config = get_trading_config_manager().update(**kwargs)
        return config.to_dict()

    def is_reverse_enabled(self) -> bool:
        """检查是否启用反向交易模式"""
        return get_trading_config_manager().reverse_enabled

    def cancel_pending_order(self, order_id: str, source: Optional[str] = None) -> bool:
        """撤销待触发订单（条件单或限价单）

        Args:
            order_id: 订单ID（PendingOrder.id）
            source: 可选，限制只能撤销指定来源的订单
        """
        order = self.order_repository.get(order_id)
        if not order:
            return False

        if source and order.source != source:
            return False

        success = False
        if order.order_kind == 'CONDITIONAL' and order.algo_id:
            success = self.order_manager.cancel_algo_order(order.symbol, order.algo_id)
        elif order.order_kind == 'LIMIT' and order.order_id:
            success = self.order_manager.cancel_order(order.symbol, order.order_id)

        if success:
            self.order_repository.delete(order_id)
            return True
        return False

    def close_record(self, record_id: str, source: Optional[str] = None) -> bool:
        """手动关闭指定开仓记录

        Args:
            record_id: 记录ID
            source: 可选，限制只能关闭指定来源的记录
        """
        record = self.record_service.get_record(record_id)
        if not record:
            return False

        if source and record.source != source:
            return False

        current_price = self.order_manager.get_mark_price(record.symbol) or record.entry_price

        result = self.order_manager.place_market_order(
            symbol=record.symbol,
            side='SELL' if record.side.upper() in ('LONG', 'BUY') else 'BUY',
            quantity=record.qty,
            position_side='LONG' if record.side.upper() in ('LONG', 'BUY') else 'SHORT',
            reduce_only=True
        )

        if result.get('success'):
            self.record_service.cancel_remaining_tpsl(record, 'TP')
            self.record_service.cancel_remaining_tpsl(record, 'SL')
            self.record_service.close_record(record_id, current_price, 'MANUAL_CLOSED')
            return True

        return False

    def close_all_records_by_symbol(self, symbol: str, source: Optional[str] = None) -> int:
        """关闭指定交易对的所有开仓记录

        Args:
            symbol: 交易对
            source: 可选，限制只关闭指定来源的记录

        Returns:
            关闭的记录数量
        """
        records = self.record_service.get_open_records_by_symbol(symbol, source=source)
        closed_count = 0

        for record in records:
            if self.close_record(record.id, source=source):
                closed_count += 1

        logger.info(f"[LiveEngine] 已关闭 {symbol} 的 {closed_count} 条开仓记录 (source={source})")
        return closed_count

    def get_positions_summary_by_source(self, source: str) -> List[Dict[str, Any]]:
        """获取指定来源的开仓记录汇总"""
        return self.record_service.get_summary(source=source)

    def get_pending_orders_summary(self, source: Optional[str] = None) -> Dict[str, Any]:
        """获取待触发订单汇总

        Args:
            source: 可选，过滤指定来源
        """
        if source:
            pending_orders = self.order_repository.get_by_source(source)
        else:
            pending_orders = self.order_repository.get_all()

        conditional_orders = [o for o in pending_orders if o.order_kind == 'CONDITIONAL']
        limit_orders = [o for o in pending_orders if o.order_kind == 'LIMIT']

        return {
            'total_conditional': len(conditional_orders),
            'total_limit': len(limit_orders),
            'conditional_orders': [o.to_dict() for o in conditional_orders],
            'limit_orders': [o.to_dict() for o in limit_orders]
        }

    def get_history_by_source(self, source: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取指定来源的历史记录"""
        records = [
            r for r in self.record_service.records.values()
            if r.source == source and r.status.value != 'OPEN'
        ]
        records.sort(key=lambda x: x.close_time or '', reverse=True)

        result = []
        for record in records[:limit]:
            pnl_pct = (record.realized_pnl / record.margin_usdt * 100) if record.margin_usdt > 0 else 0
            result.append({
                'id': record.id,
                'symbol': record.symbol,
                'side': record.side.upper(),
                'qty': record.qty,
                'entry_price': record.entry_price,
                'exit_price': record.close_price,
                'leverage': record.leverage,
                'margin_usdt': round(record.margin_usdt, 2),
                'realized_pnl': round(record.realized_pnl or 0, 4),
                'pnl_percent': round(pnl_pct, 2),
                'open_time': record.open_time,
                'close_time': record.close_time,
                'close_reason': record.close_reason,
                'source': record.source,
                'entry_commission': round(record.entry_commission, 6),
                'exit_commission': round(record.exit_commission, 6),
                'total_commission': round(record.total_commission, 6)
            })
        return result

    def get_statistics_by_source(self, source: str) -> Dict[str, Any]:
        """获取指定来源的统计信息"""
        return self.record_service.get_statistics(source=source)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取所有来源的历史记录"""
        records = [
            r for r in self.record_service.records.values()
            if r.status.value != 'OPEN'
        ]
        records.sort(key=lambda x: x.close_time or '', reverse=True)

        result = []
        for record in records[:limit]:
            pnl_pct = (record.realized_pnl / record.margin_usdt * 100) if record.margin_usdt > 0 else 0
            result.append({
                'id': record.id,
                'symbol': record.symbol,
                'side': record.side.upper(),
                'qty': record.qty,
                'entry_price': record.entry_price,
                'exit_price': record.close_price,
                'leverage': record.leverage,
                'margin_usdt': round(record.margin_usdt, 2),
                'realized_pnl': round(record.realized_pnl or 0, 4),
                'pnl_percent': round(pnl_pct, 2),
                'open_time': record.open_time,
                'close_time': record.close_time,
                'close_reason': record.close_reason,
                'source': record.source,
                'entry_commission': round(record.entry_commission, 6),
                'exit_commission': round(record.exit_commission, 6),
                'total_commission': round(record.total_commission, 6)
            })
        return result

    def get_statistics(self) -> Dict[str, Any]:
        """获取所有来源的统计信息"""
        return self.record_service.get_statistics()
