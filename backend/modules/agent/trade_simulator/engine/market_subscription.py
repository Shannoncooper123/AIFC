"""WS订阅管理服务"""
from __future__ import annotations

from typing import Dict, List

from modules.agent.trade_simulator.storage import ConfigFacade
from modules.monitor.clients.binance_ws import MultiConnectionManager
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.trade_engine.market_subscription')


class MarketSubscriptionService:
    """WS订阅管理服务：封装连接重建与关闭逻辑"""
    def __init__(self, config: Dict, on_kline_callback):
        self.cfg = ConfigFacade(config)
        self.ws_manager = MultiConnectionManager(config, on_kline_callback)
        self.interval = self.cfg.ws_interval

    def rebuild(self, symbols: List[str]) -> None:
        try:
            if symbols:
                self.ws_manager.connect_all(symbols, self.interval)
                logger.info(f"WS订阅重建: symbols={symbols}, interval={self.interval}")
            else:
                self.ws_manager.close_all()
                logger.info("WS订阅重建: 当前无持仓，关闭所有订阅")
        except Exception as e:
            logger.error(f"WS订阅重建失败: {e}")

    def start(self, symbols: List[str]) -> None:
        self.rebuild(symbols)

    def stop(self) -> None:
        """停止订阅服务（带超时控制）"""
        try:
            import time
            start = time.time()
            logger.info("正在关闭所有 WebSocket 订阅...")
            self.ws_manager.close_all()
            elapsed = time.time() - start
            logger.info(f"✅ WS订阅服务停止，关闭所有 WebSocket 订阅（耗时 {elapsed:.1f}秒）")
        except Exception as e:
            logger.error(f"❌ WS订阅服务关闭失败: {e}")

