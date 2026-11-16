"""风险提醒接口：统计、列表、详情、已读与重新分析。"""

import logging
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from app.db.matters import get_matter
from app.db.risks import get_risk, list_risks, mark_risk_read
from app.schemas.risk import (
    MatterRisksResponse,
    MatterRiskSummary,
    RiskLevel,
    RiskListResponse,
    RiskRecord,
    RiskRefreshResult,
    RiskStatusFilter,
    RiskSummary,
    RiskType,
)
from app.services.risks.service import read_risk_summary, refresh_risks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["风险提醒"])


def _database_error(action: str, error: Exception) -> HTTPException:
    logger.error(
        "%s", action, exc_info=(type(error), error, error.__traceback__)
    )
    return HTTPException(
        status_code=500,
        detail={"code": "database_error", "message": f"{action}，请稍后重试。"},
    )


def _risk_not_found(risk_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "risk_not_found",
            "message": f"风险提醒 {risk_id} 不存在，可能已被删除或编号有误。",
        },
    )


def _matter_not_found(matter_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "matter_not_found",
            "message": f"事项 {matter_id} 不存在，无法读取关联风险。",
        },
    )


@router.get(
    "/risks/summary",
    response_model=RiskSummary,
    summary="获取风险统计（只读，不写入数据库）",
)
def query_risk_summary() -> RiskSummary:
    try:
        summary, _outcome = read_risk_summary()
    except sqlite3.Error as error:
        raise _database_error("读取风险统计失败", error) from error
    return summary


@router.post(
    "/risks/refresh",
    response_model=RiskRefreshResult,
    summary="主动重新分析风险",
)
def refresh_risk_alerts() -> RiskRefreshResult:
    try:
        sync_result, summary, _outcome = refresh_risks()
    except sqlite3.Error as error:
        raise _database_error("重新分析风险失败", error) from error
    return RiskRefreshResult(
        generated_at=summary.generated_at,
        created=sync_result["created"],
        updated=sync_result["updated"],
        revived=sync_result["revived"],
        resolved=sync_result["resolved"],
        summary=summary,
    )


@router.get(
    "/risks",
    response_model=RiskListResponse,
    summary="查询风险提醒列表",
)
def query_risks(
    risk_type: RiskType | None = None,
    level: RiskLevel | None = None,
    status: RiskStatusFilter = "unresolved",
    matter_id: int | None = Query(default=None, ge=1),
    task_id: int | None = Query(default=None, ge=1),
    material_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RiskListResponse:
    try:
        total, items = list_risks(
            risk_type=risk_type,
            level=level,
            status=status,
            matter_id=matter_id,
            task_id=task_id,
            material_id=material_id,
            limit=limit,
            offset=offset,
        )
    except sqlite3.Error as error:
        raise _database_error("读取风险列表失败", error) from error
    return RiskListResponse(
        total=total,
        items=[RiskRecord.model_validate(item) for item in items],
    )


@router.get(
    "/risks/{risk_id}",
    response_model=RiskRecord,
    summary="查询风险详情",
)
def query_risk(risk_id: int) -> RiskRecord:
    if risk_id <= 0:
        raise _risk_not_found(risk_id)
    try:
        risk = get_risk(risk_id)
    except sqlite3.Error as error:
        raise _database_error("读取风险详情失败", error) from error
    if risk is None:
        raise _risk_not_found(risk_id)
    return RiskRecord.model_validate(risk)


@router.patch(
    "/risks/{risk_id}/read",
    response_model=RiskRecord,
    summary="标记风险为已读",
)
def mark_read(risk_id: int) -> RiskRecord:
    if risk_id <= 0:
        raise _risk_not_found(risk_id)
    try:
        result, risk = mark_risk_read(risk_id)
    except sqlite3.Error as error:
        raise _database_error("标记已读失败", error) from error

    if result == "not_found" or risk is None:
        raise _risk_not_found(risk_id)
    if result == "resolved":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "risk_resolved",
                "message": "该风险已解决并归档，无需再次标记已读。",
            },
        )
    return RiskRecord.model_validate(risk)


@router.get(
    "/matters/{matter_id}/risks",
    response_model=MatterRisksResponse,
    summary="查询事项关联风险与整体摘要（只读，不写入数据库）",
)
def query_matter_risks(matter_id: int) -> MatterRisksResponse:
    if matter_id <= 0:
        raise _matter_not_found(matter_id)

    try:
        matter = get_matter(matter_id)
    except sqlite3.Error as error:
        raise _database_error("读取事项失败", error) from error
    if matter is None:
        raise _matter_not_found(matter_id)

    try:
        _summary, outcome = read_risk_summary()
        summary = outcome.matter_summaries.get(matter_id)
        if summary is None:
            raise _matter_not_found(matter_id)
        _total, items = list_risks(
            matter_id=matter_id,
            status="unresolved",
            limit=200,
            offset=0,
        )
    except sqlite3.Error as error:
        raise _database_error("读取事项风险失败", error) from error

    return MatterRisksResponse(
        summary=MatterRiskSummary.model_validate(summary),
        risks=[RiskRecord.model_validate(item) for item in items],
    )
