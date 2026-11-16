"""PDF 文本读取（PyMuPDF），低文本页按需使用本地 OCR。"""

import logging
import re

import fitz
import numpy as np

from app.core.config import settings
from app.services.documents.errors import DocumentError
from app.services.documents.ocr_engine import get_ocr_status, recognize
from app.services.documents.types import ExtractedDocument, Segment
from app.services.documents.validators import PDF_MAX_PAGES, validate_text_length

logger = logging.getLogger(__name__)

# 部分 PDF 字体（尤其是内置 CJK 字体）会在字符间插入多余空格，
# 这里只做保守清理：中文之间、数字之间、日期单位周围的空白。
_SPACE_BETWEEN_CJK = re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")
_SPACE_BETWEEN_DIGITS = re.compile(r"(?<=\d)\s+(?=\d)")
_SPACE_AROUND_DATE_UNIT = re.compile(r"(?<=[年月日])\s+(?=\d)|(?<=\d)\s+(?=[年月日])")
_SPACE_BEFORE_PUNCT = re.compile(r"(?<=\d)\s+(?=[.、)）])")


def _normalize_line(line: str) -> str:
    cleaned = re.sub(r"\s+", " ", line).strip()
    cleaned = _SPACE_BETWEEN_CJK.sub("", cleaned)
    cleaned = _SPACE_BETWEEN_DIGITS.sub("", cleaned)
    cleaned = _SPACE_AROUND_DATE_UNIT.sub("", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT.sub("", cleaned)
    return cleaned.strip()


def _render_page(page: fitz.Page, page_no: int) -> np.ndarray:
    scale = settings.ocr_pdf_dpi / 72
    width = int(page.rect.width * scale) + 1
    height = int(page.rect.height * scale) + 1
    if width * height > settings.ocr_max_image_pixels:
        raise DocumentError(
            "image_too_large",
            f"PDF 第 {page_no} 页按当前 DPI 渲染后超过像素上限，请降低 OCR_PDF_DPI 或拆分页面。",
            413,
        )
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False
    )
    return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )


