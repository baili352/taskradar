"""按扩展名分发到具体文档读取器。"""

from app.services.documents.docx_reader import read_docx
from app.services.documents.errors import DocumentError
from app.services.documents.image_reader import read_image
from app.services.documents.pdf_reader import read_pdf
from app.services.documents.txt_reader import read_txt
from app.services.documents.types import ExtractedDocument
from app.services.documents.validators import SUPPORTED_EXTENSIONS, validate_upload

__all__ = ["SUPPORTED_EXTENSIONS", "read_document"]


def read_document(filename: str, content: bytes, max_bytes: int) -> ExtractedDocument:
    """校验并读取文档，失败时抛出带中文提示的 DocumentError。"""
    extension = validate_upload(filename, content, max_bytes)

    if extension == ".pdf":
        return read_pdf(filename, content)
    if extension == ".docx":
        return read_docx(filename, content)
    if extension == ".txt":
        return read_txt(filename, content)
    if extension in {".png", ".jpg", ".jpeg"}:
        return read_image(filename, extension, content)

    # validate_upload 已拦截，这里作为兜底
    raise DocumentError("unsupported_format", "不支持的文件格式。", 415)
