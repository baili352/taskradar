"""材料清单、文件上传与核验接口。"""

import logging
import sqlite3
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.materials import (
    attach_file,
    create_generated_materials,
    create_material,
    delete_material,
    get_material,
    list_materials,
    progress_for_matter,
    save_verification,
    update_material,
)
from app.db.matters import get_matter
from app.schemas.material import (
    MaterialConfirm,
    MaterialCreate,
    MaterialEventRecord,
    MaterialGenerationResult,
    MaterialProgress,
    MaterialRecord,
    MaterialUpdate,
    MaterialVerification,
    MaterialVerificationCheck,
)
from app.services.documents.errors import DocumentError
from app.services.documents.reader import read_document
from app.services.materials.generator import build_materials_from_matter
from app.services.materials.storage import (
    delete_stored_file,
    resolve_stored_file,
    sanitize_filename,
    save_material_file,
)
from app.services.materials.verifier import verify_material

logger = logging.getLogger(__name__)

router = APIRouter(tags=["材料管理"])

MaterialStatusQuery = Literal[
    "missing", "pending", "qualified", "incomplete", "conflict", "uncertain"
]

_STATUS_LABELS = {
    "missing": "尚未提供",
    "pending": "已提供待核验",
    "qualified": "已确认符合",
    "incomplete": "信息不完整",
    "conflict": "存在冲突",
    "uncertain": "无法判断",
}

_MAX_UPLOAD_BYTES = settings.max_upload_mb * 1024 * 1024


def _material_not_found(material_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "material_not_found",
            "message": f"材料 {material_id} 不存在，可能已被删除或编号有误。",
        },
    )


def _matter_not_found(matter_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "matter_not_found",
            "message": f"事项 {matter_id} 不存在，无法读取或生成材料清单。",
        },
    )


def _database_error(action: str, error: Exception) -> HTTPException:
    logger.error(
        "%s", action, exc_info=(type(error), error, error.__traceback__)
    )
    return HTTPException(
        status_code=500,
        detail={"code": "database_error", "message": f"{action}，请稍后重试。"},
    )


def _storage_error(action: str, error: OSError) -> HTTPException:
    logger.error(
        "%s", action, exc_info=(type(error), error, error.__traceback__)
    )
    return HTTPException(
        status_code=500,
        detail={"code": "storage_error", "message": f"{action}，请稍后重试。"},
    )


def _require_material(material_id: int) -> dict:
    try:
        material = get_material(material_id)
    except sqlite3.Error as error:
        raise _database_error("读取材料失败", error) from error
    if material is None:
        raise _material_not_found(material_id)
    return material


def _require_matter(matter_id: int):
    if matter_id <= 0:
        raise _matter_not_found(matter_id)
    try:
        matter = get_matter(matter_id)
    except sqlite3.Error as error:
        raise _database_error("读取事项失败", error) from error
    if matter is None:
        raise _matter_not_found(matter_id)
    return matter


@router.post(
    "/matters/{matter_id}/materials/generate",
    response_model=MaterialGenerationResult,
    status_code=status.HTTP_201_CREATED,
    summary="按事项材料要求生成材料清单",
)
def generate_materials(matter_id: int) -> MaterialGenerationResult:
    matter = _require_matter(matter_id)
    candidates = build_materials_from_matter(matter)

    try:
        created_rows, skipped = create_generated_materials(matter_id, candidates)
    except sqlite3.Error as error:
        raise _database_error("写入材料清单失败", error) from error

    created = [MaterialRecord.model_validate(row) for row in created_rows]

    total_source = len(matter.materials)
    if total_source == 0:
        message = "该事项没有登记材料要求，暂无材料可生成。"
    elif not candidates:
        message = "材料要求中没有可用的材料名称，未生成材料。"
    elif not created:
        message = f"该事项的 {len(candidates)} 项材料都已生成过，未重复创建。"
    else:
        message = f"已生成 {len(created)} 项材料"
        message += f"，跳过 {skipped} 项重复材料。" if skipped else "。"

    return MaterialGenerationResult(
        matter_id=matter.id,
        created=len(created),
        skipped=skipped,
        total_source_materials=total_source,
        message=message,
        materials=created,
    )


