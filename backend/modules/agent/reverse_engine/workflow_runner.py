"""反向交易 Workflow 运行器

针对单个币种，每根K线定时触发 workflow 进行分析。
类似回测模式，但是实时运行。
"""

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from langchain_core.runnables import RunnableConfig

from modules.agent.builder import create_workflow
from modules.agent.engine import get_engine, set_engine
from modules.agent.state import AgentState
from modules.agent.utils.workflow_trace_storage import (
    generate_trace_id,
    record_workflow_start,
    record_workflow_end,
)
from modules.agent.utils.trace_utils import workflow_trace_context
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

logger = get_logger('reverse_engine.workflow_runner')


class ReverseWorkflowRunner:
    """反向交易 Workflow 运行器
    
    针对单个币种，每根K线定时触发 workflow 进行分析。
    
    工作流程：
    1. 订阅指定币种的 K 线数据
    2. 每根新 K 线收盘时触发 workflow 分析
    3. Agent 分析后如果开仓，反向交易引擎会自动创建反向条件单
    """
    
    def __init__(
        self,
        symbol: str,
        interval: str = "15m",
        on_workflow_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        """初始化
        
        Args:
            symbol: 交易对（如 "BTCUSDT"）
            interval: K线周期（如 "15m"）
            on_workflow_complete: workflow 完成回调
        """
        self.symbol = symbol
        self.interval = interval
        self.on_workflow_complete = on_workflow_complete
        
        self._running = False
        self._stop_requested = False
        self._thread: Optional[threading.Thread] = None
        self._last_kline_time: Optional[datetime] = None
        
        self._workflow_count = 0
        self._start_time: Optional[datetime] = None
        
        self._interval_seconds = self._parse_interval(interval)
        
        logger.info(f"ReverseWorkflowRunner 创建: symbol={symbol}, interval={interval}")
    
    def _parse_interval(self, interval: str) -> int:
        """将K线周期转换为秒数"""
        mapping = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400,
        }
        return mapping.get(interval, 900)
    
    def _get_next_kline_time(self) -> datetime:
        """计算下一根K线的收盘时间"""
        now = datetime.now(timezone.utc)
        timestamp = now.timestamp()
        
        aligned = (int(timestamp) // self._interval_seconds + 1) * self._interval_seconds
        return datetime.fromtimestamp(aligned, tz=timezone.utc)
    
    def _wait_for_next_kline(self) -> bool:
        """等待下一根K线收盘
        
        Returns:
            是否成功等待（False 表示被中断）
        """
        next_time = self._get_next_kline_time()
        
        while not self._stop_requested:
            now = datetime.now(timezone.utc)
            wait_seconds = (next_time - now).total_seconds()
            
            if wait_seconds <= 0:
                self._last_kline_time = next_time
                return True
            
            sleep_time = min(wait_seconds, 1.0)
            time.sleep(sleep_time)
        
        return False
    
    def _create_mock_alert(self) -> Dict[str, Any]:
        """创建模拟警报"""
        return {
            "type": "reverse_trigger",
            "symbols": [self.symbol],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "interval": self.interval,
            "source": "reverse_workflow_runner",
            "entries": [{
                "symbol": self.symbol,
                "price": 0.0,
                "price_change_rate": 0.0,
                "triggered_indicators": ["REVERSE_TRIGGER"],
                "engulfing_type": "非外包",
            }],
        }
    
    def _wrap_config(self, alert: Dict[str, Any], workflow_run_id: str) -> RunnableConfig:
        """包装 workflow 配置"""
        cfg = get_config()
        return RunnableConfig(
            configurable={
                "latest_alert": alert,
                "workflow_run_id": workflow_run_id,
                "current_trace_id": workflow_run_id,
                "is_reverse_mode": True,
            },
            recursion_limit=100,
            tags=["reverse_workflow"],
            run_name="reverse_workflow_run",
            metadata={"env": cfg.get('env', {}), "workflow_run_id": workflow_run_id}
        )
    
    def _run_workflow(self) -> Optional[str]:
        """执行一次 workflow 分析
        
        Returns:
            workflow_run_id，失败返回 None
        """
        cfg = get_config()
        workflow_run_id = generate_trace_id("rv")
        start_iso = datetime.now(timezone.utc).isoformat()
        
        try:
            mock_alert = self._create_mock_alert()
            record_workflow_start(workflow_run_id, mock_alert, cfg)
            
            logger.info(f"[反向] 触发 workflow 分析: {self.symbol} @ {self._last_kline_time}")
            
            graph = create_workflow(cfg)
            app = graph.compile()
            
            with workflow_trace_context(workflow_run_id):
                app.invoke(
                    AgentState(),
                    config=self._wrap_config(mock_alert, workflow_run_id)
                )
            
            record_workflow_end(workflow_run_id, start_iso, "success", cfg=cfg)
            
            self._workflow_count += 1
            logger.info(f"[反向] workflow 分析完成: {self.symbol} (第 {self._workflow_count} 次)")
            
            if self.on_workflow_complete:
                self.on_workflow_complete(workflow_run_id, {
                    "symbol": self.symbol,
                    "interval": self.interval,
                    "kline_time": self._last_kline_time.isoformat() if self._last_kline_time else None,
                    "workflow_count": self._workflow_count,
                })
            
            return workflow_run_id
            
        except Exception as e:
            logger.error(f"[反向] workflow 分析失败: {self.symbol} - {e}", exc_info=True)
            record_workflow_end(workflow_run_id, start_iso, "error", error=str(e), cfg=cfg)
            return None
    
    def _run_loop(self):
        """主运行循环"""
        self._running = True
        self._start_time = datetime.now(timezone.utc)
        
        logger.info(f"[反向] Workflow 运行器启动: {self.symbol} @ {self.interval}")
        logger.info(f"[反向] 每 {self._interval_seconds} 秒触发一次分析")
        
        while not self._stop_requested:
            try:
                if not self._wait_for_next_kline():
                    break
                
                self._run_workflow()
                
            except Exception as e:
                logger.error(f"[反向] 运行循环异常: {e}", exc_info=True)
                time.sleep(5)
        
        self._running = False
        logger.info(f"[反向] Workflow 运行器已停止: {self.symbol}")
    
    def start(self) -> bool:
        """启动运行器
        
        Returns:
            是否成功启动
        """
        if self._running:
            logger.warning(f"[反向] 运行器已在运行: {self.symbol}")
            return False
        
        self._stop_requested = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        return True
    
    def stop(self) -> None:
        """停止运行器"""
        if not self._running:
            return
        
        logger.info(f"[反向] 请求停止运行器: {self.symbol}")
        self._stop_requested = True
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
    
    def get_status(self) -> Dict[str, Any]:
        """获取运行状态"""
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "running": self._running,
            "workflow_count": self._workflow_count,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "last_kline_time": self._last_kline_time.isoformat() if self._last_kline_time else None,
        }
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running


