"""风险提醒接口的请求与响应模型。

风险类型与等级在服务端固定，前端只负责展示与筛选。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RiskType = Literal[
    "overdue",
    "due_soon",
    "backlog",
    "material_missing",
    "material_pending",
    "material_incomplete",
    "material_conflict",
    "material_uncertain",
    "date_unverified",
]
RiskLevel = Literal["high", "medium", "low"]
RiskStatus = Literal["active", "read", "resolved"]
RiskStatusFilter = Literal["active", "read", "resolved", "unresolved", "all"]
MatterDeadlineState = Literal[
    "none",
    "unverified",
    "suggested",
    "overdue",
    "today",
    "due_soon",
    "normal",
    "completed",
]


class RiskTaskRef(BaseModel):
    """积压/关联任务的最小信息，供详情展示与跳转使用。"""

    id: int
    title: str
    status: str
    deadline: str | None = None
    deadline_source: str | None = None
    days_left: int | None = None


class RiskEvidence(BaseModel):
    """风险判断依据：规则、数据来源、日期与关联对象快照。"""

    model_config = ConfigDict(extra="allow")

    rule: str = ""
    data_sources: list[str] = Field(default_factory=list)
    timezone: str | None = None
    today: str | None = None
    deadline_raw: str | None = None
    deadline_normalized: str | None = None
    deadline_source: str | None = None
    days_left: int | None = None
    matter_name: str | None = None
    task: RiskTaskRef | None = None
    unfinished_tasks: list[RiskTaskRef] = Field(default_factory=list)
    material: dict[str, Any] | None = None
    note: str | None = None


class RiskRecord(BaseModel):
    """数据库中的真实风险提醒记录。"""

    id: int
    fingerprint: str
    risk_type: RiskType
    risk_level: RiskLevel
    title: str
    description: str = ""
    matter_id: int
    matter_name: str = ""
    task_id: int | None = None
    task_title: str | None = None
    material_id: int | None = None
    material_name: str | None = None
    evidence: RiskEvidence | None = None
    suggestion: str = ""
    status: RiskStatus = "active"
    is_demo: bool = False
    first_seen_at: str
    last_seen_at: str
    read_at: str | None = None
    resolved_at: str | None = None


class RiskSummary(BaseModel):
    """风险统计：仪表盘与风险中心共用。"""

    generated_at: str
    timezone: str
    today: str

    total_unresolved: int = 0
    total_risks: int = 0
    active: int = 0
    read: int = 0
    resolved: int = 0

    high: int = 0
    medium: int = 0
    low: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)

    overdue_tasks: int = 0
    due_soon_3d_tasks: int = 0
    due_soon_7d_tasks: int = 0
    pending_materials: int = 0
    conflict_materials: int = 0
    missing_materials: int = 0
    uncertain_materials: int = 0
    unfinished_tasks: int = 0
    matters_with_risks: int = 0


class RiskListResponse(BaseModel):
    total: int
    items: list[RiskRecord] = Field(default_factory=list)


class MatterRiskSummary(BaseModel):
    """单个事项的综合风险摘要；具体风险事件仍逐条保留。"""

    matter_id: int
    matter_name: str
    matter_status: str
    deadline: str | None = None
    deadline_source: str = "none"
    deadline_state: MatterDeadlineState
    deadline_days_left: int | None = None
    unfinished_tasks: int = 0
    material_total: int = 0
    material_missing: int = 0
    material_pending: int = 0
    material_conflict: int = 0
    risk_total: int = 0
    level: RiskLevel = "low"
    headline: str = ""


class MatterRisksResponse(BaseModel):
    summary: MatterRiskSummary
    risks: list[RiskRecord] = Field(default_factory=list)


class RiskRefreshResult(BaseModel):
    generated_at: str
    created: int = 0
    updated: int = 0
    revived: int = 0
    resolved: int = 0
    summary: RiskSummary
