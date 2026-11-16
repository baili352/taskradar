"""材料清单与核验接口的请求与响应模型。

状态语义：
- missing    尚未提供
- pending    已提供，待核验
- qualified  已确认符合
- incomplete 信息不完整
- conflict   存在冲突（需人工确认，规则核验不会直接给出）
- uncertain  无法判断
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.matter import MatterEvidence

MaterialStatus = Literal[
    "missing", "pending", "qualified", "incomplete", "conflict", "uncertain"
]
MaterialVerificationResult = Literal["qualified", "incomplete", "conflict", "uncertain"]
MaterialVerificationSource = Literal["rule", "manual"]
MaterialOrigin = Literal["generated", "manual"]
MaterialCheckStatus = Literal["pass", "warn", "unknown"]


class MaterialVerificationCheck(BaseModel):
    """单条核验检查项，message 为可读依据，excerpt 为原文摘录。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=100)
    status: MaterialCheckStatus
    message: str = Field(min_length=1, max_length=1000)
    excerpt: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200)


class MaterialVerification(BaseModel):
    """一次核验的完整记录：结论、时间、依据、摘录与原因。"""

    model_config = ConfigDict(extra="forbid")

    result: MaterialVerificationResult
    source: MaterialVerificationSource
    verified_at: str
    summary: str = Field(min_length=1, max_length=1000)
    checks: list[MaterialVerificationCheck] = Field(default_factory=list, max_length=30)
    reasons: list[str] = Field(default_factory=list, max_length=20)
    reviewer_note: str | None = Field(default=None, max_length=1000)


class MaterialEventRecord(BaseModel):
    """材料操作记录，用于保留人工确认与状态变更痕迹。"""

    id: int
    action: str
    detail: str
    created_at: str


class MaterialCreate(BaseModel):
    """手动新增材料（matter_id 来自路径参数）。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    source_evidence: MatterEvidence | None = None

    @field_validator("name", "description")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("材料名称不能为空")
        return value


class MaterialUpdate(BaseModel):
    """修改材料名称与要求说明，状态变更走核验/确认接口。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "description")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("材料名称不能为空")
        return value

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "MaterialUpdate":
        if not self.model_fields_set:
            raise ValueError("请求体不能为空，至少需要提供一项要修改的字段")
        return self


class MaterialConfirm(BaseModel):
    """人工确认或修改核验状态（只接受核验结论，不改变「未上传」准备状态）。"""

    model_config = ConfigDict(extra="forbid")

    status: MaterialVerificationResult
    note: str = Field(default="", max_length=1000)
    evidence_text: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def _strip_note(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence_text")
    @classmethod
    def _strip_evidence(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class MaterialRecord(BaseModel):
    """数据库中的真实材料记录。"""

    id: int
    matter_id: int
    matter_name: str = ""
    name: str
    description: str = ""
    status: MaterialStatus = "missing"
    file_path: str | None = None
    original_filename: str | None = None
    file_size: int | None = None
    file_type: str | None = None
    verification: MaterialVerification | None = None
    source_evidence: MatterEvidence | None = None
    origin: MaterialOrigin = "manual"
    is_demo: bool = False
    created_at: str
    updated_at: str
    events: list[MaterialEventRecord] = Field(default_factory=list)


class MaterialGenerationResult(BaseModel):
    """按事项材料要求生成清单的结果。"""

    matter_id: int
    created: int
    skipped: int
    total_source_materials: int
    message: str
    materials: list[MaterialRecord] = Field(default_factory=list)


class MaterialProgress(BaseModel):
    """单一事项的材料准备与核验进度。"""

    matter_id: int
    total: int
    missing: int
    provided: int
    pending: int
    qualified: int
    incomplete: int
    conflict: int
    uncertain: int
    prepared_percent: int
    verified_percent: int
