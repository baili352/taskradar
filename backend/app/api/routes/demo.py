"""参赛演示数据接口：状态、一键初始化、一键清理。

演示数据与正式数据通过 matters.is_demo 严格隔离；
清理接口只删除 is_demo = 1 的记录，不会影响正式数据。
"""

import logging
import sqlite3

from fastapi import APIRouter, HTTPException

from app.schemas.dashboard import DemoStatus
from app.services.demo.seed import clear_demo_data, get_demo_status, seed_demo_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["演示数据"])


def _database_error(action: str, error: Exception) -> HTTPException:
    logger.error("%s", action, exc_info=(type(error), error, error.__traceback__))
    return HTTPException(
        status_code=500,
        detail={"code": "database_error", "message": f"{action}，请稍后重试。"},
    )


@router.get(
    "/demo/status",
    response_model=DemoStatus,
    summary="查询演示数据状态",
)
def query_demo_status() -> DemoStatus:
    try:
        return get_demo_status()
    except sqlite3.Error as error:
        raise _database_error("读取演示数据状态失败", error) from error


@router.post(
    "/demo/seed",
    response_model=DemoStatus,
    summary="一键初始化演示数据（不影响正式数据）",
)
def seed_demo() -> DemoStatus:
    try:
        return seed_demo_data()
    except sqlite3.Error as error:
        raise _database_error("初始化演示数据失败", error) from error


@router.delete(
    "/demo/clear",
    response_model=DemoStatus,
    summary="清理演示数据（只删除演示事项，保留正式数据）",
)
def clear_demo() -> DemoStatus:
    try:
        status, _removed = clear_demo_data()
        return status
    except sqlite3.Error as error:
        raise _database_error("清理演示数据失败", error) from error
