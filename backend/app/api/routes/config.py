"""配置 API 路由"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.core.config_manager import config_manager
from app.models.schemas import (
    ConfigResponse,
    ConfigSection,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
)


router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
async def get_all_config():
    """获取所有配置"""
    config = config_manager.get_config()
    sections = [
        ConfigSection(name=name, data=data)
        for name, data in config.items()
        if isinstance(data, dict)
    ]
    return ConfigResponse(sections=sections)


@router.get("/{section}")
async def get_config_section(section: str):
    """获取指定配置节"""
    config = config_manager.get_config(section)
    if not config:
        raise HTTPException(status_code=404, detail=f"配置节不存在: {section}")
    return {"section": section, "data": config}


@router.put("/{section}", response_model=ConfigUpdateResponse)
async def update_config_section(section: str, request: ConfigUpdateRequest):
    """
    更新指定配置节（支持热重载）
    
    更新后会自动：
    1. 写入 config.yaml 文件
    2. 更新内存中的配置缓存
    3. 通知订阅了该配置节的服务进行热重载
    4. 通过 WebSocket 广播 CONFIG_UPDATED 事件
    """
    success = await config_manager.update_section(section, request.data)
    
    if not success:
        raise HTTPException(status_code=500, detail=f"更新配置节 {section} 失败")
    
    return ConfigUpdateResponse(
        success=True,
        message=f"配置节 {section} 已更新并热重载",
    )


@router.post("/reload")
async def reload_config():
    """
    重新加载配置文件
    
    从磁盘重新读取 config.yaml，检测变更并通知相关服务热重载。
    适用于直接编辑 config.yaml 文件后的场景。
    """
    try:
        has_changes = await config_manager.reload()
        
        if has_changes:
            return {"success": True, "message": "配置已重新加载，检测到变更并已通知相关服务"}
        else:
            return {"success": True, "message": "配置已检查，无变更"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新加载配置失败: {str(e)}")


@router.get("/hash/current")
async def get_config_hash():
    """获取当前配置的hash值（用于检测变更）"""
    return {"hash": config_manager._config_hash}
