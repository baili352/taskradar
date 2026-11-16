"""PNG / JPG / JPEG 图片读取与本地 OCR。"""

from io import BytesIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.services.documents.errors import DocumentError
from app.services.documents.ocr_engine import recognize
from app.services.documents.types import ExtractedDocument, Segment
from app.services.documents.validators import validate_text_length

_EXPECTED_FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
}


def read_image(filename: str, extension: str, content: bytes) -> ExtractedDocument:
    """核验真实图片格式与尺寸，并将 OCR 文本转换为统一片段。"""
    try:
        with Image.open(BytesIO(content)) as source:
            actual_format = source.format or ""
            if actual_format not in {"PNG", "JPEG"}:
                raise DocumentError(
                    "invalid_image",
                    "文件内容不是支持的 PNG 或 JPG 图片，可能只是修改了扩展名。",
                    422,
                )
            if actual_format != _EXPECTED_FORMATS[extension]:
                raise DocumentError(
                    "image_extension_mismatch",
                    "图片真实格式与文件扩展名不一致，请使用正确的 .png、.jpg 或 .jpeg 扩展名。",
                    422,
                )
            width, height = source.size
            if width <= 0 or height <= 0:
                raise DocumentError(
                    "invalid_image", "图片尺寸无效，请重新选择有效图片。", 422
                )
            if width * height > settings.ocr_max_image_pixels:
                raise DocumentError(
                    "image_too_large",
                    f"图片像素超过 {settings.ocr_max_image_pixels:,} 上限，请缩小后再上传。",
                    413,
                )
            oriented = ImageOps.exif_transpose(source)
            rgb = oriented.convert("RGB")
            image = np.asarray(rgb)
    except DocumentError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise DocumentError(
            "invalid_image",
            "图片无法解码，可能已损坏或并非真实图片，请更换文件。",
            422,
        ) from None

    lines = recognize(image)
    lines = [line.strip() for line in lines if line.strip()]
    if not lines:
        raise DocumentError(
            "no_text",
            "图片中未识别到有效文本，请上传更清晰、文字完整且方向正确的图片。",
            422,
        )
    validate_text_length(sum(len(line) for line in lines))

    return ExtractedDocument(
        filename=filename,
        extension=extension,
        size=len(content),
        segments=[
            Segment(text=line, page=1, location="第 1 页（OCR）") for line in lines
        ],
        page_count=1,
        ocr_used=True,
        ocr_pages=[1],
    )
