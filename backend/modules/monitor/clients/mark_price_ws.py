"""标记价格 WebSocket 客户端

订阅币安合约的标记价格流，用于实时监控 TP/SL 触发条件。

WebSocket 地址: wss://fstream.binance.com/ws/!markPrice@arr@1s
推送频率: 每秒推送所有交易对的标记价格
"""

import json
import time
import threading
from typing import Callable, Dict, Optional, Set
import websocket
from ..utils.logger import get_logger

logger = get_logger('mark_price_ws')


class MarkPriceWSClient:
    """标记价格 WebSocket 客户端
    
    功能：
    - 订阅所有交易对的标记价格流（每秒推送）
    - 支持过滤特定交易对
    - 自动重连机制
    - 回调函数处理价格更新
    """
    
    BASE_URL = "wss://fstream.binance.com/ws"
    
    def __init__(self, on_price_update: Callable[[Dict[str, float]], None],
                 symbols_filter: Optional[Set[str]] = None):
        """初始化
        
        Args:
            on_price_update: 价格更新回调函数，参数为 {symbol: mark_price} 字典
            symbols_filter: 需要关注的交易对集合，None 表示关注所有
        """
        self.on_price_update = on_price_update
        self.symbols_filter = symbols_filter
        
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_running = False
        self.reconnect_count = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5
        self.ws_thread: Optional[threading.Thread] = None
        
        self._lock = threading.RLock()
        self._latest_prices: Dict[str, float] = {}
    
    def start(self):
        """启动 WebSocket 连接"""
        if self.is_running:
            logger.warning("[MarkPriceWS] 已在运行")
            return
        
        self.is_running = True
        self.reconnect_count = 0
        
        url = f"{self.BASE_URL}/!markPrice@arr@1s"
        
        logger.info(f"[MarkPriceWS] 正在连接: {url}")
        
        self.ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        self.ws_thread = threading.Thread(target=self._run_forever, daemon=True)
        self.ws_thread.start()
    
    def stop(self):
        """停止 WebSocket 连接"""
        logger.info("[MarkPriceWS] 正在停止...")
        self.is_running = False
        
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.warning(f"[MarkPriceWS] 关闭连接时出错: {e}")
        
        logger.info("[MarkPriceWS] 已停止")
    
    def _run_forever(self):
        """持续运行 WebSocket 连接"""
        while self.is_running:
            try:
                self.ws.run_forever(
                    ping_interval=180,
                    ping_timeout=10
                )
            except Exception as e:
                logger.error(f"[MarkPriceWS] 运行错误: {e}")
            
            if self.is_running:
                self._try_reconnect()
    
    def _try_reconnect(self):
        """尝试重连"""
        self.reconnect_count += 1
        
        if self.reconnect_count > self.max_reconnect_attempts:
            logger.error(f"[MarkPriceWS] 超过最大重连次数({self.max_reconnect_attempts})，停止重连")
            self.is_running = False
            return
        
        delay = min(self.reconnect_delay * (2 ** (self.reconnect_count - 1)), 60)
        logger.warning(f"[MarkPriceWS] 断开连接，{delay}秒后尝试第{self.reconnect_count}次重连...")
        time.sleep(delay)
    
    def _on_open(self, ws):
        """连接建立回调"""
        logger.info("[MarkPriceWS] ✅ 连接建立成功")
        self.reconnect_count = 0
    
    def _on_message(self, ws, message):
        """消息处理回调"""
        try:
            data = json.loads(message)
            
            if not isinstance(data, list):
                return
            
            prices: Dict[str, float] = {}
            
            for item in data:
                symbol = item.get('s')
                mark_price_str = item.get('p')
                
                if not symbol or not mark_price_str:
                    continue
                
                if self.symbols_filter and symbol not in self.symbols_filter:
                    continue
                
                try:
                    mark_price = float(mark_price_str)
                    prices[symbol] = mark_price
                except (ValueError, TypeError):
                    continue
            
            if prices:
                with self._lock:
                    self._latest_prices.update(prices)
                
                try:
                    self.on_price_update(prices)
                except Exception as e:
                    logger.error(f"[MarkPriceWS] 价格更新回调出错: {e}")
                    
        except json.JSONDecodeError as e:
            logger.warning(f"[MarkPriceWS] JSON 解析错误: {e}")
        except Exception as e:
            logger.error(f"[MarkPriceWS] 消息处理错误: {e}")
    
    def _on_error(self, ws, error):
        """错误回调"""
        logger.error(f"[MarkPriceWS] WebSocket 错误: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭回调"""
        logger.warning(f"[MarkPriceWS] 连接关闭: code={close_status_code}, msg={close_msg}")
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """获取指定交易对的最新标记价格
        
        Args:
            symbol: 交易对
            
        Returns:
            标记价格，未找到返回 None
        """
        with self._lock:
            return self._latest_prices.get(symbol)
    
    def get_all_prices(self) -> Dict[str, float]:
        """获取所有交易对的最新标记价格"""
        with self._lock:
            return self._latest_prices.copy()
    
    def add_symbol(self, symbol: str):
        """添加关注的交易对
        
        Args:
            symbol: 交易对
        """
        if self.symbols_filter is None:
            self.symbols_filter = set()
        self.symbols_filter.add(symbol)
        logger.info(f"[MarkPriceWS] 添加关注交易对: {symbol}")
    
    def remove_symbol(self, symbol: str):
        """移除关注的交易对
        
        Args:
            symbol: 交易对
        """
        if self.symbols_filter:
            self.symbols_filter.discard(symbol)
            logger.info(f"[MarkPriceWS] 移除关注交易对: {symbol}")
    
    def set_symbols_filter(self, symbols: Set[str]):
        """设置关注的交易对集合
        
        Args:
            symbols: 交易对集合
        """
        self.symbols_filter = symbols
        logger.info(f"[MarkPriceWS] 设置关注交易对: {len(symbols)} 个")
