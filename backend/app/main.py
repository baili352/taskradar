"""TaskRadar AI 后端入口。

启动方式（在 backend 目录下）：
    py -3.11 -m uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    analysis,
    dashboard,
    demo,
    health,
    materials,
    matters,
    risks,
    tasks,
)
from app.core.config import settings
from app.db.database import init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化数据库。"""
    init_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI 智能事项拆解与材料核验平台 - 后端服务",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)
app.include_router(demo.router, prefix=settings.api_prefix)
app.include_router(analysis.router, prefix=settings.api_prefix)
app.include_router(matters.router, prefix=settings.api_prefix)
app.include_router(tasks.router, prefix=settings.api_prefix)
app.include_router(materials.router, prefix=settings.api_prefix)
app.include_router(risks.router, prefix=settings.api_prefix)


@app.get("/", tags=["系统"], summary="服务信息")
def root() -> dict:
    """根路径，方便快速确认服务已启动。"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
