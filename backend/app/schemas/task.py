"""任务接口的请求与响应模型。

证据结构与事项保持一致（复用 MatterEvidence），前端无需转换。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.matter import MatterEvidence

TaskPriority = Literal["high", "medium", "low"]
TaskStatus = Literal["pending", "in_progress", "done"]
# suggested 仅用于兼容读取历史记录：用户应用建议后统一保存为 manual。
TaskDeadlineSource = Literal["document", "suggested", "manual", "none"]
TaskOrigin = Literal["generated", "manual"]


class TaskCreate(BaseModel):
    """手动新增任务：必须归属一个有效事项。"""

    model_config = ConfigDict(extra="forbid")

    matter_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    deadline: str | None = Field(default=None, max_length=40)
    deadline_source: TaskDeadlineSource | None = None
    priority: TaskPriority = "medium"
    status: TaskStatus = "pending"

    @field_validator("title", "description", "deadline")
    @classmethod
    def _strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("任务名称不能为空")
        return value


class TaskUpdate(BaseModel):
    """局部更新任务，只允许白名单字段；截止时间的来源会自动标记。"""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    deadline: str | None = Field(default=None, max_length=40)
    deadline_source: TaskDeadlineSource | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None

    @field_validator("title", "description", "deadline")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("任务名称不能为空")
        return value

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "TaskUpdate":
        if not self.model_fields_set:
            raise ValueError("请求体不能为空，至少需要提供一项要修改的字段")
        return self


class TaskRecord(BaseModel):
    """数据库中的真实任务记录。"""

    id: int
    matter_id: int
    title: str
    description: str = ""
    deadline: str | None = None
    deadline_source: TaskDeadlineSource = "none"
    priority: TaskPriority = "medium"
    status: TaskStatus = "pending"
    origin: TaskOrigin = "manual"
    source_evidence: MatterEvidence | None = None
    is_demo: bool = False
    created_at: str
    updated_at: str


class TaskDeadlineSuggestion(BaseModel):
    """系统依据事项总截止日期给出的建议，未确认前不会写入任务。"""

    deadline: str | None = None
    note: str
    task_ids: list[int] = Field(default_factory=list)


class TaskGenerationResult(BaseModel):
    """一次任务生成的结果统计，用于前端展示实际生成数量。"""

    matter_id: int
    created: int
    skipped: int
    total_process_steps: int
    message: str
    tasks: list[TaskRecord] = Field(default_factory=list)
    suggestion: TaskDeadlineSuggestion | None = None
