"""总览页统计接口的响应模型。

统计口径全部来自数据库真实记录，按「正式数据 / 演示数据」隔离，
不混入任何模拟节省时间、准确率或用户数量。
"""

from typing import Literal

from pydantic import BaseModel, Field

DashboardScope = Literal["real", "demo"]


class DashboardMatterStats(BaseModel):
    total: int = 0
    pending: int = 0
    in_progress: int = 0
    done: int = 0


class DashboardTaskStats(BaseModel):
    total: int = 0
    unfinished: int = 0
    done: int = 0
    overdue: int = 0
    due_soon_3d: int = 0
    due_soon_7d: int = 0


class DashboardMaterialStats(BaseModel):
    total: int = 0
    missing: int = 0
    pending: int = 0
    qualified: int = 0
    incomplete: int = 0
    conflict: int = 0
    uncertain: int = 0
    provided: int = 0
    prepared_percent: int = 0
    verified_percent: int = 0


class DashboardRiskStats(BaseModel):
    unresolved: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class DashboardRecentMatter(BaseModel):
    id: int
    name: str
    matter_type: str = ""
    status: str = "pending"
    deadline: str | None = None
    deadline_source: str = "none"
    updated_at: str


class DashboardDueTask(BaseModel):
    id: int
    title: str
    matter_id: int
    matter_name: str = ""
    deadline: str | None = None
    deadline_source: str = "none"
    priority: str = "medium"
    status: str = "pending"
    days_left: int | None = None
    overdue: bool = False


class DashboardSummary(BaseModel):
    """总览统计：scope=demo 时只统计演示数据，real 时只统计正式数据。"""

    scope: DashboardScope = "real"
    generated_at: str
    timezone: str
    today: str

    matters: DashboardMatterStats = Field(default_factory=DashboardMatterStats)
    tasks: DashboardTaskStats = Field(default_factory=DashboardTaskStats)
    materials: DashboardMaterialStats = Field(default_factory=DashboardMaterialStats)
    risks: DashboardRiskStats = Field(default_factory=DashboardRiskStats)

    recent_matters: list[DashboardRecentMatter] = Field(default_factory=list)
    due_soon_tasks: list[DashboardDueTask] = Field(default_factory=list)


class DemoStatus(BaseModel):
    """演示数据状态：用于一键初始化与清理操作前的确认提示。"""

    available: bool = True
    seeded: bool = False
    matters: int = 0
    tasks: int = 0
    materials: int = 0
    risks: int = 0
    real_matters: int = 0
    seeded_at: str | None = None
    message: str = ""
