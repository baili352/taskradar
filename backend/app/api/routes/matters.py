"""我的事项接口：把第三阶段分析结果真实保存到 SQLite。"""

import logging
import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.db import matters as repository
from app.schemas.matter import MatterCreate, MatterRecord, MatterUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matters", tags=["我的事项"])

MatterListStatus = Literal["pending", "in_progress", "done"]


def _not_found(matter_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "matter_not_found",
            "message": f"事项 {matter_id} 不存在，可能已被删除或编号有误。",
        },
    )


def _database_error(action: str) -> HTTPException:
    logger.exception("事项数据库操作失败：%s", action)
    return HTTPException(
        status_code=500,
        detail={
            "code": "database_error",
            "message": "数据库操作失败，请稍后重试；若持续出现请检查后端日志。",
        },
    )


@router.post(
    "",
    response_model=MatterRecord,
    status_code=201,
    summary="创建并保存事项",
)
def create_matter(payload: MatterCreate) -> MatterRecord:
    """保存分析结果为事项；原文证据随记录一并写入数据库。"""
    try:
        return repository.create_matter(payload)
    except sqlite3.Error as exc:
        raise _database_error("create") from exc


@router.get(
    "",
    response_model=list[MatterRecord],
    summary="获取事项列表",
)
def list_matters(
    status: Annotated[MatterListStatus | None, Query(description="按状态筛选")] = None,
    keyword: Annotated[str | None, Query(max_length=100, description="按名称搜索")] = None,
    limit: Annotated[int | None, Query(ge=1, le=500, description="分页大小，不传返回全部")] = None,
    offset: Annotated[int, Query(ge=0, description="分页偏移")] = 0,
) -> list[MatterRecord]:
    try:
        return repository.list_matters(
            status=status, keyword=keyword, limit=limit, offset=offset
        )
    except sqlite3.Error as exc:
        raise _database_error("list") from exc


@router.get(
    "/{matter_id}",
    response_model=MatterRecord,
    summary="获取事项详情",
)
def get_matter(matter_id: int) -> MatterRecord:
    if matter_id <= 0:
        raise _not_found(matter_id)
    try:
        matter = repository.get_matter(matter_id)
    except sqlite3.Error as exc:
        raise _database_error("get") from exc
    if matter is None:
        raise _not_found(matter_id)
    return matter


@router.patch(
    "/{matter_id}",
    response_model=MatterRecord,
    summary="更新事项信息",
)
def update_matter(matter_id: int, payload: MatterUpdate) -> MatterRecord:
    if matter_id <= 0:
        raise _not_found(matter_id)
    try:
        matter = repository.update_matter(matter_id, payload)
    except sqlite3.Error as exc:
        raise _database_error("update") from exc
    if matter is None:
        raise _not_found(matter_id)
    return matter
