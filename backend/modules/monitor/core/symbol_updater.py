"""交易对动态更新管理器"""
import time
import threading
from typing import List, Set, Dict, Callable
from ..clients.binance_rest import BinanceRestClient
from ..utils.logger import get_logger

logger = get_logger('symbol_updater')


class SymbolUpdater:
    """交易对动态更新管理器"""
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        config: Dict,
        on_symbols_changed: Callable[[List[str], List[str]], None]
    ):
        """初始化
        
        Args:
            rest_client: REST API客户端
            config: 配置字典
            on_symbols_changed: 交易对变化回调函数(added, removed)
        """
        self.rest_client = rest_client
        self.config = config
        self.on_symbols_changed = on_symbols_changed
        
        # 配置参数
        self.update_interval = config.get('symbols', {}).get('update_interval_minutes', 15) * 60
        self.min_volume = config['symbols'].get('min_volume_24h', 0)
        self.exclude_list = config['symbols'].get('exclude', [])
        
        # 当前监控的交易对集合
        self.current_symbols: Set[str] = set()
        
        # 更新线程控制
        self._running = False
        self._update_thread = None
    
    def start(self, initial_symbols: List[str]):
        """启动动态更新
        
        Args:
            initial_symbols: 初始交易对列表
        """
        self.current_symbols = set(initial_symbols)
        self._running = True
        
        logger.info(f"启动交易对动态更新器（更新间隔: {self.update_interval/60:.0f}分钟）")
        
        # 启动更新线程
        self._update_thread = threading.Thread(
            target=self._update_loop,
            daemon=True,
            name="SymbolUpdater"
        )
        self._update_thread.start()
    
    def stop(self):
        """停止动态更新"""
        logger.info("停止交易对动态更新器...")
        self._running = False
        
        if self._update_thread and self._update_thread.is_alive():
            self._update_thread.join(timeout=5)
    
    def _update_loop(self):
        """更新循环"""
        while self._running:
            try:
                # 等待更新间隔
                time.sleep(self.update_interval)
                
                if not self._running:
                    break
                
                # 执行更新检查
                self._check_and_update()
                
            except Exception as e:
                logger.error(f"交易对更新出错: {e}")
    
    def _check_and_update(self):
        """检查并更新交易对列表"""
        try:
            logger.info("检查交易对列表更新...")
            
            # 获取最新的符合条件的交易对
            latest_symbols = self._get_qualified_symbols()
            latest_set = set(latest_symbols)
            
            # 计算差异
            added = latest_set - self.current_symbols
            removed = self.current_symbols - latest_set
            
            if not added and not removed:
                logger.info("  无交易对变化")
                return
            
            # 记录变化
            if added:
                added_list = sorted(added)
                logger.info(f"  新增交易对 ({len(added)}): {', '.join(added_list[:5])}"
                           f"{'...' if len(added) > 5 else ''}")
            
            if removed:
                removed_list = sorted(removed)
                logger.info(f"  移除交易对 ({len(removed)}): {', '.join(removed_list[:5])}"
                           f"{'...' if len(removed) > 5 else ''}")
            
            # 更新当前列表
            self.current_symbols = latest_set
            
            # 触发回调
            if self.on_symbols_changed:
                self.on_symbols_changed(list(added), list(removed))
                
        except Exception as e:
            logger.error(f"检查交易对更新失败: {e}")
    
    def _get_qualified_symbols(self) -> List[str]:
        """获取符合条件的交易对列表
        
        Returns:
            交易对列表
        """
        # 获取所有USDT永续合约
        symbols = self.rest_client.get_all_usdt_perpetual_symbols(self.min_volume)
        
        # 应用排除列表
        if self.exclude_list:
            symbols = [s for s in symbols if s not in self.exclude_list]
        
        return symbols
    
    def force_update(self):
        """立即强制更新（用于手动触发）"""
        logger.info("强制更新交易对列表...")
        self._check_and_update()
    
    def get_current_symbols(self) -> List[str]:
        """获取当前监控的交易对列表"""
        return sorted(list(self.current_symbols))
    
    def get_symbol_count(self) -> int:
        """获取当前监控的交易对数量"""
        return len(self.current_symbols)

