"""总览统计接口（只读，真实数据库聚合）。"""

import logging
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from app.db.dashboard import build_summary
from app.schemas.dashboard import DashboardSummary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["总览"])


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummary,
    summary="获取总览统计（正式数据 / 演示数据隔离）",
)
def query_dashboard_summary(
    demo: bool = Query(default=False, description="true 时只统计演示数据"),
) -> DashboardSummary:
    try:
        return build_summary(demo)
    except sqlite3.Error as error:
        logger.error(
            "读取总览统计失败", exc_info=(type(error), error, error.__traceback__)
        )
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": "读取总览统计失败，请稍后重试。"},
        ) from error
