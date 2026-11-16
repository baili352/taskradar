"""事项持久化接口的请求与响应模型。

字段命名与第三阶段分析接口保持一致（证据结构完全相同），
前端可以直接把分析结果提交保存，不需要重新拼装证据。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MatterStatus = Literal["pending", "in_progress", "done"]
EvidenceStatus = Literal["found", "pending"]
MatterDeadlineSource = Literal["document", "suggested", "manual", "none"]


class MatterEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    location: str = Field(min_length=1, max_length=200)
    page: int | None = Field(default=None, ge=1)
    paragraph: int | None = Field(default=None, ge=1)


class MatterMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    status: Literal["found"] = "found"
    evidence: MatterEvidence


class MatterProcessStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1, le=200)
    text: str = Field(min_length=1, max_length=1000)
    evidence: MatterEvidence


class MatterNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    evidence: MatterEvidence


class MatterField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=50)
    value: str | None = Field(default=None, max_length=2000)
    status: EvidenceStatus
    evidence: list[MatterEvidence] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=1000)


class MatterCreate(BaseModel):
    """创建事项。除名称外均可缺省，缺省表示原文未提供。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    matter_type: str = Field(default="", max_length=50)
    qualification: str = Field(default="", max_length=1000)
    registration_start: str | None = Field(default=None, max_length=40)
    deadline: str | None = Field(default=None, max_length=40)
    deadline_source: MatterDeadlineSource | None = None
    materials: list[MatterMaterial] = Field(default_factory=list, max_length=100)
    process: list[MatterProcessStep] = Field(default_factory=list, max_length=100)
    notes: list[MatterNote] = Field(default_factory=list, max_length=100)
    fields: list[MatterField] = Field(default_factory=list, max_length=30)
    source_filename: str = Field(default="", max_length=255)
    status: MatterStatus = "pending"
    analysis_mode: str = Field(default="rule_based", max_length=30)

    @field_validator("name", "matter_type", "qualification", "source_filename")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("事项名称不能为空")
        return value


class MatterUpdate(BaseModel):
    """局部更新事项；缺省列表保持原值，显式空列表表示用户主动清空。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    matter_type: str | None = Field(default=None, max_length=50)
    qualification: str | None = Field(default=None, max_length=1000)
    registration_start: str | None = Field(default=None, max_length=40)
    deadline: str | None = Field(default=None, max_length=40)
    deadline_source: MatterDeadlineSource | None = None
    materials: list[MatterMaterial] | None = Field(default=None, max_length=100)
    process: list[MatterProcessStep] | None = Field(default=None, max_length=100)
    notes: list[MatterNote] | None = Field(default=None, max_length=100)
    fields: list[MatterField] | None = Field(default=None, max_length=30)
    source_filename: str | None = Field(default=None, max_length=255)
    status: MatterStatus | None = None

    @field_validator("name", "matter_type", "qualification", "source_filename")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("事项名称不能为空")
        return value

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "MatterUpdate":
        if not self.model_fields_set:
            raise ValueError("请求体不能为空，至少需要提供一项要修改的字段")
        return self


class MatterRecord(BaseModel):
    """数据库中的真实事项记录。"""

    id: int
    name: str
    matter_type: str
    qualification: str
    registration_start: str | None = None
    deadline: str | None = None
    deadline_source: MatterDeadlineSource = "none"
    materials: list[MatterMaterial] = Field(default_factory=list)
    process: list[MatterProcessStep] = Field(default_factory=list)
    notes: list[MatterNote] = Field(default_factory=list)
    fields: list[MatterField] = Field(default_factory=list)
    source_filename: str = ""
    status: MatterStatus = "pending"
    analysis_mode: str = "rule_based"
    is_demo: bool = False
    created_at: str
    updated_at: str
