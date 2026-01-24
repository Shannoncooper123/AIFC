"""币安实盘交易引擎

职责：
- 初始化各服务层
- 协调各层交互
- 对外提供统一接口（符合 EngineProtocol）
"""
from typing import Dict, Optional, List, Any
import threading
import time
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.clients.binance_ws import BinanceUserDataWSClient
from modules.monitor.utils.logger import get_logger

from modules.agent.live_engine.services.account_service import AccountService
from modules.agent.live_engine.services.position_service import PositionService
from modules.agent.live_engine.services.order_service import OrderService
from modules.agent.live_engine.services.close_detector import CloseDetectorService

from modules.agent.live_engine.events.dispatcher import EventDispatcher
from modules.agent.live_engine.events.account_handler import AccountUpdateHandler
from modules.agent.live_engine.events.order_handler import OrderUpdateHandler

from modules.agent.live_engine.persistence.state_writer import StateWriter
from modules.agent.live_engine.persistence.history_writer import HistoryWriter

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
        
        # 验证 API 密钥
        if not self.rest_client.api_key or not self.rest_client.api_secret:
            logger.error("=" * 60)
            logger.error("⚠️  API 密钥未配置！")
            logger.error(f"API Key: {'已配置' if self.rest_client.api_key else '未配置'}")
            logger.error(f"API Secret: {'已配置' if self.rest_client.api_secret else '未配置'}")
            logger.error("请在 .env 文件中设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
            logger.error("=" * 60)
        else:
            logger.info(f"API 密钥已加载: Key长度={len(self.rest_client.api_key)}, Secret长度={len(self.rest_client.api_secret)}")
        
        # 初始化服务层
        self.account_service = AccountService(self.rest_client)
        self.order_service = OrderService(self.rest_client, config)
        self.position_service = PositionService(self.rest_client)
        
        # 初始化持久化层
        self.history_writer = HistoryWriter(config)
        self.state_writer = StateWriter(config, self.account_service, self.position_service, self.order_service)
        
        # 初始化平仓检测服务
        self.close_detector = CloseDetectorService(self.rest_client, self.order_service, self.history_writer)
        
        # 初始化事件层
        account_handler = AccountUpdateHandler(
            self.account_service, self.position_service, self.order_service, self.close_detector
        )
        order_handler = OrderUpdateHandler(self.order_service)
        self.event_dispatcher = EventDispatcher(account_handler, order_handler)
        
        # 用户数据流 WebSocket
        self.user_data_ws: Optional[BinanceUserDataWSClient] = None
    
    def _inject_tpsl_into_positions(self) -> None:
        """从当前挂单中提取 TP/SL 价格并写入到 Position 对象"""
        try:
            prices_map = self.order_service.get_tpsl_prices()
            for symbol, pos in self.position_service.positions.items():
                prices = prices_map.get(symbol)
                if not prices:
                    continue
                tp_price = prices.get('tp_price')
                sl_price = prices.get('sl_price')
                if tp_price is not None:
                    pos.tp_price = tp_price
                if sl_price is not None:
                    pos.sl_price = sl_price
        except Exception as e:
            logger.warning(f"注入 TP/SL 价格到持仓失败: {e}")
    
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
                # 1. 检查并设置持仓模式为单向持仓
                logger.info("1. 检查持仓模式...")
                try:
                    position_mode = self.rest_client.get_position_mode()
                    dual_side = position_mode.get('dualSidePosition', False)
                    if dual_side:
                        logger.warning("当前为双向持仓模式，正在切换为单向持仓模式...")
                        self.rest_client.set_position_mode(dual_side=False)
                        logger.info("✅ 已切换为单向持仓模式（One-way Mode）")
                    else:
                        logger.info("✅ 当前已是单向持仓模式")
                except Exception as e:
                    logger.error(f"设置持仓模式失败: {e}")
                    logger.warning("将继续启动，但下单可能失败")
                
                # 2. 同步账户和持仓信息
                logger.info("2. 同步账户信息...")
                self.account_service.sync_from_api()
                
                logger.info("3. 同步持仓信息...")
                self.position_service.sync_from_api()
                
                logger.info("4. 同步 TP/SL 订单...")
                self.order_service.sync_tpsl_orders()
                self._inject_tpsl_into_positions()
                
                # 5. 跳过历史同步（已默认禁用）
                logger.info("5. 跳过历史持仓同步（history_sync_days=0）")
                
                # 6. 启动用户数据流
                logger.info("6. 启动用户数据流...")
                self.user_data_ws = BinanceUserDataWSClient(
                    self.config,
                    self.rest_client,
                    self.event_dispatcher.handle_event
                )
                self.user_data_ws.start()
                
                # 7. 初始持久化
                logger.info("7. 持久化初始状态...")
                self._inject_tpsl_into_positions()
                self.state_writer.persist()
                
                # 8. 启动定时同步线程
                logger.info("8. 启动定时同步线程...")
                self._sync_thread = threading.Thread(target=self._periodic_sync_loop, daemon=True)
                self._sync_thread.start()
                
                logger.info("=" * 60)
                logger.info("实盘交易引擎启动完成")
                logger.info(f"账户余额: ${self.account_service.balance:.2f}")
                logger.info(f"持仓数量: {len(self.position_service.positions)}")
                logger.info("=" * 60)
            
            except Exception as e:
                logger.error(f"启动引擎失败: {e}", exc_info=True)
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
                self.position_service.sync_from_api()
                self.account_service.sync_from_api()
                
                # 清理孤儿订单
                active_symbols = set(self.position_service.positions.keys())
                cleaned = self.order_service.cleanup_orphan_orders(active_symbols)
                if cleaned > 0:
                    logger.info(f"定时清理: 已清除 {cleaned} 个币种的孤儿订单")
                
                # 验证一致性
                self.order_service.validate_tpsl_consistency(self.position_service.positions)
                
                # 持久化
                self._inject_tpsl_into_positions()
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
                
                # 同步持久化状态
                self.state_writer.persist_sync()
                
                logger.info("实盘交易引擎已停止")
            
            except Exception as e:
                logger.error(f"停止引擎时出错: {e}")
    
    def get_account_summary(self) -> Dict[str, Any]:
        """获取账户汇总（兼容模拟器接口）"""
        with self._lock:
            summary = self.account_service.get_summary()
            summary['positions_count'] = len(self.position_service.positions)
            return summary
    
    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """获取持仓汇总（兼容模拟器接口）"""
        with self._lock:
            return self.position_service.get_positions_summary(self.order_service)
    
    def open_position(self, symbol: str, side: str, quote_notional_usdt: float, leverage: int,
                      tp_price: Optional[float] = None, sl_price: Optional[float] = None,
                      run_id: Optional[str] = None) -> Dict[str, Any]:
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
                # 立即同步持仓信息
                try:
                    self.position_service.sync_from_api()
                except Exception as e:
                    logger.warning(f"开仓后同步持仓失败: {e}")
                
                # 更新持仓的 TP/SL 价格
                if symbol in self.position_service.positions:
                    pos = self.position_service.positions[symbol]
                    pos.tp_price = tp_price
                    pos.sl_price = sl_price
                    pos.leverage = leverage
                    
                    # 构造返回值
                    result = {
                        'success': True,
                        'id': pos.id,
                        'symbol': symbol,
                        'side': side,
                        'qty': pos.qty,
                        'entry_price': pos.entry_price,
                        'tp_price': tp_price,
                        'sl_price': sl_price,
                        'leverage': leverage,
                        'notional_usdt': pos.notional_usdt,
                        'margin_used': pos.margin_used,
                        'market_order': result.get('market_order'),
                        'tp_order_id': result.get('tp_order_id'),
                        'sl_order_id': result.get('sl_order_id')
                    }
                else:
                    logger.warning(f"{symbol} 开仓成功但持仓跟踪器中未找到持仓对象")
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
    
    def close_position(self, position_id: Optional[str] = None, symbol: Optional[str] = None,
                       close_reason: Optional[str] = None, close_price: Optional[float] = None,
                       run_id: Optional[str] = None) -> Dict[str, Any]:
        """平仓（兼容模拟器接口）"""
        with self._lock:
            # 通过 symbol 或 position_id 查找持仓
            target_symbol = symbol
            if not target_symbol and position_id:
                for sym, pos in self.position_service.positions.items():
                    if pos.id == position_id:
                        target_symbol = sym
                        break
            
            if not target_symbol:
                return {'error': '未找到持仓'}
            
            if target_symbol not in self.position_service.positions:
                return {'error': f'{target_symbol} 无持仓'}
            
            pos = self.position_service.positions[target_symbol]
            
            logger.info(f"平仓: {target_symbol} 原因={close_reason}")
            
            # 调用订单服务平仓
            result = self.order_service.close_position_market(
                target_symbol, pos.side, pos.qty, 
                position_obj=pos, 
                close_reason=close_reason or 'Agent主动平仓'
            )
            
            if 'error' not in result:
                # 记录历史（主动平仓）
                order_data = result.get('order', {})
                avg_price = float(order_data.get('avgPrice', pos.latest_mark_price or pos.entry_price))
                order_id = order_data.get('orderId')
                
                self.history_writer.record_closed_position(
                    pos,
                    close_reason=close_reason or 'Agent主动平仓',
                    close_price=avg_price,
                    close_order_id=order_id
                )
                
                # 持久化
                self.state_writer.persist()
            
            return result
    
    def update_tp_sl(self, symbol: str,
                     tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        """更新止盈止损（兼容模拟器接口）"""
        with self._lock:
            if symbol not in self.position_service.positions:
                return {'error': f'{symbol} 无持仓'}
            
            pos = self.position_service.positions[symbol]
            
            logger.info(f"更新 TP/SL: {symbol} TP={tp_price} SL={sl_price}")
            
            # 调用订单服务更新
            result = self.order_service.update_tpsl(symbol, tp_price, sl_price, pos.side)
            
            if 'error' not in result:
                # 更新 Position 对象
                pos.tp_price = tp_price
                pos.sl_price = sl_price
                
                # 持久化
                self.state_writer.persist()
                
                # 返回完整的持仓信息（工具需要这些字段）
                return {
                    'success': True,
                    'id': pos.id,
                    'symbol': symbol,
                    'side': pos.side,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'tp_order_id': result.get('tp_order_id'),
                    'sl_order_id': result.get('sl_order_id')
                }
            
            return result
