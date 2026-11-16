"""DOCX 文本读取（python-docx）。"""

import io
import logging
import zipfile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.documents.errors import DocumentError
from app.services.documents.types import ExtractedDocument, Segment
from app.services.documents.validators import (
    DOCX_MAX_COMPRESSION_RATIO,
    DOCX_MAX_UNCOMPRESSED_BYTES,
    validate_text_length,
)

logger = logging.getLogger(__name__)

_TABLE_HEADER_WORDS = ("材料名称", "序号", "份数", "备注", "名称", "数量")


def _validate_docx_archive(content: bytes) -> None:
    """在 python-docx 解压前检查 ZIP 元数据，拦截解压炸弹。"""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            total_size = sum(item.file_size for item in archive.infolist())
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise DocumentError(
            "invalid_document",
            "DOCX 文件无法解析，可能已损坏或不是标准 Word 文档。",
            422,
        ) from exc

    if total_size > DOCX_MAX_UNCOMPRESSED_BYTES:
        raise DocumentError(
            "docx_uncompressed_too_large",
            "DOCX 解压后的内容超过 100MB 上限，请压缩图片或拆分文档后再上传。",
            413,
        )
    if total_size > len(content) * DOCX_MAX_COMPRESSION_RATIO:
        raise DocumentError(
            "docx_compression_ratio_too_high",
            "DOCX 压缩比异常，可能存在安全风险，请重新导出文档后再上传。",
            413,
        )


def _iter_blocks(document: Document):
    """按文档真实顺序遍历段落与表格，保证章节归属正确。"""
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield "paragraph", Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield "table", Table(child, document)


def read_docx(filename: str, content: bytes) -> ExtractedDocument:
    """读取 DOCX 的段落与表格文本，保留段落/表格位置。"""
    if not content.startswith(b"PK"):
        raise DocumentError(
            "invalid_document",
            "文件内容不是有效的 DOCX（不是 ZIP 容器），可能是旧版 .doc 或仅修改了扩展名。",
            422,
        )

    _validate_docx_archive(content)

    try:
        document = Document(io.BytesIO(content))
    except PackageNotFoundError as exc:
        raise DocumentError(
            "invalid_document",
            "DOCX 文件无法解析，可能已损坏或不是标准 Word 文档。",
            422,
        ) from exc
    except Exception as exc:
        logger.exception("DOCX 文件打开失败，文件名=%r", filename)
        raise DocumentError(
            "invalid_document",
            "DOCX 文件无法解析，可能已损坏或不是标准 Word 文档。",
            422,
        ) from exc

    segments: list[Segment] = []
    paragraph_index = 0
    table_index = 0
    text_chars = 0

    for kind, block in _iter_blocks(document):
        if kind == "paragraph":
            paragraph_index += 1
            text = block.text.strip()
            text_chars += len(text)
            validate_text_length(text_chars)
            if text:
                segments.append(
                    Segment(
                        text=text,
                        paragraph=paragraph_index,
                        location=f"第 {paragraph_index} 段",
                    )
                )
            continue

        table_index += 1
        for row_index, row in enumerate(block.rows, start=1):
            cells: list[str] = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                text_chars += len(cell_text)
                validate_text_length(text_chars)
                if cell_text and cell_text not in cells:
                    cells.append(cell_text)
            row_text = " | ".join(cells)
            if not row_text:
                continue
            # 跳过表头，避免把「材料名称 / 份数」当成材料条目
            if row_index == 1 and any(word in row_text for word in _TABLE_HEADER_WORDS):
                continue
            segments.append(
                Segment(
                    text=row_text,
                    paragraph=None,
                    location=f"表格 {table_index} 第 {row_index} 行",
                )
            )

    if not segments:
        raise DocumentError(
            "empty_file",
            "DOCX 中没有可读取的文本内容，请确认文档不是空白页。",
            400,
        )

    return ExtractedDocument(
        filename=filename,
        extension=".docx",
        size=len(content),
        segments=segments,
        paragraph_count=paragraph_index,
    )
