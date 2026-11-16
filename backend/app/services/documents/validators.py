"""上传文件的基础校验：格式、空文件、大小上限。"""

from pathlib import Path

from app.services.documents.errors import DocumentError

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg")

# 上传体积之外的二次资源限制，避免高压缩比或超长文档耗尽内存。
DOCX_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
DOCX_MAX_COMPRESSION_RATIO = 100
PDF_MAX_PAGES = 500
MAX_EXTRACTED_TEXT_CHARS = 2_000_000


def validate_text_length(total_chars: int) -> None:
    if total_chars > MAX_EXTRACTED_TEXT_CHARS:
        raise DocumentError(
            "text_too_large",
            "文档提取出的文本过长，请拆分文档后再上传。",
            413,
        )


def get_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def validate_upload(filename: str, content: bytes, max_bytes: int) -> str:
    """校验文件名与内容大小，返回小写扩展名。"""
    if not filename:
        raise DocumentError("missing_filename", "没有获取到文件名，请重新选择文件。", 400)

    extension = get_extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        supported = " / ".join(item.lstrip(".").upper() for item in SUPPORTED_EXTENSIONS)
        raise DocumentError(
            "unsupported_format",
            f"不支持的文件格式「{extension or '无扩展名'}」，请上传 {supported} 文件。",
            415,
        )

    if len(content) == 0:
        raise DocumentError("empty_file", "文件内容为空（0 字节），请重新选择有效文件。", 400)

    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise DocumentError(
            "file_too_large",
            f"文件超过 {limit_mb}MB 上限，请压缩或拆分后再上传。",
            413,
        )

    return extension
