"""风险分析与事项风险摘要。

只读取现有真实数据（matters / tasks / materials），不伪造任何提醒对象。
风险事件按“风险类型 + 关联对象”生成稳定指纹，由数据层负责去重与状态恢复。
"""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.db.materials import list_materials
from app.db.matters import list_matters
from app.db.tasks import list_tasks
from app.schemas.task import TaskRecord
from app.services.risks.dates import (
    DeadlineInfo,
    days_left,
    get_timezone_name,
    is_overdue,
    now_in_timezone,
    parse_deadline,
    participates,
    today_in_timezone,
)

SOURCE_LABELS = {
    "document": "原文明确日期",
    "manual": "用户手动设置",
    "suggested": "系统建议日期（未经用户应用时不参与到期判断）",
    "none": "未设置截止日期",
}

_MATERIAL_RULES = {
    "missing": (
        "material_missing",
        "medium",
        "材料缺失",
        "必需材料尚未提供。",
        "请准备并上传该材料，上传后可执行规则核验。",
    ),
    "pending": (
        "material_pending",
        "low",
        "材料待核验",
        "材料已上传，但尚未执行核验或人工确认。",
        "请在材料核验页执行规则核验，或人工确认核验结果。",
    ),
    "incomplete": (
        "material_incomplete",
        "medium",
        "材料信息不完整",
        "材料已上传，但核验发现信息可能不完整，需要人工确认。",
        "请核对材料内容并补全信息，确认后重新核验。",
    ),
    "conflict": (
        "material_conflict",
        "high",
        "材料存在冲突",
        "材料的核验结果或人工确认显示存在冲突信息。",
        "请优先核对冲突内容，必要时更换材料并重新核验。",
    ),
    "uncertain": (
        "material_uncertain",
        "low",
        "材料无法判断",
        "规则核验无法判断该材料是否符合要求，不代表材料不合格。",
        "请人工检查材料内容，并在材料核验页确认核验结论。",
    ),
}

_LEVEL_WEIGHT = {"high": 3, "medium": 2, "low": 1}


@dataclass
class AnalysisOutcome:
    candidates: list[dict] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    matter_summaries: dict[int, dict] = field(default_factory=dict)


def _fingerprint(
    risk_type: str, matter_id: int, task_id: int | None, material_id: int | None
) -> str:
    parts = [risk_type, f"matter:{matter_id}"]
    if task_id is not None:
        parts.append(f"task:{task_id}")
    if material_id is not None:
        parts.append(f"material:{material_id}")
    return "|".join(parts)


def _task_ref(task: TaskRecord, info: DeadlineInfo, today: date) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "deadline": task.deadline,
        "deadline_source": task.deadline_source,
        "days_left": days_left(info.day, today) if info.day else None,
    }


def _deadline_state(
    info: DeadlineInfo,
    source: str,
    moment: datetime,
    today: date,
    matter_done: bool,
) -> tuple[str, int | None]:
    if info.status == "missing":
        return "none", None
    if source not in {"document", "manual"}:
        # 系统建议日期尚未应用，不参与正式到期判断。
        return ("none" if source == "none" else "suggested"), None
    if matter_done:
        return "completed", None
    if info.status == "unverified" or info.day is None or info.moment is None:
        return "unverified", None
    if is_overdue(info, moment):
        return "overdue", days_left(info.day, today)
    left = days_left(info.day, today)
    if left == 0:
        return "today", 0
    if left <= 7:
        return "due_soon", left
    return "normal", left


def _format_days(value: int | None) -> str:
    if value is None:
        return "未知"
    return f"{abs(value)} 天"