def read_pdf(filename: str, content: bytes) -> ExtractedDocument:
    """保留原生文本，仅对扫描或低文本图像页追加 OCR 片段。"""
    if b"%PDF-" not in content[:1024]:
        raise DocumentError(
            "invalid_document",
            "文件内容不是有效的 PDF（缺少 PDF 文件头），可能只是修改了扩展名，请上传真实 PDF。",
            422,
        )

    try:
        pdf = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        logger.exception("PDF 文件打开失败，文件名=%r", filename)
        raise DocumentError(
            "invalid_document",
            "PDF 文件无法打开，可能已损坏或未完整下载。",
            422,
        ) from exc

    try:
        if pdf.needs_pass:
            raise DocumentError(
                "encrypted_pdf",
                "PDF 已加密，当前无法读取内容，请上传未加密的 PDF。",
                422,
            )
        if pdf.page_count == 0:
            raise DocumentError("empty_file", "PDF 中没有任何页面，请重新选择文件。", 400)
        if pdf.page_count > PDF_MAX_PAGES:
            raise DocumentError(
                "pdf_too_many_pages",
                f"PDF 页数超过 {PDF_MAX_PAGES} 页上限，请拆分文档后再上传。",
                413,
            )

        native_by_page: list[list[Segment]] = []
        has_images: list[bool] = []
        text_chars = 0
        page_no = 0
        try:
            for page_index in range(pdf.page_count):
                page_no = page_index + 1
                page = pdf[page_index]
                text = page.get_text("text")
                text_chars += len(text)
                validate_text_length(text_chars)
                page_segments = []
                for line in text.splitlines():
                    cleaned = _normalize_line(line)
                    if cleaned:
                        page_segments.append(
                            Segment(
                                text=cleaned,
                                page=page_no,
                                location=f"第 {page_no} 页",
                            )
                        )
                native_by_page.append(page_segments)
                has_images.append(bool(page.get_images(full=True)))
        except DocumentError:
            raise
        except Exception as exc:
            logger.exception("PDF 第 %s 页读取失败，文件名=%r", page_no, filename)
            raise DocumentError(
                "invalid_document",
                f"读取 PDF 第 {page_no} 页时失败，文件可能已损坏。",
                422,
            ) from exc

        has_native_text = any(native_by_page)
        candidates = []
        for page_index, page_segments in enumerate(native_by_page):
            native_chars = sum(len(re.sub(r"\s+", "", item.text)) for item in page_segments)
            if not has_native_text or (
                native_chars < settings.ocr_pdf_text_threshold and has_images[page_index]
            ):
                candidates.append(page_index + 1)

        warnings: list[str] = []
        ocr_by_page: dict[int, list[Segment]] = {}
        ocr_pages: list[int] = []
        last_ocr_error: DocumentError | None = None

        if len(candidates) > settings.ocr_max_pages:
            raise DocumentError(
                "ocr_too_many_pages",
                f"本次有 {len(candidates)} 页需要 OCR，超过 {settings.ocr_max_pages} 页上限，请拆分文档后再上传。",
                413,
            )

        if candidates:
            _enabled, available, status_message = get_ocr_status()
            if not settings.ocr_enabled:
                if not has_native_text:
                    raise DocumentError(
                        "ocr_disabled",
                        "该 PDF 需要 OCR，但本地 OCR 已禁用；请启用 OCR 或上传含文本层的 PDF。",
                        422,
                    )
                warnings.append("本地 OCR 已禁用，低文本图像页未识别；已保留其他页面的原生文本。")
            elif not available:
                if not has_native_text:
                    raise DocumentError(
                        "ocr_unavailable",
                        f"该 PDF 需要 OCR，但{status_message}",
                        422,
                    )
                warnings.append(f"{status_message} 已保留其他页面的原生文本。")
            else:
                for page_no in candidates:
                    try:
                        image = _render_page(pdf[page_no - 1], page_no)
                        lines = recognize(image)
                        ocr_pages.append(page_no)
                        page_segments = []
                        for line in lines:
                            cleaned = _normalize_line(line)
                            if cleaned:
                                page_segments.append(
                                    Segment(
                                        text=cleaned,
                                        page=page_no,
                                        location=f"第 {page_no} 页（OCR）",
                                    )
                                )
                        ocr_by_page[page_no] = page_segments
                    except DocumentError as exc:
                        last_ocr_error = exc
                        warnings.append(f"第 {page_no} 页 OCR 未完成：{exc.message}")
                    except Exception:
                        logger.exception("PDF 第 %s 页 OCR 渲染失败", page_no)
                        last_ocr_error = DocumentError(
                            "ocr_failed", "本地 OCR 页面处理失败。", 422
                        )
                        warnings.append(f"第 {page_no} 页 OCR 未完成，已跳过该页。")

        segments: list[Segment] = []
        for page_no, native_segments in enumerate(native_by_page, start=1):
            segments.extend(native_segments)
            segments.extend(ocr_by_page.get(page_no, []))
        validate_text_length(sum(len(segment.text) for segment in segments))

        if not segments:
            if last_ocr_error is not None:
                raise DocumentError(
                    last_ocr_error.code,
                    f"PDF 未获得可用文本；{last_ocr_error.message}",
                    last_ocr_error.status_code,
                )
            raise DocumentError(
                "no_text",
                "PDF 经文本读取和本地 OCR 后仍未获得有效文本，请上传更清晰的扫描件或含文本层的 PDF。",
                422,
            )

        return ExtractedDocument(
            filename=filename,
            extension=".pdf",
            size=len(content),
            segments=segments,
            page_count=pdf.page_count,
            ocr_used=bool(ocr_pages),
            ocr_pages=ocr_pages,
            warnings=warnings,
        )
    finally:
        pdf.close()
