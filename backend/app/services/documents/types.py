"""文档读取的通用数据结构。"""

from dataclasses import dataclass, field


@dataclass
class Segment:
    """文档中的一个文本片段，保留可追溯的位置信息。"""

    text: str
    page: int | None = None
    paragraph: int | None = None
    location: str = ""


@dataclass
class ExtractedDocument:
    """读取完成的文档。"""

    filename: str
    extension: str
    size: int
    segments: list[Segment] = field(default_factory=list)
    page_count: int | None = None
    paragraph_count: int | None = None
    ocr_used: bool = False
    ocr_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return sum(len(segment.text) for segment in self.segments)