@router.get(
    "/matters/{matter_id}/materials",
    response_model=list[MaterialRecord],
    summary="查询事项的材料清单",
)
def query_matter_materials(matter_id: int) -> list[MaterialRecord]:
    _require_matter(matter_id)
    try:
        return list_materials(matter_id=matter_id)
    except sqlite3.Error as error:
        raise _database_error("读取材料清单失败", error) from error


@router.get(
    "/matters/{matter_id}/materials/progress",
    response_model=MaterialProgress,
    summary="查询事项材料准备进度",
)
def query_material_progress(matter_id: int) -> MaterialProgress:
    _require_matter(matter_id)
    try:
        return MaterialProgress.model_validate(progress_for_matter(matter_id))
    except sqlite3.Error as error:
        raise _database_error("统计材料进度失败", error) from error


@router.post(
    "/matters/{matter_id}/materials",
    response_model=MaterialRecord,
    status_code=status.HTTP_201_CREATED,
    summary="手动新增材料",
)
def create_manual_material(matter_id: int, payload: MaterialCreate) -> MaterialRecord:
    _require_matter(matter_id)
    try:
        return create_material(matter_id, payload)
    except sqlite3.Error as error:
        raise _database_error("新增材料失败", error) from error


@router.get("/materials", response_model=list[MaterialRecord], summary="查询材料列表")
def query_materials(
    matter_id: int | None = Query(default=None, ge=1),
    status_filter: MaterialStatusQuery | None = Query(default=None, alias="status"),
) -> list[MaterialRecord]:
    try:
        return list_materials(matter_id=matter_id, status=status_filter)
    except sqlite3.Error as error:
        raise _database_error("读取材料列表失败", error) from error


@router.get(
    "/materials/{material_id}",
    response_model=MaterialRecord,
    summary="查询材料详情（含操作记录）",
)
def query_material(material_id: int) -> MaterialRecord:
    if material_id <= 0:
        raise _material_not_found(material_id)
    try:
        material = get_material(material_id, with_events=True)
    except sqlite3.Error as error:
        raise _database_error("读取材料详情失败", error) from error
    if material is None:
        raise _material_not_found(material_id)
    return MaterialRecord.model_validate(material)


@router.patch(
    "/materials/{material_id}",
    response_model=MaterialRecord,
    summary="修改材料名称与要求说明",
)
def modify_material(material_id: int, payload: MaterialUpdate) -> MaterialRecord:
    if material_id <= 0:
        raise _material_not_found(material_id)
    try:
        material = update_material(material_id, payload)
    except sqlite3.Error as error:
        raise _database_error("更新材料失败", error) from error
    if material is None:
        raise _material_not_found(material_id)
    return material


@router.delete(
    "/materials/{material_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除材料及其受控文件",
)
def remove_material(material_id: int) -> Response:
    if material_id <= 0:
        raise _material_not_found(material_id)
    material = _require_material(material_id)
    stored_path = material.get("file_path")

    # 先删除受控目录内的物理文件，再删除数据库记录：
    # 文件删除失败时保留记录，避免“记录已删但磁盘残留无法追踪的文件”。
    if stored_path and resolve_stored_file(str(stored_path)) is not None:
        if not delete_stored_file(str(stored_path)):
            logger.error("删除材料文件失败，material_id=%s", material_id)
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "storage_error",
                    "message": "删除材料文件失败，请稍后重试。",
                },
            )

    try:
        found, _ = delete_material(material_id)
    except sqlite3.Error as error:
        raise _database_error("删除材料失败", error) from error
    if not found:
        raise _material_not_found(material_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/materials/{material_id}/file",
    response_model=MaterialRecord,
    summary="上传材料文件（PDF / DOCX / TXT / PNG / JPG / JPEG）",
)
async def upload_material_file(
    material_id: int, file: UploadFile = File(...)
) -> MaterialRecord:
    material = _require_material(material_id)
    original_name = sanitize_filename(file.filename or "")
    content = await file.read(_MAX_UPLOAD_BYTES + 1)

    try:
        document = await run_in_threadpool(
            read_document, original_name, content, _MAX_UPLOAD_BYTES
        )
    except DocumentError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    except Exception:
        logger.exception("材料文档读取失败，材料编号=%s", material_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "document_read_failed",
                "message": "材料文档读取失败，请更换文件或稍后重试。",
            },
        ) from None

    try:
        relative_path = await run_in_threadpool(
            save_material_file, material["matter_id"], document.extension, content
        )
    except OSError as error:
        raise _storage_error("保存文件失败", error) from error

    previous_path = material.get("file_path")
    try:
        updated = attach_file(
            material_id=material_id,
            file_path=relative_path,
            original_filename=original_name,
            file_size=len(content),
            file_type=document.extension.lstrip(".").upper(),
        )
    except sqlite3.Error as error:
        delete_stored_file(relative_path)
        raise _database_error("记录文件信息失败", error) from error

    if updated is None:
        delete_stored_file(relative_path)
        raise _material_not_found(material_id)

    # 替换文件时清理旧文件，避免受控目录堆积无用文件。
    if previous_path and previous_path != relative_path:
        delete_stored_file(previous_path)

    return updated


