"""币安REST API客户端"""
import requests
import time
import hmac
import hashlib
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ..utils.helpers import retry_on_exception


class BinanceRestClient:
    """币安合约REST API客户端"""
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.base_url = config['api']['base_url']
        self.timeout = config['api']['timeout']
        self.retry_times = config['api']['retry_times']
        
        # 交易API密钥（可选，仅实盘模式需要）
        env = config.get('env', {})
        self.api_key = env.get('binance_api_key', '')
        self.api_secret = env.get('binance_api_secret', '')
        
        # 创建Session以复用连接池，提升性能
        self.session = requests.Session()
        retry_strategy = Retry(
            total=0,  # 由@retry_on_exception装饰器处理重试
            connect=0,
            read=0,
            redirect=0,
            status=0,
            backoff_factor=0
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,  # 连接池大小
            pool_maxsize=20
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
    
    @retry_on_exception(max_retries=5, delay=1.0, exceptions=(requests.RequestException,))
    def get_exchange_info(self) -> Dict[str, Any]:
        """获取交易所信息
        
        Returns:
            交易所信息字典
        """
        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=1.0, exceptions=(requests.RequestException,))
    def get_klines(self, symbol: str, interval: str, limit: int = 500,
                   start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[List]:
        """获取K线数据
        
        Args:
            symbol: 交易对符号
            interval: K线间隔
            limit: 数量限制（最大1500）
            start_time: 起始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            
        Returns:
            K线数据列表
            
        Note:
            返回的K线数据格式为:
            [
                [
                    1499040000000,      // 开盘时间
                    "0.01634790",       // 开盘价
                    "0.80000000",       // 最高价
                    "0.01575800",       // 最低价
                    "0.01577100",       // 收盘价
                    "148976.11427815",  // 成交量
                    1499644799999,      // 收盘时间
                    "2434.19055334",    // 成交额
                    308,                // 成交笔数
                    "1756.87402397",    // 主动买入成交量
                    "28.46694368",      // 主动买入成交额
                    "17928899.62484339" // 请忽略该参数
                ]
            ]
        """
        url = f"{self.base_url}/fapi/v1/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1500)
        }
        
        if start_time is not None:
            params['startTime'] = start_time
        if end_time is not None:
            params['endTime'] = end_time
        
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=1.0, exceptions=(requests.RequestException,))
    def get_24hr_ticker(self, symbol: Optional[str] = None) -> Any:
        """获取24小时价格变动统计
        
        Args:
            symbol: 交易对符号（None表示获取所有）
            
        Returns:
            24小时统计数据
        """
        url = f"{self.base_url}/fapi/v1/ticker/24hr"
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def get_all_usdt_perpetual_symbols(self, min_volume_24h: float = 0) -> List[str]:
        """获取所有USDT永续合约交易对
        
        Args:
            min_volume_24h: 最小24小时成交量（USDT）
            
        Returns:
            交易对符号列表
        """
        # 获取交易所信息
        exchange_info = self.get_exchange_info()
        
        # 过滤USDT永续合约
        symbols = []
        for symbol_info in exchange_info.get('symbols', []):
            # 检查是否为USDT永续合约
            if (symbol_info.get('quoteAsset') == 'USDT' and
                symbol_info.get('contractType') == 'PERPETUAL' and
                symbol_info.get('status') == 'TRADING'):
                symbols.append(symbol_info['symbol'])
        
        # 如果需要过滤成交量
        if min_volume_24h > 0:
            # 获取24小时统计
            tickers = self.get_24hr_ticker()
            
            # 建立成交量映射
            volume_map = {}
            for ticker in tickers:
                try:
                    quote_volume = float(ticker.get('quoteVolume', 0))
                    volume_map[ticker['symbol']] = quote_volume
                except (ValueError, KeyError):
                    continue
            
            # 过滤成交量
            symbols = [s for s in symbols if volume_map.get(s, 0) >= min_volume_24h]
        
        return sorted(symbols)
    
    @retry_on_exception(max_retries=5, delay=1.0, exceptions=(requests.RequestException,))
    def get_open_interest_hist(self, symbol: str, period: str, limit: int = 30,
                                start_time: Optional[int] = None, 
                                end_time: Optional[int] = None) -> List[Dict]:
        """获取合约持仓量历史数据
        
        Args:
            symbol: 交易对符号
            period: 时间周期 ("5m","15m","30m","1h","2h","4h","6h","12h","1d")
            limit: 数量限制（默认30，最大500）
            start_time: 开始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            
        Returns:
            持仓量历史数据列表
            
        Note:
            - 若无 startTime 和 endTime 限制，则默认返回当前时间往前的limit值
            - 仅支持最近1个月的数据
            - IP限频为1000次/5min
        """
        url = f"{self.base_url}/futures/data/openInterestHist"
        params = {
            'symbol': symbol,
            'period': period,
            'limit': min(limit, 500)
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def _sign_request(self, params: Dict[str, Any]) -> str:
        """生成请求签名
        
        Args:
            params: 请求参数
            
        Returns:
            HMAC SHA256 签名
        """
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头
        
        Returns:
            包含API密钥的请求头
        """
        return {
            'X-MBX-APIKEY': self.api_key
        }
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def place_order(self, symbol: str, side: str, order_type: str, 
                    quantity: Optional[float] = None, price: Optional[float] = None,
                    stop_price: Optional[float] = None, close_position: bool = False,
                    reduce_only: bool = False, time_in_force: str = 'GTC',
                    working_type: str = 'MARK_PRICE') -> Dict[str, Any]:
        """下单
        
        Args:
            symbol: 交易对
            side: 买卖方向（BUY/SELL）
            order_type: 订单类型（MARKET/LIMIT/STOP_MARKET/TAKE_PROFIT_MARKET）
            quantity: 数量（MARKET 订单必填，条件单可选）
            price: 价格（LIMIT 订单必填）
            stop_price: 触发价（条件单必填）
            close_position: 是否全平仓（条件单）
            reduce_only: 只减仓
            time_in_force: 有效方式（GTC/IOC/FOK）
            working_type: 条件单触发价格类型（MARK_PRICE/CONTRACT_PRICE）
            
        Returns:
            订单响应
        """
        url = f"{self.base_url}/fapi/v1/order"
        
        # 使用最新时间戳，避免过期（币安要求5000ms窗口内）
        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'timestamp': int(time.time() * 1000)
        }
        
        if quantity is not None:
            params['quantity'] = quantity
        if price is not None:
            params['price'] = price
        if stop_price is not None:
            params['stopPrice'] = stop_price
        if close_position:
            params['closePosition'] = 'true'
        if reduce_only:
            params['reduceOnly'] = 'true'
        if order_type in ['LIMIT']:
            params['timeInForce'] = time_in_force
        if order_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
            params['workingType'] = working_type
        
        # 签名（在发送前立即生成，确保时间戳新鲜）
        params['signature'] = self._sign_request(params)
        
        # 使用更长的超时时间，下单操作可能需要更多时间
        order_timeout = max(self.timeout, 20)  # 至少20秒
        response = self.session.post(url, params=params, headers=self._get_headers(), timeout=order_timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                     client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """撤销订单
        
        Args:
            symbol: 交易对
            order_id: 订单ID（二选一）
            client_order_id: 客户端订单ID（二选一）
            
        Returns:
            撤单响应
        """
        url = f"{self.base_url}/fapi/v1/order"
        
        params = {
            'symbol': symbol,
            'timestamp': int(time.time() * 1000)
        }
        
        if order_id is not None:
            params['orderId'] = order_id
        elif client_order_id is not None:
            params['origClientOrderId'] = client_order_id
        else:
            raise ValueError("必须提供 order_id 或 client_order_id")
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        order_timeout = max(self.timeout, 15)
        response = self.session.delete(url, params=params, headers=self._get_headers(), timeout=order_timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询当前挂单
        
        Args:
            symbol: 交易对（可选，不填则查询所有）
            
        Returns:
            挂单列表
        """
        url = f"{self.base_url}/fapi/v1/openOrders"
        
        params = {
            'timestamp': int(time.time() * 1000)
        }
        
        if symbol:
            params['symbol'] = symbol
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        # 使用 self.session 复用连接池，增加超时时间
        order_timeout = max(self.timeout, 15)
        response = self.session.get(url, params=params, headers=self._get_headers(), timeout=order_timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_order(self, symbol: str, order_id: Optional[int] = None,
                  client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """查询单个订单详情（包含 avgPrice/stopPrice 等字段）
        
        Args:
            symbol: 交易对
            order_id: 系统订单号（二选一）
            client_order_id: 客户端订单号（二选一）
        
        Returns:
            订单详情字典
        """
        url = f"{self.base_url}/fapi/v1/order"
        params = {
            'symbol': symbol,
            'timestamp': int(time.time() * 1000)
        }
        if order_id is not None:
            params['orderId'] = order_id
        elif client_order_id is not None:
            params['origClientOrderId'] = client_order_id
        else:
            raise ValueError("必须提供 order_id 或 client_order_id")
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        # 使用 self.session 复用连接池
        response = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_account(self) -> Dict[str, Any]:
        """查询账户信息（V3版本）
        
        Returns:
            账户信息
            
        Note:
            使用 V3 API 获取账户信息，包含余额、持仓、保证金等完整数据
            参考：https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3
        """
        url = f"{self.base_url}/fapi/v3/account"
        
        params = {
            'timestamp': int(time.time() * 1000)
        }
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        # 使用 self.session 复用连接池
        response = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_position_risk(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询持仓信息
        
        Args:
            symbol: 交易对（可选）
            
        Returns:
            持仓列表
        """
        url = f"{self.base_url}/fapi/v2/positionRisk"
        
        params = {
            'timestamp': int(time.time() * 1000)
        }
        
        if symbol:
            params['symbol'] = symbol
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        # 使用 self.session 复用连接池
        response = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """设置杠杆
        
        Args:
            symbol: 交易对
            leverage: 杠杆倍数（1-125）
            
        Returns:
            响应
        """
        url = f"{self.base_url}/fapi/v1/leverage"
        
        params = {
            'symbol': symbol,
            'leverage': leverage,
            'timestamp': int(time.time() * 1000)
        }
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        response = self.session.post(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def set_position_mode(self, dual_side: bool = False) -> Dict[str, Any]:
        """设置持仓模式
        
        Args:
            dual_side: True=双向持仓（Hedge Mode），False=单向持仓（One-way Mode）
            
        Returns:
            设置结果
        """
        url = f"{self.base_url}/fapi/v1/positionSide/dual"
        
        params = {
            'dualSidePosition': 'true' if dual_side else 'false',
            'timestamp': int(time.time() * 1000)
        }
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        response = self.session.post(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_position_mode(self) -> Dict[str, Any]:
        """查询持仓模式
        
        Returns:
            {'dualSidePosition': True/False}
        """
        url = f"{self.base_url}/fapi/v1/positionSide/dual"
        
        params = {
            'timestamp': int(time.time() * 1000)
        }
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        # 使用 self.session 复用连接池
        response = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=1.0, exceptions=(requests.RequestException,))
    def create_listen_key(self) -> Dict[str, Any]:
        """创建用户数据流 listenKey
        
        Returns:
            包含 listenKey 的响应
        """
        url = f"{self.base_url}/fapi/v1/listenKey"
        
        response = self.session.post(url, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=1.0, exceptions=(requests.RequestException,))
    def keepalive_listen_key(self) -> Dict[str, Any]:
        """保活用户数据流 listenKey
        
        Returns:
            响应
        """
        url = f"{self.base_url}/fapi/v1/listenKey"
        
        # 使用 self.session 复用连接池
        response = self.session.put(url, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_all_orders(self, symbol: str, order_id: Optional[int] = None,
                       start_time: Optional[int] = None, end_time: Optional[int] = None,
                       limit: int = 500) -> List[Dict[str, Any]]:
        """查询所有订单（包括历史订单）
        
        Args:
            symbol: 交易对
            order_id: 起始订单ID（可选）
            start_time: 起始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            limit: 返回数量限制（默认500，最大1000）
            
        Returns:
            订单列表
            
        Note:
            - 查询时间范围不能超过7天
            - 如果设置了 orderId，则返回订单ID大于等于该值的订单
        """
        url = f"{self.base_url}/fapi/v1/allOrders"
        
        params = {
            'symbol': symbol,
            'limit': min(limit, 1000),
            'timestamp': int(time.time() * 1000)
        }
        
        if order_id is not None:
            params['orderId'] = order_id
        if start_time is not None:
            params['startTime'] = start_time
        if end_time is not None:
            params['endTime'] = end_time
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        response = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_user_trades(self, symbol: str, start_time: Optional[int] = None,
                        end_time: Optional[int] = None, from_id: Optional[int] = None,
                        limit: int = 500) -> List[Dict[str, Any]]:
        """查询账户成交历史
        
        Args:
            symbol: 交易对
            start_time: 起始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            from_id: 起始成交ID
            limit: 返回数量限制（默认500，最大1000）
            
        Returns:
            成交记录列表
            
        Note:
            - 查询时间范围不能超过7天
        """
        url = f"{self.base_url}/fapi/v1/userTrades"
        
        params = {
            'symbol': symbol,
            'limit': min(limit, 1000),
            'timestamp': int(time.time() * 1000)
        }
        
        if start_time is not None:
            params['startTime'] = start_time
        if end_time is not None:
            params['endTime'] = end_time
        if from_id is not None:
            params['fromId'] = from_id
        
        # 签名
        params['signature'] = self._sign_request(params)
        
        response = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def test_connection(self) -> bool:
        """测试连接
        
        Returns:
            是否连接成功
        """
        try:
            url = f"{self.base_url}/fapi/v1/ping"
            response = self.session.get(url, timeout=self.timeout)
            return response.status_code == 200
        except Exception:
            return False

