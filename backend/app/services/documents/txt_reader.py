"""TXT 文本读取，兼容 UTF-8 / GB18030 / UTF-16 编码。"""

from app.services.documents.errors import DocumentError
from app.services.documents.types import ExtractedDocument, Segment
from app.services.documents.validators import validate_text_length

_ENCODINGS = ("utf-8-sig", "gb18030", "utf-16")


def _decode(content: bytes) -> tuple[str, str]:
    for encoding in _ENCODINGS:
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise DocumentError(
        "invalid_encoding",
        "无法识别文本编码，请将文件另存为 UTF-8 编码的 TXT 后重试。",
        422,
    )


def read_txt(filename: str, content: bytes) -> ExtractedDocument:
    """按行读取纯文本，保留行号。"""
    text, _encoding = _decode(content)
    validate_text_length(len(text))

    segments: list[Segment] = []
    line_index = 0
    for raw_line in text.splitlines():
        line_index += 1
        cleaned = raw_line.strip()
        if cleaned:
            segments.append(
                Segment(
                    text=cleaned,
                    paragraph=line_index,
                    location=f"第 {line_index} 行",
                )
            )

    if not segments:
        raise DocumentError(
            "empty_file",
            "TXT 文件没有有效文本（可能只有空白字符），请重新选择文件。",
            400,
        )

    return ExtractedDocument(
        filename=filename,
        extension=".txt",
        size=len(content),
        segments=segments,
        paragraph_count=line_index,
    )
