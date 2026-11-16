"""总览页统计查询。

所有数字都由 matters / tasks / materials / risks 的真实记录聚合而来，
按 matters.is_demo 严格隔离正式数据与演示数据。演示数据从不参与
正式统计，清理演示数据也不会影响正式记录。
"""

from app.db.database import get_connection
from app.schemas.dashboard import (
    DashboardDueTask,
    DashboardMaterialStats,
    DashboardMatterStats,
    DashboardRecentMatter,
    DashboardRiskStats,
    DashboardSummary,
    DashboardTaskStats,
)
from app.services.risks.dates import (
    days_left,
    get_timezone_name,
    is_overdue,
    now_in_timezone,
    parse_deadline,
    participates,
    today_in_timezone,
)

_RECENT_LIMIT = 5
_DUE_LIMIT = 5


def _matter_stats(rows) -> DashboardMatterStats:
    stats = DashboardMatterStats(total=len(rows))
    for row in rows:
        status = row["status"]
        if status == "pending":
            stats.pending += 1
        elif status == "in_progress":
            stats.in_progress += 1
        elif status == "done":
            stats.done += 1
    return stats


def _task_stats(tasks, matter_status: dict[int, str]) -> DashboardTaskStats:
    moment = now_in_timezone()
    today = today_in_timezone()
    stats = DashboardTaskStats(total=len(tasks))
    for task in tasks:
        if task["status"] == "done":
            stats.done += 1
            continue
        stats.unfinished += 1
        if matter_status.get(task["matter_id"]) == "done":
            continue
        if not participates(task["deadline_source"], task["deadline"]):
            continue
        info = parse_deadline(task["deadline"])
        if info.status != "ok" or info.day is None:
            continue
        if is_overdue(info, moment):
            stats.overdue += 1
            continue
        left = days_left(info.day, today)
        if left <= 7:
            stats.due_soon_7d += 1
        if left <= 3:
            stats.due_soon_3d += 1
    return stats


def _material_stats(rows) -> DashboardMaterialStats:
    stats = DashboardMaterialStats(total=len(rows))
    for row in rows:
        status = row["status"]
        if status == "missing":
            stats.missing += 1
        elif status == "pending":
            stats.pending += 1
        elif status == "qualified":
            stats.qualified += 1
        elif status == "incomplete":
            stats.incomplete += 1
        elif status == "conflict":
            stats.conflict += 1
        elif status == "uncertain":
            stats.uncertain += 1
        if row["file_path"]:
            stats.provided += 1
    if stats.total:
        stats.prepared_percent = round(stats.provided / stats.total * 100)
        stats.verified_percent = round(stats.qualified / stats.total * 100)
    return stats


def _risk_stats(rows) -> DashboardRiskStats:
    stats = DashboardRiskStats(unresolved=len(rows))
    for row in rows:
        level = row["risk_level"]
        if level == "high":
            stats.high += 1
        elif level == "medium":
            stats.medium += 1
        elif level == "low":
            stats.low += 1
    return stats


def _due_tasks(tasks, matter_status: dict[int, str]) -> list[DashboardDueTask]:
    moment = now_in_timezone()
    today = today_in_timezone()
    items: list[tuple[int, DashboardDueTask]] = []
    for task in tasks:
        if task["status"] == "done":
            continue
        if matter_status.get(task["matter_id"]) == "done":
            continue
        if not participates(task["deadline_source"], task["deadline"]):
            continue
        info = parse_deadline(task["deadline"])
        if info.status != "ok" or info.day is None:
            continue
        left = days_left(info.day, today)
        overdue = is_overdue(info, moment)
        if not overdue and left > 7:
            continue
        items.append(
            (
                left,
                DashboardDueTask(
                    id=task["id"],
                    title=task["title"],
                    matter_id=task["matter_id"],
                    matter_name=task["matter_name"] or "",
                    deadline=task["deadline"],
                    deadline_source=task["deadline_source"],
                    priority=task["priority"],
                    status=task["status"],
                    days_left=left,
                    overdue=overdue,
                ),
            )
        )
    items.sort(key=lambda item: item[0])
    return [item[1] for item in items[:_DUE_LIMIT]]


def build_summary(is_demo: bool) -> DashboardSummary:
    flag = 1 if is_demo else 0
    with get_connection() as conn:
        matter_rows = conn.execute(
            "SELECT id, name, matter_type, status, deadline, deadline_source, "
            "updated_at FROM matters WHERE is_demo = ? "
            "ORDER BY datetime(updated_at) DESC, id DESC",
            (flag,),
        ).fetchall()
        task_rows = conn.execute(
            "SELECT t.id, t.matter_id, COALESCE(mt.name, '') AS matter_name, "
            "t.title, t.priority, t.status, t.deadline, t.deadline_source "
            "FROM tasks t LEFT JOIN matters mt ON mt.id = t.matter_id "
            "WHERE COALESCE(mt.is_demo, 0) = ?",
            (flag,),
        ).fetchall()
        material_rows = conn.execute(
            "SELECT m.status, m.file_path "
            "FROM materials m LEFT JOIN matters mt ON mt.id = m.matter_id "
            "WHERE COALESCE(mt.is_demo, 0) = ?",
            (flag,),
        ).fetchall()
        risk_rows = conn.execute(
            "SELECT r.risk_level FROM risks r "
            "LEFT JOIN matters mt ON mt.id = r.matter_id "
            "WHERE COALESCE(mt.is_demo, 0) = ? AND r.status IN ('active', 'read')",
            (flag,),
        ).fetchall()

    matter_status = {row["id"]: row["status"] for row in matter_rows}
    recent = [
        DashboardRecentMatter(
            id=row["id"],
            name=row["name"],
            matter_type=row["matter_type"],
            status=row["status"],
            deadline=row["deadline"],
            deadline_source=row["deadline_source"],
            updated_at=row["updated_at"],
        )
        for row in matter_rows[:_RECENT_LIMIT]
    ]

    return DashboardSummary(
        scope="demo" if is_demo else "real",
        generated_at=now_in_timezone().isoformat(timespec="milliseconds"),
        timezone=get_timezone_name(),
        today=today_in_timezone().isoformat(),
        matters=_matter_stats(matter_rows),
        tasks=_task_stats(task_rows, matter_status),
        materials=_material_stats(material_rows),
        risks=_risk_stats(risk_rows),
        recent_matters=recent,
        due_soon_tasks=_due_tasks(task_rows, matter_status),
    )
