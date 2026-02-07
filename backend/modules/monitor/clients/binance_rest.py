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
from ..utils.logger import get_logger

logger = get_logger('binance_rest')


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
    
    def close(self):
        """关闭 Session 连接池"""
        if self.session:
            self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
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
    
    @retry_on_exception(max_retries=3, delay=0.5, exceptions=(requests.RequestException,))
    def get_ticker_price(self, symbol: Optional[str] = None) -> Any:
        """获取最新价格
        
        使用 /fapi/v1/ticker/price 接口，返回最新成交价格。
        
        Args:
            symbol: 交易对符号（None表示获取所有）
            
        Returns:
            最新价格数据，包含：
            - symbol: 交易对
            - price: 最新价格
            - time: 更新时间
        """
        url = f"{self.base_url}/fapi/v1/ticker/price"
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=3, delay=0.5, exceptions=(requests.RequestException,))
    def get_mark_price(self, symbol: Optional[str] = None) -> Any:
        """获取标记价格和资金费率
        
        Args:
            symbol: 交易对符号（None表示获取所有）
            
        Returns:
            标记价格数据，包含：
            - symbol: 交易对
            - markPrice: 标记价格
            - indexPrice: 指数价格
            - estimatedSettlePrice: 预估结算价
            - lastFundingRate: 最近资金费率
            - nextFundingTime: 下次资金费时间
            - interestRate: 利率
            - time: 更新时间
        """
        url = f"{self.base_url}/fapi/v1/premiumIndex"
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
                    working_type: str = 'MARK_PRICE',
                    position_side: str = 'BOTH') -> Dict[str, Any]:
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
            position_side: 持仓方向（BOTH/LONG/SHORT），双向持仓模式下需指定
            
        Returns:
            订单响应
        """
        url = f"{self.base_url}/fapi/v1/order"
        
        # 使用最新时间戳，避免过期（币安要求5000ms窗口内）
        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'positionSide': position_side,
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
        if not response.ok:
            logger.error(f"Algo Order API 错误: {response.status_code} - {response.text}")
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
    
    @retry_on_exception(max_retries=3, delay=1.0, exceptions=(requests.RequestException,))
    def change_position_mode(self, dual_side_position: bool) -> Dict[str, Any]:
        """更改持仓模式
        
        变换用户在所有 symbol 合约上的持仓模式：双向持仓或单向持仓
        
        Args:
            dual_side_position: True 为双向持仓模式，False 为单向持仓模式
            
        Returns:
            {'code': 200, 'msg': 'success'}
            
        Note:
            - 只有在没有持仓和挂单的情况下才能更改持仓模式
            - 参考：https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode
        """
        url = f"{self.base_url}/fapi/v1/positionSide/dual"
        
        params = {
            'dualSidePosition': 'true' if dual_side_position else 'false',
            'timestamp': int(time.time() * 1000)
        }
        
        params['signature'] = self._sign_request(params)
        
        response = self.session.post(url, params=params, headers=self._get_headers(), timeout=self.timeout)
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
    def get_user_trades(self, symbol: str, order_id: Optional[int] = None,
                        start_time: Optional[int] = None, end_time: Optional[int] = None, 
                        from_id: Optional[int] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """查询账户成交历史
        
        Args:
            symbol: 交易对
            order_id: 订单ID，查询特定订单的成交记录（推荐使用，更精确）
            start_time: 起始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            from_id: 起始成交ID（不能与 startTime/endTime 一起使用）
            limit: 返回数量限制（默认500，最大1000）
            
        Returns:
            成交记录列表，每条包含 orderId, price, qty, commission, realizedPnl 等
            
        Note:
            - 查询时间范围不能超过7天
            - 使用 orderId 可以精确查询特定订单的所有成交记录
        """
        url = f"{self.base_url}/fapi/v1/userTrades"
        
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
        if from_id is not None:
            params['fromId'] = from_id
        
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
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def place_algo_order(self, symbol: str, side: str, algo_type: str,
                         trigger_price: float, quantity: float,
                         order_type: str = 'MARKET',
                         price: Optional[float] = None,
                         time_in_force: str = 'GTC',
                         working_type: str = 'MARK_PRICE',
                         good_till_date: Optional[int] = None,
                         position_side: str = 'BOTH') -> Dict[str, Any]:
        """创建条件单 (Algo Order)
        
        Args:
            symbol: 交易对
            side: BUY/SELL
            algo_type: 条件单类型（CONDITIONAL）
            trigger_price: 触发价格
            quantity: 数量
            order_type: 订单类型（MARKET/LIMIT）
            price: 限价单价格（仅 LIMIT 类型需要）
            time_in_force: 有效方式（GTC/IOC/FOK）
            working_type: 触发价格类型（MARK_PRICE/CONTRACT_PRICE）
            good_till_date: 过期时间戳（毫秒），超过此时间自动取消
            position_side: 持仓方向（BOTH/LONG/SHORT）
            
        Returns:
            条件单响应
            
        Note:
            参考：https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order
        """
        url = f"{self.base_url}/fapi/v1/algoOrder"
        
        params = {
            'symbol': symbol,
            'side': side,
            'algoType': algo_type,
            'triggerPrice': trigger_price,
            'quantity': quantity,
            'type': order_type,
            'workingType': working_type,
            'positionSide': position_side,
            'timestamp': int(time.time() * 1000)
        }
        
        if order_type == 'LIMIT' and price is not None:
            params['price'] = price
            params['timeInForce'] = time_in_force
        
        if good_till_date is not None:
            params['goodTillDate'] = good_till_date
        
        params['signature'] = self._sign_request(params)
        
        order_timeout = max(self.timeout, 20)
        response = self.session.post(url, params=params, headers=self._get_headers(), timeout=order_timeout)
        if not response.ok:
            logger.error(f"[Algo Order] API 错误: {response.status_code} - {response.text}")
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def cancel_algo_order(self, algo_id: int) -> Dict[str, Any]:
        """撤销条件单
        
        Args:
            algo_id: 条件单ID
            
        Returns:
            撤销响应
            
        Note:
            参考：https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Cancel-Algo-Order
        """
        url = f"{self.base_url}/fapi/v1/algoOrder"
        
        params = {
            'algoId': algo_id,
            'timestamp': int(time.time() * 1000)
        }
        
        params['signature'] = self._sign_request(params)
        
        order_timeout = max(self.timeout, 15)
        response = self.session.delete(url, params=params, headers=self._get_headers(), timeout=order_timeout)
        response.raise_for_status()
        return response.json()
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_algo_open_orders(self, symbol: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """查询当前条件单
        
        Args:
            symbol: 交易对（可选）
            
        Returns:
            条件单列表，查询失败时返回 None（而不是空列表，以区分"没有条件单"和"查询失败"）
            
        Note:
            参考：https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Algo-Open-Orders
            正确端点：GET /fapi/v1/openAlgoOrders
        """
        url = f"{self.base_url}/fapi/v1/openAlgoOrders"
        
        params = {
            'timestamp': int(time.time() * 1000)
        }
        
        if symbol:
            params['symbol'] = symbol
        
        params['signature'] = self._sign_request(params)
        
        try:
            response = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"[Algo Order] 查询条件单失败: {e}")
            return None
    
    @retry_on_exception(max_retries=5, delay=0.5, exceptions=(requests.RequestException,))
    def get_algo_order_history(self, symbol: Optional[str] = None,
                                start_time: Optional[int] = None,
                                end_time: Optional[int] = None,
                                limit: int = 100) -> List[Dict[str, Any]]:
        """查询条件单历史
        
        Args:
            symbol: 交易对（可选）
            start_time: 起始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            limit: 返回数量限制（默认100，最大1000）
            
        Returns:
            条件单历史列表
            
        Note:
            参考：https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Query-Historical-Algo-Orders
        """
        url = f"{self.base_url}/fapi/v1/algo/historyOrders"
        
        params = {
            'limit': min(limit, 1000),
            'timestamp': int(time.time() * 1000)
        }
        
        if symbol:
            params['symbol'] = symbol
        if start_time is not None:
            params['startTime'] = start_time
        if end_time is not None:
            params['endTime'] = end_time
        
        params['signature'] = self._sign_request(params)
        
        response = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        return result.get('orders', [])
    
    def place_tp_sl_algo_orders(self, symbol: str, position_side: str, quantity: float,
                                 tp_price: float, sl_price: float,
                                 working_type: str = 'MARK_PRICE') -> Dict[str, Any]:
        """下止盈止损条件单
        
        为已有持仓下止盈和止损条件单。
        根据当前价格动态选择正确的条件单类型，避免 "Order would immediately trigger" 错误。
        
        Args:
            symbol: 交易对
            position_side: 持仓方向 (LONG/SHORT)
            quantity: 平仓数量
            tp_price: 止盈价格
            sl_price: 止损价格
            working_type: 触发价格类型 (MARK_PRICE/CONTRACT_PRICE)
            
        Returns:
            {
                'tp_algo_id': str,  # 止盈条件单ID
                'sl_algo_id': str,  # 止损条件单ID
                'success': bool
            }
        """
        close_side = 'SELL' if position_side == 'LONG' else 'BUY'
        
        result = {
            'tp_algo_id': None,
            'sl_algo_id': None,
            'success': False
        }
        
        # 获取当前价格以动态选择条件单类型
        try:
            mark_price_data = self.get_mark_price(symbol)
            current_price = float(mark_price_data.get('markPrice', 0))
        except Exception as e:
            logger.warning(f"[TP/SL] 获取当前价格失败: {e}，使用默认订单类型")
            current_price = 0
        
        # 根据平仓方向和触发价与当前价的关系选择订单类型
        # - BUY + 触发价 > 当前价: STOP_MARKET
        # - BUY + 触发价 < 当前价: TAKE_PROFIT_MARKET
        # - SELL + 触发价 > 当前价: TAKE_PROFIT_MARKET
        # - SELL + 触发价 < 当前价: STOP_MARKET
        
        def get_order_type(side: str, trigger_price: float) -> str:
            if current_price <= 0:
                # 无法获取当前价格时使用默认逻辑
                return 'TAKE_PROFIT_MARKET' if trigger_price == tp_price else 'STOP_MARKET'
            
            if side == 'BUY':
                return 'STOP_MARKET' if trigger_price > current_price else 'TAKE_PROFIT_MARKET'
            else:
                return 'TAKE_PROFIT_MARKET' if trigger_price > current_price else 'STOP_MARKET'
        
        tp_order_type = get_order_type(close_side, tp_price)
        sl_order_type = get_order_type(close_side, sl_price)
        
        logger.info(f"[TP/SL] {symbol} 当前价格: {current_price}, 平仓方向: {close_side}")
        logger.info(f"[TP/SL] 止盈: {tp_price} → {tp_order_type}, 止损: {sl_price} → {sl_order_type}")
        
        try:
            tp_result = self._place_single_tp_sl_order(
                symbol=symbol,
                side=close_side,
                position_side=position_side,
                order_type=tp_order_type,
                trigger_price=tp_price,
                quantity=quantity,
                working_type=working_type
            )
            if tp_result and tp_result.get('algoId'):
                result['tp_algo_id'] = str(tp_result['algoId'])
                logger.info(f"[TP/SL] ✅ 止盈单创建成功: {symbol} algoId={result['tp_algo_id']} price={tp_price}")
        except requests.HTTPError as e:
            error_detail = ""
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text
            logger.error(f"[TP/SL] ❌ 止盈单创建失败: {symbol} price={tp_price} error={error_detail}")
        except Exception as e:
            logger.error(f"[TP/SL] ❌ 止盈单创建失败: {symbol} price={tp_price} error={e}")
        
        try:
            sl_result = self._place_single_tp_sl_order(
                symbol=symbol,
                side=close_side,
                position_side=position_side,
                order_type=sl_order_type,
                trigger_price=sl_price,
                quantity=quantity,
                working_type=working_type
            )
            if sl_result and sl_result.get('algoId'):
                result['sl_algo_id'] = str(sl_result['algoId'])
                logger.info(f"[TP/SL] ✅ 止损单创建成功: {symbol} algoId={result['sl_algo_id']} price={sl_price}")
        except requests.HTTPError as e:
            error_detail = ""
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text
            logger.error(f"[TP/SL] ❌ 止损单创建失败: {symbol} price={sl_price} error={error_detail}")
        except Exception as e:
            logger.error(f"[TP/SL] ❌ 止损单创建失败: {symbol} price={sl_price} error={e}")
        
        result['success'] = result['tp_algo_id'] is not None and result['sl_algo_id'] is not None
        return result
    
    def _place_single_tp_sl_order(self, symbol: str, side: str, position_side: str,
                                   order_type: str, trigger_price: float, quantity: float,
                                   working_type: str = 'MARK_PRICE') -> Dict[str, Any]:
        """下单个止盈/止损条件单
        
        Args:
            symbol: 交易对
            side: 买卖方向 (BUY/SELL)
            position_side: 持仓方向 (LONG/SHORT)
            order_type: 订单类型 (TAKE_PROFIT_MARKET/STOP_MARKET)
            trigger_price: 触发价格
            quantity: 数量
            working_type: 触发价格类型
            
        Returns:
            API 响应
        """
        price_precision = self._get_price_precision(symbol)
        qty_precision = self._get_quantity_precision(symbol)
        
        formatted_price = round(trigger_price, price_precision)
        formatted_qty = round(quantity, qty_precision)
        
        url = f"{self.base_url}/fapi/v1/algoOrder"
        
        params = {
            'algoType': 'CONDITIONAL',
            'symbol': symbol,
            'side': side,
            'positionSide': position_side,
            'type': order_type,
            'quantity': str(formatted_qty),
            'triggerPrice': str(formatted_price),
            'workingType': working_type,
            'timestamp': int(time.time() * 1000)
        }
        
        params['signature'] = self._sign_request(params)
        
        response = self.session.post(url, params=params, headers=self._get_headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def _get_price_precision(self, symbol: str) -> int:
        """获取交易对的价格精度"""
        try:
            exchange_info = self.get_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s.get('symbol') == symbol:
                    return s.get('pricePrecision', 4)
        except:
            pass
        return 4
    
    def _get_quantity_precision(self, symbol: str) -> int:
        """获取交易对的数量精度"""
        try:
            exchange_info = self.get_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s.get('symbol') == symbol:
                    return s.get('quantityPrecision', 3)
        except:
            pass
        return 3
    
    def cancel_algo_order(self, symbol: str, algo_id: str) -> bool:
        """取消条件单
        
        Args:
            symbol: 交易对
            algo_id: 条件单ID
            
        Returns:
            是否成功
        """
        url = f"{self.base_url}/fapi/v1/algoOrder"
        
        params = {
            'symbol': symbol,
            'algoId': algo_id,
            'timestamp': int(time.time() * 1000)
        }
        
        params['signature'] = self._sign_request(params)
        
        try:
            response = self.session.delete(url, params=params, headers=self._get_headers(), timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            logger.info(f"[Algo Order] ✅ 取消条件单成功: {symbol} algoId={algo_id}")
            return True
        except Exception as e:
            logger.error(f"[Algo Order] ❌ 取消条件单失败: {symbol} algoId={algo_id} error={e}")
            return False

