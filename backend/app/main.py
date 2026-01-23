"""FastAPI 主应用入口"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import alerts, config, positions, system, workflow
from app.api.websocket import router as websocket_router
from app.core.config import get_settings
from app.services.thread_manager import thread_manager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Crypto Monitor Backend 启动中...")
    logger.info("=" * 60)
    
    yield
    
    logger.info("=" * 60)
    logger.info("Crypto Monitor Backend 关闭中...")
    logger.info("=" * 60)
    
    logger.info("停止所有服务线程...")
    thread_manager.stop_all()
    
    logger.info("Backend 已关闭")


settings = get_settings()

app = FastAPI(
    title="Crypto Monitor API",
    description="加密货币异动监控系统 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(alerts.router)
app.include_router(positions.router)
app.include_router(config.router)
app.include_router(workflow.router)
app.include_router(websocket_router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "Crypto Monitor API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
