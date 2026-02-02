"""反向交易 Workflow 运行器

针对单个币种，基于 WebSocket K线更新触发 workflow 进行分析。
"""

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import websocket
from langchain_core.runnables import RunnableConfig

from modules.agent.builder import create_workflow
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


def _ensure_trading_engine_initialized():
    """确保交易引擎已初始化"""
    from modules.agent.engine import get_engine, set_engine, ensure_engine
    
    if get_engine() is None:
        cfg = get_config()
        trading_mode = cfg.get('trading', {}).get('mode', 'simulator')
        
        if trading_mode == 'live':
            from modules.agent.live_engine import BinanceLiveEngine
            eng = BinanceLiveEngine(cfg)
            set_engine(eng)
            eng.start()
            logger.info("[反向] 实盘交易引擎已初始化")
        else:
            from modules.agent.trade_simulator.engine.simulator import TradeSimulatorEngine
            eng = TradeSimulatorEngine(cfg)
            set_engine(eng)
            eng.start()
            logger.info("[反向] 模拟交易引擎已初始化")


class ReverseWorkflowRunner:
    """反向交易 Workflow 运行器
    
    基于 WebSocket 监听 K 线更新，每根新 K 线收盘时触发 workflow 分析。
    
    工作流程：
    1. 启动时立即执行一次分析
    2. 建立 WebSocket 连接订阅 K 线数据
    3. 每根新 K 线收盘时触发 workflow 分析
    4. Agent 分析后如果开仓，反向交易引擎会自动创建反向条件单
    """
    
    WS_BASE_URL = "wss://fstream.binance.com/ws"
    
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
        self.symbol = symbol.upper()
        self.interval = interval
        self.on_workflow_complete = on_workflow_complete
        
        self._running = False
        self._stop_requested = False
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._last_kline_time: Optional[int] = None
        self._last_kline_close_time: Optional[int] = None
        
        self._workflow_count = 0
        self._start_time: Optional[datetime] = None
        self._workflow_lock = threading.Lock()
        self._workflow_running = False
        
        logger.info(f"ReverseWorkflowRunner 创建: symbol={symbol}, interval={interval}")
    
    def _create_mock_alert(self, kline_data: Optional[Dict] = None) -> Dict[str, Any]:
        """创建模拟警报"""
        price = 0.0
        if kline_data:
            price = float(kline_data.get('c', 0))
        
        return {
            "type": "reverse_trigger",
            "symbols": [self.symbol],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "interval": self.interval,
            "source": "reverse_workflow_runner",
            "entries": [{
                "symbol": self.symbol,
                "price": price,
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
    
    def _run_workflow(self, kline_data: Optional[Dict] = None, trigger_reason: str = "kline_close") -> Optional[str]:
        """执行一次 workflow 分析
        
        Args:
            kline_data: K线数据（可选）
            trigger_reason: 触发原因
        
        Returns:
            workflow_run_id，失败返回 None
        """
        with self._workflow_lock:
            if self._workflow_running:
                logger.warning(f"[反向] {self.symbol} workflow 正在运行中，跳过本次触发")
                return None
            self._workflow_running = True
        
        try:
            _ensure_trading_engine_initialized()
            
            cfg = get_config()
            workflow_run_id = generate_trace_id("rv")
            start_iso = datetime.now(timezone.utc).isoformat()
            
            mock_alert = self._create_mock_alert(kline_data)
            record_workflow_start(workflow_run_id, mock_alert, cfg)
            
            kline_time_str = ""
            if self._last_kline_close_time:
                kline_time_str = datetime.fromtimestamp(
                    self._last_kline_close_time / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M")
            
            logger.info(f"[反向] 触发 workflow 分析: {self.symbol} @ {self.interval} "
                       f"(原因: {trigger_reason}, K线时间: {kline_time_str})")
            
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
                    "kline_time": kline_time_str,
                    "workflow_count": self._workflow_count,
                    "trigger_reason": trigger_reason,
                })
            
            return workflow_run_id
            
        except Exception as e:
            logger.error(f"[反向] workflow 分析失败: {self.symbol} - {e}", exc_info=True)
            try:
                record_workflow_end(workflow_run_id, start_iso, "error", error=str(e), cfg=cfg)
            except:
                pass
            return None
        finally:
            with self._workflow_lock:
                self._workflow_running = False
    
    def _on_ws_message(self, ws, message):
        """WebSocket 消息回调"""
        try:
            data = json.loads(message)
            
            if data.get('e') != 'kline':
                return
            
            kline = data.get('k', {})
            is_closed = kline.get('x', False)
            close_time = kline.get('T', 0)
            
            if is_closed:
                if self._last_kline_close_time is None or close_time > self._last_kline_close_time:
                    self._last_kline_close_time = close_time
                    
                    logger.info(f"[反向] 检测到新 K 线收盘: {self.symbol} @ {self.interval}")
                    
                    threading.Thread(
                        target=self._run_workflow,
                        args=(kline, "kline_close"),
                        daemon=True
                    ).start()
        except Exception as e:
            logger.error(f"[反向] 处理 WebSocket 消息失败: {e}")
    
    def _on_ws_error(self, ws, error):
        """WebSocket 错误回调"""
        logger.error(f"[反向] WebSocket 错误 ({self.symbol}): {error}")
    
    def _on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket 关闭回调"""
        logger.info(f"[反向] WebSocket 连接关闭 ({self.symbol}): {close_status_code} - {close_msg}")
        
        if self._running and not self._stop_requested:
            logger.info(f"[反向] 5 秒后尝试重连 WebSocket ({self.symbol})")
            time.sleep(5)
            if self._running and not self._stop_requested:
                self._connect_ws()
    
    def _on_ws_open(self, ws):
        """WebSocket 连接成功回调"""
        logger.info(f"[反向] WebSocket 连接成功: {self.symbol} @ {self.interval}")
    
    def _connect_ws(self):
        """建立 WebSocket 连接"""
        stream_name = f"{self.symbol.lower()}@kline_{self.interval}"
        ws_url = f"{self.WS_BASE_URL}/{stream_name}"
        
        logger.info(f"[反向] 连接 WebSocket: {ws_url}")
        
        self._ws = websocket.WebSocketApp(
            ws_url,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
            on_open=self._on_ws_open,
        )
        
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 180, "ping_timeout": 10},
            daemon=True
        )
        self._ws_thread.start()
    
    def start(self) -> bool:
        """启动运行器
        
        Returns:
            是否成功启动
        """
        if self._running:
            logger.warning(f"[反向] 运行器已在运行: {self.symbol}")
            return False
        
        self._running = True
        self._stop_requested = False
        self._start_time = datetime.now(timezone.utc)
        
        logger.info(f"[反向] Workflow 运行器启动: {self.symbol} @ {self.interval}")
        
        logger.info(f"[反向] 启动时立即执行一次分析: {self.symbol}")
        threading.Thread(
            target=self._run_workflow,
            args=(None, "startup"),
            daemon=True
        ).start()
        
        self._connect_ws()
        
        return True
    
    def stop(self) -> None:
        """停止运行器"""
        if not self._running:
            return
        
        logger.info(f"[反向] 请求停止运行器: {self.symbol}")
        self._stop_requested = True
        self._running = False
        
        if self._ws:
            try:
                self._ws.close()
            except:
                pass
            self._ws = None
        
        logger.info(f"[反向] Workflow 运行器已停止: {self.symbol}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取运行状态"""
        last_kline_str = None
        if self._last_kline_close_time:
            last_kline_str = datetime.fromtimestamp(
                self._last_kline_close_time / 1000, tz=timezone.utc
            ).isoformat()
        
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "running": self._running,
            "workflow_count": self._workflow_count,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "last_kline_time": last_kline_str,
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
