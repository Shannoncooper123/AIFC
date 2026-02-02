"""币安WebSocket客户端"""
import json
import time
import threading
from typing import List, Callable, Optional, Dict, Set
import websocket
from ..utils.logger import get_logger

logger = get_logger('binance_ws')


class BinanceWSClient:
    """币安WebSocket客户端"""
    
    def __init__(self, config: Dict, on_kline_callback: Callable):
        """初始化
        
        Args:
            config: 配置字典
            on_kline_callback: K线数据回调函数
        """
        self.config = config
        self.base_url = config['websocket']['base_url']
        self.reconnect_delay = config['websocket']['reconnect_delay']
        self.max_reconnect_attempts = config['websocket']['max_reconnect_attempts']
        self.on_kline_callback = on_kline_callback
        
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_running = False
        self.reconnect_count = 0
        self.ws_thread: Optional[threading.Thread] = None
    
    def connect(self, symbols: List[str], interval: str):
        """连接WebSocket
        
        Args:
            symbols: 交易对列表
            interval: K线间隔
        """
        # 构建streams
        streams = [f"{symbol.lower()}@kline_{interval}" for symbol in symbols]
        streams_str = "/".join(streams)
        
        url = f"{self.base_url}/stream?streams={streams_str}"
        
        logger.info(f"连接WebSocket: {len(symbols)}个交易对, 间隔={interval}")
        
        # 创建WebSocket连接
        self.ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_ping=self._on_ping,
            on_pong=self._on_pong
        )
        
        self.is_running = True
        self.reconnect_count = 0
        
        # 在单独的线程中运行
        self.ws_thread = threading.Thread(target=self._run_forever, daemon=True)
        self.ws_thread.start()
    
    def _run_forever(self):
        """持续运行WebSocket连接"""
        while self.is_running:
            try:
                self.ws.run_forever(
                    ping_interval=180,  # 3分钟发送一次ping
                    ping_timeout=10
                )
            except Exception as e:
                logger.error(f"WebSocket运行错误: {e}")
            
            # 如果还在运行状态，尝试重连
            if self.is_running:
                self._try_reconnect()
    
    def _try_reconnect(self):
        """尝试重连"""
        self.reconnect_count += 1
        
        if self.reconnect_count > self.max_reconnect_attempts:
            logger.error(f"超过最大重连次数({self.max_reconnect_attempts})，停止重连")
            self.is_running = False
            return
        
        # 指数退避
        delay = min(self.reconnect_delay * (2 ** (self.reconnect_count - 1)), 60)
        logger.warning(f"WebSocket断开，{delay}秒后尝试第{self.reconnect_count}次重连...")
        time.sleep(delay)
    
    def _on_open(self, ws):
        """连接建立回调"""
        logger.info("WebSocket连接建立成功")
        self.reconnect_count = 0
    
    def _on_message(self, ws, message):
        """消息接收回调"""
        try:
            data = json.loads(message)
            
            # WebSocket返回的数据格式: {"stream": "...", "data": {...}}
            if 'stream' in data and 'data' in data:
                stream = data['stream']
                event_data = data['data']
                
                # 处理K线数据
                if '@kline_' in stream and event_data.get('e') == 'kline':
                    symbol = event_data['s']
                    kline_data = event_data['k']
                    
                    # 调用回调函数
                    self.on_kline_callback(symbol, kline_data)
        
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败: {message[:100]}")
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
    
    def _on_error(self, ws, error):
        """错误回调"""
        logger.error(f"WebSocket错误: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭回调"""
        logger.warning(f"WebSocket连接关闭: {close_status_code} - {close_msg}")
    
    def _on_ping(self, ws, message):
        """接收到ping"""
        logger.debug("收到ping")
    
    def _on_pong(self, ws, message):
        """接收到pong"""
        logger.debug("收到pong")
    
    def close(self):
        """关闭连接"""
        logger.info("关闭WebSocket连接...")
        self.is_running = False
        
        if self.ws:
            self.ws.close()
        
        # 避免在 WebSocket 回调线程中 join 自己导致错误
        try:
            if self.ws_thread and self.ws_thread.is_alive():
                import threading
                if threading.current_thread() == self.ws_thread:
                    logger.warning("close() 在 ws_thread 内调用，跳过 join 以避免cannot join current thread")
                else:
                    # 减少超时时间到 2 秒，避免退出过慢
                    self.ws_thread.join(timeout=2)
                    if self.ws_thread.is_alive():
                        logger.warning("WebSocket 线程在 2 秒后仍未退出，跳过等待")
        except Exception as e:
            logger.error(f"关闭WebSocket线程时出现异常: {e}")
        finally:
            # 释放引用，便于后续重建
            self.ws_thread = None
        
        logger.info("WebSocket已关闭")
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.is_running and self.ws is not None


class MultiConnectionManager:
    """多连接管理器"""
    
    def __init__(self, config: Dict, on_kline_callback: Callable):
        """初始化
        
        Args:
            config: 配置字典
            on_kline_callback: K线数据回调函数
        """
        self.config = config
        self.on_kline_callback = on_kline_callback
        self.max_streams = config['websocket']['max_streams_per_connection']
        self.clients: List[BinanceWSClient] = []
        self.current_symbols: Set[str] = set()
        self.interval: str = ""
        self._lock = threading.Lock()
    
    def connect_all(self, symbols: List[str], interval: str):
        """连接所有交易对
        
        Args:
            symbols: 交易对列表
            interval: K线间隔
        """
        with self._lock:
            #关闭并清理所有旧连接，避免连接泄漏
            if self.clients:
                logger.info(f"清理{len(self.clients)}个旧WebSocket连接...")
                for client in self.clients:
                    client.close()
                self.clients.clear()
                # 等待旧连接完全关闭
                time.sleep(0.5)
            
            self.interval = interval
            self.current_symbols = set(symbols)
            
            # 如果没有需要订阅的币种，直接返回
            if not symbols:
                logger.info("无需订阅任何币种，跳过WebSocket连接创建")
                return
            
            # 按最大streams分组
            symbol_groups = [
                symbols[i:i + self.max_streams]
                for i in range(0, len(symbols), self.max_streams)
            ]
            
            logger.info(f"创建{len(symbol_groups)}个WebSocket连接")
            
            # 为每组创建一个连接
            for i, group in enumerate(symbol_groups):
                client = BinanceWSClient(self.config, self.on_kline_callback)
                client.connect(group, interval)
                self.clients.append(client)
                logger.info(f"连接 {i+1}/{len(symbol_groups)}: {len(group)}个交易对")
                
                # 避免同时建立太多连接
                if i < len(symbol_groups) - 1:
                    time.sleep(0.5)
    
    def update_symbols(self, added: List[str], removed: List[str]):
        """动态更新交易对订阅
        
        Args:
            added: 新增的交易对列表
            removed: 移除的交易对列表
        """
        with self._lock:
            if not added and not removed:
                return
            
            logger.info(f"更新WebSocket订阅: +{len(added)}, -{len(removed)}")
            
            # 更新当前交易对集合
            for symbol in added:
                self.current_symbols.add(symbol)
            for symbol in removed:
                self.current_symbols.discard(symbol)
            
            # 简单策略：完全重建连接
            # 注：这会有短暂中断，但保证数据一致性
            self._rebuild_connections()
    
    def _rebuild_connections(self):
        """重建所有WebSocket连接（使用 connect_all 统一逻辑）"""
        logger.info("重建WebSocket连接...")
        
        # 直接调用 connect_all，它会自动清理旧连接
        symbols = sorted(list(self.current_symbols))
        self.connect_all(symbols, self.interval)
        
        logger.info(f"WebSocket重建完成: {len(symbols)}个交易对")
    
    def close_all(self):
        """关闭所有连接"""
        with self._lock:
            logger.info(f"关闭{len(self.clients)}个WebSocket连接...")
            for client in self.clients:
                client.close()
            self.clients.clear()
            self.current_symbols.clear()
    
    def is_all_connected(self) -> bool:
        """检查是否所有连接都正常"""
        return all(client.is_connected() for client in self.clients)
    
    def get_subscribed_count(self) -> int:
        """获取当前订阅的交易对数量"""
        return len(self.current_symbols)


class BinanceUserDataWSClient:
    """币安用户数据流WebSocket客户端"""
    
    def __init__(self, config: Dict, rest_client, on_event_callback: Callable):
        """初始化
        
        Args:
            config: 配置字典
            rest_client: REST客户端（用于创建和保活listenKey）
            on_event_callback: 事件回调函数 callback(event_type, data)
        """
        self.config = config
        self.rest_client = rest_client
        self.base_url = config['websocket']['base_url']
        self.on_event_callback = on_event_callback
        
        self.listen_key: Optional[str] = None
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_running = False
        self.ws_thread: Optional[threading.Thread] = None
        self.keepalive_thread: Optional[threading.Thread] = None
    
    def start(self):
        """启动用户数据流"""
        try:
            # 创建 listenKey
            response = self.rest_client.create_listen_key()
            self.listen_key = response.get('listenKey')
            
            if not self.listen_key:
                logger.error("无法创建 listenKey")
                return
            
            logger.info(f"用户数据流 listenKey 已创建")
            
            # 构建 WebSocket URL
            url = f"{self.base_url}/ws/{self.listen_key}"
            
            # 创建 WebSocket 连接
            self.ws = websocket.WebSocketApp(
                url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            self.is_running = True
            
            # 启动 WebSocket 线程
            self.ws_thread = threading.Thread(target=self._run_forever, daemon=True)
            self.ws_thread.start()
            
            # 启动保活线程
            self.keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
            self.keepalive_thread.start()
            
            logger.info("用户数据流 WebSocket 已启动")
        
        except Exception as e:
            logger.error(f"启动用户数据流失败: {e}")
    
    def _run_forever(self):
        """持续运行 WebSocket"""
        while self.is_running:
            try:
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.error(f"用户数据流 WebSocket 运行错误: {e}")
            
            # 如果还在运行，尝试重连
            if self.is_running:
                logger.warning("用户数据流断开，5秒后重连...")
                time.sleep(5)
                # 重新创建 listenKey
                try:
                    response = self.rest_client.create_listen_key()
                    new_listen_key = response.get('listenKey')
                    if new_listen_key:
                        self.listen_key = new_listen_key
                        url = f"{self.base_url}/ws/{self.listen_key}"
                        self.ws = websocket.WebSocketApp(
                            url,
                            on_open=self._on_open,
                            on_message=self._on_message,
                            on_error=self._on_error,
                            on_close=self._on_close
                        )
                        logger.info("用户数据流 listenKey 已重新创建")
                except Exception as e:
                    logger.error(f"重新创建 listenKey 失败: {e}")
    
    def _keepalive_loop(self):
        """保活循环（每30分钟）"""
        while self.is_running:
            time.sleep(30 * 60)  # 30分钟
            if not self.is_running:
                break
            
            try:
                self.rest_client.keepalive_listen_key()
                logger.info("用户数据流 listenKey 已保活")
            except Exception as e:
                logger.error(f"保活 listenKey 失败: {e}")
    
    def _on_open(self, ws):
        """连接建立回调"""
        logger.info(f"[UserDataWS] ✅ WebSocket 连接建立成功 (listenKey={self.listen_key[:20]}...)")
    
    def _on_message(self, ws, message):
        """消息接收回调"""
        try:
            data = json.loads(message)
            event_type = data.get('e')
            
            # 打印所有收到的消息（便于调试）
            if event_type:
                logger.info(f"[UserDataWS] 📥 收到事件: {event_type}")
            
            if event_type == 'ACCOUNT_UPDATE':
                logger.info(f"[UserDataWS] ACCOUNT_UPDATE 事件")
                self.on_event_callback('ACCOUNT_UPDATE', data)
            elif event_type == 'ORDER_TRADE_UPDATE':
                order_info = data.get('o', {})
                symbol = order_info.get('s', '')
                status = order_info.get('X', '')
                order_type = order_info.get('ot', '')
                logger.info(f"[UserDataWS] ORDER_TRADE_UPDATE: {symbol} type={order_type} status={status}")
                self.on_event_callback('ORDER_TRADE_UPDATE', data)
            elif event_type == 'listenKeyExpired':
                logger.warning(f"[UserDataWS] ⚠️ listenKey 已过期！需要重新连接")
            else:
                logger.debug(f"[UserDataWS] 收到其他事件类型: {event_type}")
        
        except json.JSONDecodeError:
            logger.error(f"用户数据流 JSON 解析失败: {message[:100]}")
        except Exception as e:
            logger.error(f"用户数据流消息处理失败: {e}")
    
    def _on_error(self, ws, error):
        """错误回调"""
        logger.error(f"[UserDataWS] ❌ WebSocket 错误: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭回调"""
        logger.warning(f"[UserDataWS] ⚠️ WebSocket 关闭: code={close_status_code} msg={close_msg}")
    
    def stop(self):
        """停止用户数据流"""
        logger.info("停止用户数据流...")
        self.is_running = False
        
        if self.ws:
            self.ws.close()
        
        # 等待线程结束
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2)
        if self.keepalive_thread and self.keepalive_thread.is_alive():
            self.keepalive_thread.join(timeout=2)
        
        logger.info("用户数据流已停止")
