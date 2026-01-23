"""系统初始化器"""
import time
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..clients.binance_rest import BinanceRestClient
from ..data.kline_manager import KlineManager
from ..data.models import Kline
from ..utils.logger import get_logger

logger = get_logger('initializer')


class SystemInitializer:
    """系统初始化器 - 负责启动时的数据预加载"""
    
    def __init__(self, rest_client: BinanceRestClient, kline_manager: KlineManager, config: Dict):
        """初始化
        
        Args:
            rest_client: REST API客户端
            kline_manager: K线管理器
            config: 配置字典
        """
        self.rest_client = rest_client
        self.kline_manager = kline_manager
        self.config = config
        
        self.interval = config['kline']['interval']
        self.warmup_size = config['kline']['warmup_size']
    
    def initialize_historical_data(self, symbols: List[str]) -> bool:
        """初始化历史数据（并发获取）
        
        Args:
            symbols: 交易对列表
            
        Returns:
            是否成功
        """
        logger.info(f"开始初始化历史数据: {len(symbols)}个交易对, {self.warmup_size}根K线/交易对")
        start_time = time.time()
        
        success_count = 0
        failed_symbols = []
        
        # 使用线程池并发获取
        max_workers = min(10, len(symbols))  # 最多10个并发
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_symbol = {
                executor.submit(self._fetch_and_store_klines, symbol): symbol
                for symbol in symbols
            }
            
            # 处理完成的任务
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    success = future.result()
                    if success:
                        success_count += 1
                    else:
                        failed_symbols.append(symbol)
                    
                    # 每完成10%输出进度
                    if success_count % max(1, len(symbols) // 10) == 0:
                        progress = (success_count / len(symbols)) * 100
                        logger.info(f"初始化进度: {progress:.1f}% ({success_count}/{len(symbols)})")
                
                except Exception as e:
                    logger.error(f"初始化{symbol}失败: {e}")
                    failed_symbols.append(symbol)
        
        elapsed = time.time() - start_time
        logger.info(f"历史数据初始化完成: 成功{success_count}个, 失败{len(failed_symbols)}个, 耗时{elapsed:.2f}秒")
        
        if failed_symbols:
            logger.warning(f"失败的交易对: {', '.join(failed_symbols[:10])}")
            if len(failed_symbols) > 10:
                logger.warning(f"  ... 还有{len(failed_symbols) - 10}个")
        
        return success_count > 0
    
    def _fetch_and_store_klines(self, symbol: str) -> bool:
        """获取并存储K线数据
        
        Args:
            symbol: 交易对符号
            
        Returns:
            是否成功
        """
        try:
            # 获取历史K线
            raw_klines = self.rest_client.get_klines(
                symbol=symbol,
                interval=self.interval,
                limit=self.warmup_size
            )
            
            if not raw_klines:
                logger.warning(f"{symbol}: 未获取到K线数据")
                return False
            
            # 转换为Kline对象
            klines = [Kline.from_rest_api(k) for k in raw_klines]
            
            # 排除最后一根（可能是未完结的当前周期K线）
            # 避免与实时WebSocket数据重复
            klines_to_store = klines[:-1] if len(klines) > 1 else klines
            
            # 存储到管理器
            self.kline_manager.initialize_symbol(symbol, klines_to_store)
            
            return True
        
        except Exception as e:
            logger.error(f"{symbol}: 获取K线失败 - {e}")
            return False
    
    def verify_initialization(self, symbols: List[str], min_required: int) -> bool:
        """验证初始化结果
        
        Args:
            symbols: 交易对列表
            min_required: 最小要求的K线数量
            
        Returns:
            是否满足要求
        """
        insufficient = []
        
        for symbol in symbols:
            if not self.kline_manager.has_enough_data(symbol, min_required):
                insufficient.append(symbol)
        
        if insufficient:
            logger.warning(f"{len(insufficient)}个交易对的数据不足{min_required}根K线")
            return False
        
        logger.info(f"所有{len(symbols)}个交易对的数据充足")
        return True

