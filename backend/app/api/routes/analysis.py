"""智能分析接口：本地 OCR、规则提取与 OpenAI 兼容大模型辅助分析。"""

import logging
import time

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.schemas.analysis import (
    AIConnectionTestResponse,
    AnalysisResponse,
    CapabilitiesResponse,
    DocumentInfo,
)
from app.services.ai import AIError, analyze_with_ai, test_ai_connection
from app.services.documents import SUPPORTED_EXTENSIONS, DocumentError, read_document
from app.services.documents.ocr_engine import get_ocr_status
from app.services.extraction import extract_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["智能分析"])

AI_NOT_CONFIGURED_MESSAGE = (
    "当前未完整配置 AI_BASE_URL 和 AI_MODEL，本次使用本地规则提取，"
    "未找到原文依据的字段会标记为「待核实」。"
)
AI_CONFIGURED_MESSAGE = (
    "智能分析将调用已配置模型，文档文本会发送到该模型服务；"
    "证据仍由本地原文生成，失败时自动回退到规则结果。"
)


def _ai_message() -> str:
    return AI_CONFIGURED_MESSAGE if settings.ai_configured else AI_NOT_CONFIGURED_MESSAGE


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="分析能力与 AI / OCR 配置状态",
)
def get_capabilities() -> CapabilitiesResponse:
    """只读取配置和依赖状态，不调用外部模型或执行 OCR。"""
    ocr_enabled, ocr_available, ocr_message = get_ocr_status()
    return CapabilitiesResponse(
        analysis_mode="ai_assisted" if settings.ai_configured else "rule_based",
        ai_configured=settings.ai_configured,
        ai_provider=settings.ai_provider.strip() or "OpenAI 兼容服务",
        ai_model=settings.ai_model,
        ai_key_configured=bool(settings.ai_api_key.strip()),
        ai_message=_ai_message(),
        ocr_enabled=ocr_enabled,
        ocr_available=ocr_available,
        ocr_message=ocr_message,
        supported_extensions=[item.lstrip(".") for item in SUPPORTED_EXTENSIONS],
        max_upload_mb=settings.max_upload_mb,
    )


@router.post(
    "/ai/test",
    response_model=AIConnectionTestResponse,
    summary="测试大模型连接（不发送文档）",
)
async def test_connection() -> AIConnectionTestResponse:
    started = time.perf_counter()
    if not settings.ai_configured:
        return AIConnectionTestResponse(
            success=False,
            message="请先在 backend/.env 中配置 AI_BASE_URL 和 AI_MODEL，再重启后端。",
            model=settings.ai_model,
            elapsed_ms=0,
        )
    try:
        await test_ai_connection()
        message = "连接成功，模型服务已响应；本次测试未发送文档。"
    except AIError as exc:
        return AIConnectionTestResponse(
            success=False,
            message=str(exc),
            model=settings.ai_model,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        logger.error("大模型连接测试出现未预期错误：%s", type(exc).__name__)
        return AIConnectionTestResponse(
            success=False,
            message="连接测试失败，请检查模型服务配置或稍后重试。",
            model=settings.ai_model,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
    return AIConnectionTestResponse(
        success=True,
        message=message,
        model=settings.ai_model,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="上传文档并执行 OCR / 规则 / AI 分析",
)
async def analyze_document(file: UploadFile = File(...)) -> AnalysisResponse:
    """规则结果先生成并保留；AI 故障只导致显式回退，不影响文档分析。"""
    started = time.perf_counter()
    filename = file.filename or ""
    content = await file.read(settings.max_upload_bytes + 1)

    try:
        document = await run_in_threadpool(
            read_document, filename, content, settings.max_upload_bytes
        )
    except DocumentError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception:
        logger.exception("文档读取失败：%s", filename)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "document_read_failed",
                "message": "文档读取失败，请更换文件或稍后重试。",
            },
        ) from None

    try:
        rule_result = await run_in_threadpool(extract_document, document)
    except Exception:
        logger.exception("文档提取失败：%s", filename)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "extraction_failed",
                "message": "文档已读取，但提取事项要素时发生错误，请更换文件后重试。",
            },
        ) from None

    extracted = rule_result
    analysis_mode = "rule_based"
    ai_message = _ai_message()
    if settings.ai_configured:
        try:
            extracted = await analyze_with_ai(document)
            analysis_mode = "ai_assisted"
            ai_message = (
                f"本次已调用模型 {settings.ai_model} 辅助提取；所有证据均由本地原文片段重建，请继续人工核实。"
            )
        except AIError as exc:
            analysis_mode = "rule_fallback"
            ai_message = f"大模型分析未完成，已回退到本地规则结果。原因：{exc}"
        except Exception as exc:
            logger.error("大模型分析出现未预期错误：%s", type(exc).__name__)
            analysis_mode = "rule_fallback"
            ai_message = "大模型分析出现未预期错误，已回退到本地规则结果。"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    warnings = list(dict.fromkeys([*document.warnings, *extracted["warnings"]]))

    return AnalysisResponse(
        document=DocumentInfo(
            filename=document.filename,
            extension=document.extension,
            size=document.size,
            char_count=document.char_count,
            page_count=document.page_count,
            paragraph_count=document.paragraph_count,
            ocr_used=document.ocr_used,
            ocr_pages=document.ocr_pages,
        ),
        fields=extracted["fields"],
        materials=extracted["materials"],
        process=extracted["process"],
        notes=extracted["notes"],
        warnings=warnings,
        analysis_mode=analysis_mode,
        ai_configured=settings.ai_configured,
        ai_message=ai_message,
        elapsed_ms=elapsed_ms,
    )
