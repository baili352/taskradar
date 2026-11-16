"""文档读取服务：读取 PDF / DOCX / TXT，并本地 OCR 图片和扫描 PDF。"""

from app.services.documents.errors import DocumentError
from app.services.documents.reader import SUPPORTED_EXTENSIONS, read_document
from app.services.documents.types import ExtractedDocument, Segment

__all__ = [
    "DocumentError",
    "ExtractedDocument",
    "Segment",
    "SUPPORTED_EXTENSIONS",
    "read_document",
]
