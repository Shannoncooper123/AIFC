"""FastAPI 主应用入口"""
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import alerts, backtest, config, positions, system, workflow
from app.api.websocket import router as websocket_router
from app.core.config import get_settings
from app.services.thread_manager import thread_manager


class FlushingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
handler = FlushingStreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
root_logger.addHandler(handler)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Crypto Monitor Backend 启动中...")
    logger.info("=" * 60)
    
    logger.info("服务已就绪，等待手动启动 Monitor 和 Workflow...")
    logger.info("提示: 通过 API /api/system/start 或前端控制面板启动服务")
    
    logger.info("=" * 60)
    logger.info("✅ Backend 启动完成")
    logger.info("=" * 60)
    
    yield
    
    logger.info("=" * 60)
    logger.info("Crypto Monitor Backend 关闭中...")
    logger.info("=" * 60)
    
    logger.info("停止所有服务线程...")
    thread_manager.stop_all()
    
    logger.info("关闭图表渲染进程池...")
    try:
        from modules.agent.tools.chart_renderer import shutdown_chart_renderer
        shutdown_chart_renderer()
    except Exception as e:
        logger.warning(f"关闭图表渲染进程池失败: {e}")
    
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
app.include_router(backtest.router)
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
