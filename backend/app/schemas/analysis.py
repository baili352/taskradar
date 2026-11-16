"""智能分析接口的响应模型。"""

from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    text: str
    location: str
    page: int | None = None
    paragraph: int | None = None


class FieldResult(BaseModel):
    key: str
    label: str
    value: str | None = None
    status: Literal["found", "pending"]
    evidence: list[Evidence] = Field(default_factory=list)
    note: str | None = None


class MaterialItem(BaseModel):
    name: str
    status: Literal["found"] = "found"
    evidence: Evidence


class ProcessStep(BaseModel):
    index: int
    text: str
    evidence: Evidence


class NoteItem(BaseModel):
    text: str
    evidence: Evidence


class DocumentInfo(BaseModel):
    filename: str
    extension: str
    size: int
    char_count: int
    page_count: int | None = None
    paragraph_count: int | None = None
    ocr_used: bool = False
    ocr_pages: list[int] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    document: DocumentInfo
    fields: list[FieldResult]
    materials: list[MaterialItem]
    process: list[ProcessStep]
    notes: list[NoteItem]
    warnings: list[str]
    analysis_mode: Literal["rule_based", "ai_assisted", "rule_fallback"]
    ai_configured: bool
    ai_message: str
    elapsed_ms: int


class CapabilitiesResponse(BaseModel):
    analysis_mode: Literal["rule_based", "ai_assisted", "rule_fallback"]
    ai_configured: bool
    ai_provider: str
    ai_model: str
    ai_key_configured: bool
    ai_message: str
    ocr_enabled: bool
    ocr_available: bool
    ocr_message: str
    supported_extensions: list[str]
    max_upload_mb: int


class AIConnectionTestResponse(BaseModel):
    success: bool
    message: str
    model: str
    elapsed_ms: int