def analyze_risks(conn: sqlite3.Connection | None = None) -> AnalysisOutcome:
    """计算风险候选。

    conn 非空时所有读取都走该连接，调用方可在同一事务内看到尚未提交的写入；
    为空时各读取函数自行开连接，保持原有行为。
    """
    tz_name = get_timezone_name()
    moment = now_in_timezone()
    today = today_in_timezone()

    matters = list_matters(conn=conn)
    tasks = list_tasks(conn=conn)
    materials = list_materials(conn=conn)

    matter_names = {matter.id: matter.name for matter in matters}
    matter_statuses = {matter.id: matter.status for matter in matters}
    tasks_by_matter: dict[int, list[TaskRecord]] = defaultdict(list)
    for task in tasks:
        tasks_by_matter[task.matter_id].append(task)
    materials_by_matter: dict[int, list[dict]] = defaultdict(list)
    for material in materials:
        materials_by_matter[material["matter_id"]].append(material)

    task_info: dict[int, DeadlineInfo] = {task.id: parse_deadline(task.deadline) for task in tasks}
    candidates: dict[str, dict] = {}

    def add(candidate: dict) -> None:
        candidates[candidate["fingerprint"]] = candidate

    # ---- 任务级风险：逾期、即将截止、日期待核实 ----
    for task in tasks:
        if task.status == "done":
            # 已完成任务不再产生逾期或即将截止提醒。
            continue
        if matter_statuses.get(task.matter_id) == "done":
            # 事项已完成时，其下未完成任务也不再产生风险；历史记录由同步逻辑归档。
            continue
        if not participates(task.deadline_source, task.deadline):
            continue

        info = task_info[task.id]
        matter_name = matter_names.get(task.matter_id, f"事项 #{task.matter_id}")
        base_evidence = {
            "timezone": tz_name,
            "today": today.isoformat(),
            "deadline_raw": task.deadline,
            "deadline_normalized": info.normalized,
            "deadline_source": task.deadline_source,
            "matter_name": matter_name,
            "task": _task_ref(task, info, today),
        }

        if info.status == "unverified":
            add(
                {
                    "fingerprint": _fingerprint("date_unverified", task.matter_id, task.id, None),
                    "risk_type": "date_unverified",
                    "risk_level": "low",
                    "title": f"任务截止日期待核实：{task.title}",
                    "description": (
                        f"事项「{matter_name}」的任务「{task.title}」截止日期为"
                        f"「{task.deadline}」，{info.reason or '无法确定具体日期'}"
                    ),
                    "matter_id": task.matter_id,
                    "task_id": task.id,
                    "material_id": None,
                    "suggestion": "请在任务中心补充明确的截止日期，或人工核实原文日期。",
                    "evidence": {
                        **base_evidence,
                        "rule": f"截止日期「{task.deadline}」无法解析为明确日期，因此暂不参与逾期判断。",
                        "data_sources": ["tasks.deadline", "tasks.deadline_source"],
                        "note": info.reason,
                    },
                }
            )
            continue

        if info.status != "ok" or info.moment is None or info.day is None:
            continue

        if is_overdue(info, moment):
            days = days_left(info.day, today)
            add(
                {
                    "fingerprint": _fingerprint("overdue", task.matter_id, task.id, None),
                    "risk_type": "overdue",
                    "risk_level": "high",
                    "title": f"任务已逾期：{task.title}",
                    "description": (
                        f"事项「{matter_name}」的任务「{task.title}」截止日期为"
                        f"「{task.deadline}」，已超过截止时间 {_format_days(days)}，且任务尚未完成。"
                    ),
                    "matter_id": task.matter_id,
                    "task_id": task.id,
                    "material_id": None,
                    "suggestion": "请尽快完成任务；如截止日期已经变化，可在任务中心修改截止日期。",
                    "evidence": {
                        **base_evidence,
                        "days_left": days,
                        "rule": (
                            f"任务截止日期 {info.normalized} 早于当前时间，"
                            f"且任务状态为「{task.status}」，因此判定为逾期。"
                        ),
                        "data_sources": ["tasks.deadline", "tasks.deadline_source", "tasks.status"],
                    },
                }
            )
            continue

        left = days_left(info.day, today)
        if left <= 7:
            level = "high" if left <= 3 else "medium"
            window = "3 天内" if left <= 3 else "4—7 天内"
            add(
                {
                    "fingerprint": _fingerprint("due_soon", task.matter_id, task.id, None),
                    "risk_type": "due_soon",
                    "risk_level": level,
                    "title": f"任务即将截止：{task.title}",
                    "description": (
                        f"事项「{matter_name}」的任务「{task.title}」将在"
                        f"「{task.deadline}」截止，距今 {left} 天（{window}）。"
                    ),
                    "matter_id": task.matter_id,
                    "task_id": task.id,
                    "material_id": None,
                    "suggestion": "请按截止时间安排处理顺序，完成后在任务中心标记完成。",
                    "evidence": {
                        **base_evidence,
                        "days_left": left,
                        "rule": (
                            f"任务截止日期 {info.normalized} 距今 {left} 天，"
                            f"处于{window}的提醒范围，且任务尚未完成。"
                        ),
                        "data_sources": ["tasks.deadline", "tasks.deadline_source", "tasks.status"],
                    },
                }
            )

    # ---- 事项级风险：任务积压、日期待核实 ----
    for matter in matters:
        matter_tasks = tasks_by_matter.get(matter.id, [])
        unfinished = [task for task in matter_tasks if task.status != "done"]

        if matter.status != "done" and len(unfinished) >= 2:
            refs = [_task_ref(task, task_info[task.id], today) for task in unfinished]
            names = "、".join(task.title for task in unfinished[:5])
            more = f" 等 {len(unfinished)} 项" if len(unfinished) > 5 else ""
            add(
                {
                    "fingerprint": _fingerprint("backlog", matter.id, None, None),
                    "risk_type": "backlog",
                    "risk_level": "medium",
                    "title": f"事项任务积压：{matter.name}",
                    "description": (
                        f"事项「{matter.name}」还有 {len(unfinished)} 个未完成任务："
                        f"{names}{more}。任务处于未完成状态本身不判定为逾期，"
                        "只有存在明确截止日期且已过期时才单独产生逾期提醒。"
                    ),
                    "matter_id": matter.id,
                    "task_id": None,
                    "material_id": None,
                    "suggestion": "建议按截止时间与优先级安排处理顺序，可前往任务中心逐项完成。",
                    "evidence": {
                        "timezone": tz_name,
                        "today": today.isoformat(),
                        "matter_name": matter.name,
                        "unfinished_tasks": refs,
                        "rule": f"事项下存在 {len(unfinished)} 个未完成任务（状态非 done）。",
                        "data_sources": ["tasks.status", "tasks.title", "tasks.deadline"],
                    },
                }
            )

        if (
            matter.status != "done"
            and participates(matter.deadline_source, matter.deadline)
        ):
            info = parse_deadline(matter.deadline)
            if info.status == "unverified":
                add(
                    {
                        "fingerprint": _fingerprint("date_unverified", matter.id, None, None),
                        "risk_type": "date_unverified",
                        "risk_level": "low",
                        "title": f"事项截止日期待核实：{matter.name}",
                        "description": (
                            f"事项「{matter.name}」的截止日期为「{matter.deadline}」，"
                            f"{info.reason or '无法确定具体日期'}"
                        ),
                        "matter_id": matter.id,
                        "task_id": None,
                        "material_id": None,
                        "suggestion": "请在事项详情中核实并补充明确截止日期，核实前不参与逾期判断。",
                        "evidence": {
                            "timezone": tz_name,
                            "today": today.isoformat(),
                            "deadline_raw": matter.deadline,
                            "deadline_source": matter.deadline_source,
                            "matter_name": matter.name,
                            "rule": f"截止日期「{matter.deadline}」无法解析为明确日期。",
                            "data_sources": ["matters.deadline", "matters.deadline_source"],
                            "note": info.reason,
                        },
                    }
                )

    # ---- 材料风险 ----
    for material in materials:
        # 事项已完成时不再生成未完成事项相关的材料风险；
        # 历史风险由同步逻辑标记为 resolved 保留，不删除。
        if matter_statuses.get(material["matter_id"]) == "done":
            continue
        rule = _MATERIAL_RULES.get(material["status"])
        if rule is None:
            # qualified（已确认符合）不产生材料缺失提醒。
            continue
        risk_type, level, label, reason, suggestion = rule
        matter_id = material["matter_id"]
        matter_name = material["matter_name"] or matter_names.get(matter_id, "")
        verification = material.get("verification")
        verification_payload = None
        if verification is not None:
            verification_payload = {
                "result": verification.result,
                "source": verification.source,
                "verified_at": verification.verified_at,
                "summary": verification.summary,
                "reasons": list(verification.reasons),
                "checks": [
                    {
                        "key": check.key,
                        "label": check.label,
                        "status": check.status,
                        "message": check.message,
                        "excerpt": check.excerpt,
                        "location": check.location,
                    }
                    for check in verification.checks
                ],
            }
        evidence = material.get("source_evidence")

        add(
            {
                "fingerprint": _fingerprint(risk_type, matter_id, None, material["id"]),
                "risk_type": risk_type,
                "risk_level": level,
                "title": f"{label}：{material['name']}",
                "description": (
                    f"事项「{matter_name}」的材料「{material['name']}」{reason}"
                    + (f" 材料要求：{material['description']}" if material["description"] else "")
                ),
                "matter_id": matter_id,
                "task_id": None,
                "material_id": material["id"],
                "suggestion": suggestion,
                "evidence": {
                    "timezone": tz_name,
                    "today": today.isoformat(),
                    "matter_name": matter_name,
                    "rule": f"材料状态为「{material['status']}」，{reason}",
                    "data_sources": [
                        "materials.status",
                        "materials.verification_evidence_json",
                    ],
                    "material": {
                        "name": material["name"],
                        "description": material["description"],
                        "status": material["status"],
                        "original_filename": material["original_filename"],
                        "file_type": material["file_type"],
                        "file_size": material["file_size"],
                        "requirement_evidence": (
                            evidence.model_dump() if evidence is not None else None
                        ),
                        "verification": verification_payload,
                    },
                },
            }
        )

    # ---- 统计与事项摘要 ----
    per_matter_task_stats: dict[int, dict[str, int]] = defaultdict(
        lambda: {"unfinished": 0, "overdue": 0, "due_3": 0, "due_7": 0}
    )
    for task in tasks:
        if task.status == "done" or not participates(task.deadline_source, task.deadline):
            continue
        stats = per_matter_task_stats[task.matter_id]
        stats["unfinished"] += 1
        info = task_info[task.id]
        if info.status != "ok" or info.day is None:
            continue
        if is_overdue(info, moment):
            stats["overdue"] += 1
            continue
        left = days_left(info.day, today)
        if left <= 7:
            stats["due_7"] += 1
        if left <= 3:
            stats["due_3"] += 1

    stats = {
        "overdue_tasks": sum(value["overdue"] for value in per_matter_task_stats.values()),
        "due_soon_3d_tasks": sum(value["due_3"] for value in per_matter_task_stats.values()),
        "due_soon_7d_tasks": sum(value["due_7"] for value in per_matter_task_stats.values()),
        "unfinished_tasks": sum(1 for task in tasks if task.status != "done"),
        "pending_materials": sum(1 for m in materials if m["status"] == "pending"),
        "conflict_materials": sum(1 for m in materials if m["status"] == "conflict"),
        "missing_materials": sum(1 for m in materials if m["status"] == "missing"),
        "uncertain_materials": sum(1 for m in materials if m["status"] == "uncertain"),
        "matters_with_risks": len({candidate["matter_id"] for candidate in candidates.values()}),
    }

    summaries: dict[int, dict] = {}
    candidates_by_matter: dict[int, list[dict]] = defaultdict(list)
    for candidate in candidates.values():
        candidates_by_matter[candidate["matter_id"]].append(candidate)

    for matter in matters:
        info = parse_deadline(matter.deadline)
        state, left = _deadline_state(
            info,
            matter.deadline_source,
            moment,
            today,
            matter.status == "done",
        )
        matter_candidates = candidates_by_matter.get(matter.id, [])
        level = "low"
        for candidate in matter_candidates:
            if _LEVEL_WEIGHT[candidate["risk_level"]] > _LEVEL_WEIGHT[level]:
                level = candidate["risk_level"]

        # 事项截止日期本身可以提升整体风险，但不会赋给每一个任务。
        if state == "overdue":
            level = "high"
        elif state in {"today"}:
            level = "high"
        elif state == "due_soon" and left is not None and left <= 3:
            level = "high"

        matter_tasks = tasks_by_matter.get(matter.id, [])
        matter_materials = materials_by_matter.get(matter.id, [])
        task_stats = per_matter_task_stats.get(
            matter.id, {"unfinished": 0, "overdue": 0, "due_3": 0, "due_7": 0}
        )
        material_missing = sum(1 for item in matter_materials if item["status"] == "missing")
        material_pending = sum(1 for item in matter_materials if item["status"] == "pending")
        material_conflict = sum(1 for item in matter_materials if item["status"] == "conflict")

        parts: list[str] = []
        if matter.status == "done":
            # 已完成事项只说明完成状态，不再把未完成任务/材料计为风险描述。
            parts.append("事项已完成")
        else:
            if state == "overdue":
                parts.append(f"已超过事项截止日期 {_format_days(left)}")
            elif state == "today":
                parts.append("事项今天截止")
            elif state == "due_soon" and left is not None:
                parts.append(f"事项将在 {left} 天后截止")
            elif state == "unverified":
                parts.append("事项截止日期待核实")
            elif state == "suggested":
                parts.append("事项截止日期为系统建议，尚未应用")
            if task_stats["unfinished"]:
                parts.append(f"{task_stats['unfinished']} 个任务未完成")
            if task_stats["overdue"]:
                parts.append(f"{task_stats['overdue']} 个任务已逾期")
            if material_missing:
                parts.append(f"{material_missing} 项材料未提供")
            if material_pending:
                parts.append(f"{material_pending} 项材料待核验")
            if material_conflict:
                parts.append(f"{material_conflict} 项材料存在冲突")
        if not parts:
            parts.append("暂无风险")

        summaries[matter.id] = {
            "matter_id": matter.id,
            "matter_name": matter.name,
            "matter_status": matter.status,
            "deadline": matter.deadline,
            "deadline_source": matter.deadline_source,
            "deadline_state": state,
            "deadline_days_left": left,
            "unfinished_tasks": task_stats["unfinished"],
            "material_total": len(matter_materials),
            "material_missing": material_missing,
            "material_pending": material_pending,
            "material_conflict": material_conflict,
            "risk_total": len(matter_candidates),
            "level": level,
            "headline": "；".join(parts) + "。",
        }

    return AnalysisOutcome(
        candidates=list(candidates.values()),
        stats=stats,
        matter_summaries=summaries,
    )


def summarize_matter(matter_id: int) -> dict[str, Any] | None:
    outcome = analyze_risks()
    return outcome.matter_summaries.get(matter_id)
