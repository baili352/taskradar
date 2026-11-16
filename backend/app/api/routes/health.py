"""健康检查接口：用于确认后端与数据库是否正常。"""

from datetime import datetime

from fastapi import APIRouter

from app.core.config import settings
from app.db.database import check_database

router = APIRouter(tags=["系统"])


@router.get("/health", summary="健康检查")
def health_check() -> dict:
    """返回服务状态、版本、运行环境与数据库连通性。"""
    db_ok = check_database()
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": "ok" if db_ok else "error",
        "time": datetime.now().isoformat(timespec="seconds"),
    }
