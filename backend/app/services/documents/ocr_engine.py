"""本地 RapidOCR 封装：延迟加载、串行推理并过滤低置信度文本。"""

import importlib.util
import logging
import threading
from typing import Any

import numpy as np

from app.core.config import settings
from app.services.documents.errors import DocumentError

logger = logging.getLogger(__name__)

_engine: Any = None
_lock = threading.Lock()


def get_ocr_status() -> tuple[bool, bool, str]:
    """返回启用、依赖可用状态；不加载模型，也不执行推理。"""
    if not settings.ocr_enabled:
        return False, False, "本地 OCR 已通过 OCR_ENABLED 禁用。"
    missing = [
        name
        for name in ("rapidocr_onnxruntime", "onnxruntime")
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        return True, False, "本地 OCR 依赖未完整安装，图片和扫描 PDF 暂不可用。"
    return True, True, "本地 RapidOCR 可用，图片和扫描 PDF 仅在本机识别。"


def recognize(image: np.ndarray) -> list[str]:
    """识别 RGB 图像，按引擎返回顺序输出有效文本行。"""
    if not settings.ocr_enabled:
        raise DocumentError(
            "ocr_disabled",
            "本地 OCR 已禁用，无法识别图片或扫描 PDF；请启用 OCR 或上传含文本层的文档。",
            422,
        )

    global _engine
    with _lock:
        if _engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR()
            except Exception:
                logger.exception("本地 OCR 初始化失败")
                raise DocumentError(
                    "ocr_unavailable",
                    "本地 OCR 初始化失败，请检查运行环境；也可上传 DOCX、TXT 或含文本层的 PDF。",
                    422,
                ) from None

        try:
            result, _elapsed = _engine(image)
        except DocumentError:
            raise
        except Exception:
            logger.exception("本地 OCR 推理失败")
            raise DocumentError(
                "ocr_failed",
                "本地 OCR 识别失败，请更换清晰图片或上传含文本层的文档。",
                422,
            ) from None

    lines: list[str] = []
    for item in result or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        text = str(item[1]).strip()
        try:
            confidence = float(item[2])
        except (TypeError, ValueError):
            continue
        if text and confidence >= settings.ocr_min_confidence:
            lines.append(text)
    return lines
