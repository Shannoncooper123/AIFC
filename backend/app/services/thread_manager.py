"""线程管理器：管理服务线程的生命周期"""
import logging
import threading
import traceback
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.core.events import (
    emit_agent_status,
    emit_error,
    emit_log,
    emit_monitor_status,
)
from app.models.schemas import ServiceInfo, ServiceStatus


logger = logging.getLogger(__name__)


class ManagedService:
    
    def __init__(
        self,
        name: str,
        target_func: Callable[[], None],
        on_status_change: Optional[Callable[[str, ServiceStatus], None]] = None,
    ):
        self.name = name
        self.target_func = target_func
        self.on_status_change = on_status_change
        
        self._thread: Optional[threading.Thread] = None
        self._status = ServiceStatus.STOPPED
        self._started_at: Optional[datetime] = None
        self._error: Optional[str] = None
        self._stop_event = threading.Event()
        self._output_lines: List[str] = []
        self._max_output_lines = 1000
        self._lock = threading.Lock()
    
    @property
    def status(self) -> ServiceStatus:
        return self._status
    
    @status.setter
    def status(self, value: ServiceStatus):
        if self._status != value:
            self._status = value
            if self.on_status_change:
                try:
                    self.on_status_change(self.name, value)
                except Exception as e:
                    logger.error(f"状态变更回调失败: {e}")
    
    @property
    def thread_id(self) -> Optional[int]:
        return self._thread.ident if self._thread and self._thread.is_alive() else None
    
    @property
    def info(self) -> ServiceInfo:
        return ServiceInfo(
            name=self.name,
            status=self.status,
            thread_id=self.thread_id,
            started_at=self._started_at.isoformat() if self._started_at else None,
            error=self._error,
        )
    
    def add_log(self, line: str):
        with self._lock:
            self._output_lines.append(line)
            if len(self._output_lines) > self._max_output_lines:
                self._output_lines = self._output_lines[-self._max_output_lines:]
        emit_log("info", line, self.name)
    
    def get_recent_output(self, lines: int = 100) -> List[str]:
        with self._lock:
            return self._output_lines[-lines:]
    
    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()
    
    def start(self) -> bool:
        if self.status in (ServiceStatus.RUNNING, ServiceStatus.STARTING):
            logger.warning(f"服务 {self.name} 已在运行或正在启动")
            return False
        
        self.status = ServiceStatus.STARTING
        self._error = None
        self._stop_event.clear()
        
        with self._lock:
            self._output_lines = []
        
        def thread_wrapper():
            try:
                self._started_at = datetime.utcnow()
                self.status = ServiceStatus.RUNNING
                self.add_log(f"服务 {self.name} 已启动")
                logger.info(f"服务 {self.name} 已启动, Thread ID: {threading.current_thread().ident}")
                
                self.target_func()
                
                if not self._stop_event.is_set():
                    self._error = "服务意外退出"
                    self.status = ServiceStatus.ERROR
                    emit_error(f"{self.name} 意外退出", {"error": self._error})
                else:
                    self.status = ServiceStatus.STOPPED
                    
            except Exception as e:
                error_msg = f"{e}\n{traceback.format_exc()}"
                self._error = str(e)
                self.status = ServiceStatus.ERROR
                logger.error(f"服务 {self.name} 异常: {error_msg}")
                emit_error(f"{self.name} 异常", {"error": str(e)})
        
        try:
            self._thread = threading.Thread(
                target=thread_wrapper,
                name=f"service-{self.name}",
                daemon=True,
            )
            self._thread.start()
            return True
            
        except Exception as e:
            self._error = str(e)
            self.status = ServiceStatus.ERROR
            logger.error(f"启动服务 {self.name} 失败: {e}")
            emit_error(f"启动 {self.name} 失败", {"error": str(e)})
            return False
    
    def stop(self, timeout: float = 10.0) -> bool:
        if self.status == ServiceStatus.STOPPED:
            logger.warning(f"服务 {self.name} 已停止")
            return True
        
        if not self._thread:
            self.status = ServiceStatus.STOPPED
            return True
        
        self.status = ServiceStatus.STOPPING
        self._stop_event.set()
        
        try:
            self._thread.join(timeout=timeout)
            
            if self._thread.is_alive():
                logger.warning(f"服务 {self.name} 未在 {timeout}s 内退出")
                self._error = "停止超时"
                self.status = ServiceStatus.ERROR
                return False
            
            self._thread = None
            self.status = ServiceStatus.STOPPED
            logger.info(f"服务 {self.name} 已停止")
            return True
            
        except Exception as e:
            self._error = str(e)
            self.status = ServiceStatus.ERROR
            logger.error(f"停止服务 {self.name} 失败: {e}")
            return False
    
    def restart(self) -> bool:
        self.stop()
        return self.start()


_monitor_service: Optional[ManagedService] = None
_workflow_service: Optional[ManagedService] = None


def _run_monitor():
    from modules.monitor.main import run_monitor_service
    run_monitor_service(_monitor_service.is_stop_requested, _monitor_service.add_log)


def _run_workflow():
    from modules.agent.workflow_main import run_workflow_service
    run_workflow_service(_workflow_service.is_stop_requested, _workflow_service.add_log)


class ThreadManager:
    _instance: Optional["ThreadManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._services: Dict[str, ManagedService] = {}
        self._setup_services()
    
    def _on_status_change(self, name: str, status: ServiceStatus):
        if name == "monitor":
            emit_monitor_status(status.value)
        elif name == "workflow":
            emit_agent_status(status.value, {"service": name})
    
    def _setup_services(self):
        global _monitor_service, _workflow_service
        
        _monitor_service = ManagedService(
            name="monitor",
            target_func=_run_monitor,
            on_status_change=self._on_status_change,
        )
        self._services["monitor"] = _monitor_service
        
        _workflow_service = ManagedService(
            name="workflow",
            target_func=_run_workflow,
            on_status_change=self._on_status_change,
        )
        self._services["workflow"] = _workflow_service
    
    def get_service(self, name: str) -> Optional[ManagedService]:
        return self._services.get(name)
    
    def get_all_status(self) -> Dict[str, ServiceInfo]:
        return {name: svc.info for name, svc in self._services.items()}
    
    def start_service(self, name: str) -> bool:
        svc = self.get_service(name)
        if not svc:
            logger.error(f"未知服务: {name}")
            return False
        return svc.start()
    
    def stop_service(self, name: str) -> bool:
        svc = self.get_service(name)
        if not svc:
            logger.error(f"未知服务: {name}")
            return False
        return svc.stop()
    
    def restart_service(self, name: str) -> bool:
        svc = self.get_service(name)
        if not svc:
            logger.error(f"未知服务: {name}")
            return False
        return svc.restart()
    
    def start_all(self) -> Dict[str, bool]:
        results = {}
        for name in self._services:
            results[name] = self.start_service(name)
        return results
    
    def stop_all(self) -> Dict[str, bool]:
        results = {}
        for name in self._services:
            results[name] = self.stop_service(name)
        return results
    
    def get_service_logs(self, name: str, lines: int = 100) -> List[str]:
        svc = self.get_service(name)
        if not svc:
            return []
        return svc.get_recent_output(lines)


thread_manager = ThreadManager()
