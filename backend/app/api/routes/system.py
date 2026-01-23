"""系统状态 API 路由"""
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    LogsResponse,
    ServiceActionRequest,
    ServiceActionResponse,
    ServiceInfo,
    ServiceName,
    SystemStatusResponse,
)
from app.services.thread_manager import thread_manager


router = APIRouter(prefix="/api", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status():
    all_status = thread_manager.get_all_status()
    services = {
        name: ServiceInfo(
            name=info.name,
            status=info.status,
            pid=info.thread_id,
            started_at=info.started_at,
            error=info.error,
        )
        for name, info in all_status.items()
    }
    return SystemStatusResponse(services=services)


@router.get("/services/{service_name}", response_model=ServiceInfo)
async def get_service_status(service_name: ServiceName):
    svc = thread_manager.get_service(service_name.value)
    if not svc:
        raise HTTPException(status_code=404, detail=f"服务不存在: {service_name}")
    
    info = svc.info
    return ServiceInfo(
        name=info.name,
        status=info.status,
        pid=info.thread_id,
        started_at=info.started_at,
        error=info.error,
    )


@router.post("/services/{service_name}", response_model=ServiceActionResponse)
async def control_service(service_name: ServiceName, request: ServiceActionRequest):
    svc = thread_manager.get_service(service_name.value)
    if not svc:
        raise HTTPException(status_code=404, detail=f"服务不存在: {service_name}")
    
    action = request.action
    success = False
    message = ""
    
    if action == "start":
        success = thread_manager.start_service(service_name.value)
        message = f"服务 {service_name.value} 启动{'成功' if success else '失败'}"
    elif action == "stop":
        success = thread_manager.stop_service(service_name.value)
        message = f"服务 {service_name.value} 停止{'成功' if success else '失败'}"
    elif action == "restart":
        success = thread_manager.restart_service(service_name.value)
        message = f"服务 {service_name.value} 重启{'成功' if success else '失败'}"
    
    info = svc.info
    return ServiceActionResponse(
        success=success,
        message=message,
        service=ServiceInfo(
            name=info.name,
            status=info.status,
            pid=info.thread_id,
            started_at=info.started_at,
            error=info.error,
        ),
    )


@router.get("/services/{service_name}/logs", response_model=LogsResponse)
async def get_service_logs(service_name: ServiceName, lines: int = 100):
    logs = thread_manager.get_service_logs(service_name.value, lines)
    return LogsResponse(
        service=service_name.value,
        lines=logs,
        total=len(logs),
    )


@router.post("/services/start-all")
async def start_all_services():
    results = thread_manager.start_all()
    return {"success": all(results.values()), "results": results}


@router.post("/services/stop-all")
async def stop_all_services():
    results = thread_manager.stop_all()
    return {"success": all(results.values()), "results": results}