@router.post(
    "/materials/{material_id}/verify",
    response_model=MaterialRecord,
    summary="执行规则核验",
)
async def run_verification(material_id: int) -> MaterialRecord:
    material = _require_material(material_id)
    stored_path = material.get("file_path")
    if not stored_path:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "file_missing",
                "message": "该材料尚未上传文件，请先上传材料后再执行核验。",
            },
        )

    path = resolve_stored_file(stored_path)
    if path is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "file_missing",
                "message": "数据库记录了文件路径，但受控目录中找不到该文件，请重新上传。",
            },
        )

    try:
        content = await run_in_threadpool(path.read_bytes)
    except OSError as error:
        raise _storage_error("读取文件失败", error) from error

    try:
        document = await run_in_threadpool(
            read_document,
            material.get("original_filename") or path.name,
            content,
            _MAX_UPLOAD_BYTES,
        )
    except DocumentError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    except Exception:
        logger.exception("材料文档读取失败，材料编号=%s", material_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "document_read_failed",
                "message": "材料文档读取失败，请更换文件或稍后重试。",
            },
        ) from None

    verification = await run_in_threadpool(verify_material, material, document)
    try:
        updated = save_verification(material_id, verification)
    except sqlite3.Error as error:
        raise _database_error("保存核验结果失败", error) from error
    if updated is None:
        raise _material_not_found(material_id)
    return updated


@router.post(
    "/materials/{material_id}/confirm",
    response_model=MaterialRecord,
    summary="人工确认或修改核验状态",
)
def confirm_verification(
    material_id: int, payload: MaterialConfirm
) -> MaterialRecord:
    material = _require_material(material_id)
    if not material.get("file_path"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "file_missing",
                "message": "该材料尚未上传文件，不能确认核验结果。",
            },
        )

    previous = material.get("verification")
    checks = list(previous.checks) if previous else []
    reasons = list(previous.reasons) if previous else []
    if payload.evidence_text:
        checks.append(
            MaterialVerificationCheck(
                key="manual_evidence",
                label="人工补充依据",
                status="pass",
                message=payload.note or "人工确认时补充的原文摘录。",
                excerpt=payload.evidence_text,
                location="人工填写",
            )
        )

    label = _STATUS_LABELS.get(payload.status, payload.status)
    summary = f"人工确认：{label}。"
    if payload.note:
        summary += payload.note

    verification = MaterialVerification(
        result=payload.status,
        source="manual",
        verified_at=datetime.now().isoformat(timespec="milliseconds"),
        summary=summary,
        checks=checks,
        reasons=reasons,
        reviewer_note=payload.note or None,
    )

    try:
        updated = save_verification(material_id, verification)
    except sqlite3.Error as error:
        raise _database_error("保存人工确认结果失败", error) from error
    if updated is None:
        raise _material_not_found(material_id)
    return updated


@router.get(
    "/materials/{material_id}/events",
    response_model=list[MaterialEventRecord],
    summary="查询材料操作记录",
)
def query_material_events(material_id: int) -> list[MaterialEventRecord]:
    material = _require_material(material_id)
    try:
        detail = get_material(material_id, with_events=True)
    except sqlite3.Error as error:
        raise _database_error("读取材料操作记录失败", error) from error
    if detail is None:
        raise _material_not_found(material_id)
    return detail["events"]