class ReverseWorkflowManager:
    """反向交易 Workflow 管理器
    
    管理多个币种的 Workflow 运行器
    """
    
    def __init__(self):
        self._runners: Dict[str, ReverseWorkflowRunner] = {}
        self._lock = threading.RLock()
    
    def start_symbol(
        self,
        symbol: str,
        interval: str = "15m",
        on_workflow_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> bool:
        """启动指定币种的 workflow 运行器
        
        Args:
            symbol: 交易对
            interval: K线周期
            on_workflow_complete: workflow 完成回调
            
        Returns:
            是否成功启动
        """
        with self._lock:
            if symbol in self._runners and self._runners[symbol].is_running:
                logger.warning(f"[反向] 币种 {symbol} 已在运行")
                return False
            
            runner = ReverseWorkflowRunner(
                symbol=symbol,
                interval=interval,
                on_workflow_complete=on_workflow_complete,
            )
            
            if runner.start():
                self._runners[symbol] = runner
                logger.info(f"[反向] 币种 {symbol} workflow 运行器已启动")
                return True
            
            return False
    
    def stop_symbol(self, symbol: str) -> bool:
        """停止指定币种的 workflow 运行器
        
        Args:
            symbol: 交易对
            
        Returns:
            是否成功停止
        """
        with self._lock:
            if symbol not in self._runners:
                logger.warning(f"[反向] 币种 {symbol} 未在运行")
                return False
            
            self._runners[symbol].stop()
            del self._runners[symbol]
            logger.info(f"[反向] 币种 {symbol} workflow 运行器已停止")
            return True
    
    def stop_all(self) -> None:
        """停止所有运行器"""
        with self._lock:
            for symbol, runner in list(self._runners.items()):
                runner.stop()
            self._runners.clear()
            logger.info("[反向] 所有 workflow 运行器已停止")
    
    def get_running_symbols(self) -> List[str]:
        """获取正在运行的币种列表"""
        with self._lock:
            return [s for s, r in self._runners.items() if r.is_running]
    
    def get_status(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取运行状态
        
        Args:
            symbol: 指定币种，None 表示获取所有
            
        Returns:
            状态信息
        """
        with self._lock:
            if symbol:
                if symbol in self._runners:
                    return self._runners[symbol].get_status()
                return {"error": f"币种 {symbol} 未在运行"}
            
            return {
                "running_count": len([r for r in self._runners.values() if r.is_running]),
                "symbols": {s: r.get_status() for s, r in self._runners.items()},
            }
