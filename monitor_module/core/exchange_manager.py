"""交易对管理器"""
from typing import List, Dict
from ..clients.binance_rest import BinanceRestClient
from ..utils.logger import get_logger

logger = get_logger('exchange_manager')


class ExchangeManager:
    """交易对管理器"""
    
    def __init__(self, rest_client: BinanceRestClient, config: Dict):
        """初始化
        
        Args:
            rest_client: REST API客户端
            config: 配置字典
        """
        self.rest_client = rest_client
        self.config = config
        self.symbols_config = config['symbols']
    
    def get_tradable_symbols(self) -> List[str]:
        """获取可交易的交易对列表
        
        Returns:
            交易对符号列表
        """
        logger.info("获取USDT永续合约交易对列表...")
        
        # 获取所有USDT永续合约
        min_volume = self.symbols_config.get('min_volume_24h', 0)
        symbols = self.rest_client.get_all_usdt_perpetual_symbols(min_volume)
        
        # 应用排除列表
        exclude_list = self.symbols_config.get('exclude', [])
        if exclude_list:
            symbols = [s for s in symbols if s not in exclude_list]
            logger.info(f"排除{len(exclude_list)}个交易对")
        
        logger.info(f"获取到{len(symbols)}个可交易的USDT永续合约")
        
        return symbols
    
    def group_symbols(self, symbols: List[str], max_per_group: int = 1024) -> List[List[str]]:
        """将交易对分组（用于多WebSocket连接）
        
        Args:
            symbols: 交易对列表
            max_per_group: 每组最大数量
            
        Returns:
            分组后的交易对列表
        """
        groups = [
            symbols[i:i + max_per_group]
            for i in range(0, len(symbols), max_per_group)
        ]
        
        logger.info(f"交易对分为{len(groups)}组")
        for i, group in enumerate(groups):
            logger.info(f"  组{i+1}: {len(group)}个交易对")
        
        return groups
    
    def validate_symbols(self, symbols: List[str]) -> List[str]:
        """验证交易对有效性
        
        Args:
            symbols: 交易对列表
            
        Returns:
            有效的交易对列表
        """
        valid_symbols = []
        
        for symbol in symbols:
            if len(symbol) >= 6 and symbol.isupper():
                valid_symbols.append(symbol)
            else:
                logger.warning(f"无效的交易对符号: {symbol}")
        
        return valid_symbols

