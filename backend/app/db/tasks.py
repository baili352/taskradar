"""任务表的真实读写。

列表证据以 JSON 文本保存在 source_evidence_json 列中，读取时还原为对象。
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any

from app.db.database import get_connection
from app.db.pagination import apply_pagination
from app.schemas.matter import MatterEvidence
from app.schemas.task import TaskCreate, TaskRecord, TaskUpdate
from app.services.risks.dates import now_in_timezone

logger = logging.getLogger(__name__)

_SELECT_COLUMNS = """
    t.id, t.matter_id, t.title, t.description, t.deadline, t.deadline_source,
    t.priority, t.status, t.origin, t.source_evidence_json,
    COALESCE(mt.is_demo, 0) AS is_demo,
    t.created_at, t.updated_at
"""

_FROM = "FROM tasks t LEFT JOIN matters mt ON mt.id = t.matter_id"


def _now() -> str:
    # 毫秒精度，保证同一秒内的更新也能体现 updated_at 变化。
    return datetime.now().isoformat(timespec="milliseconds")


def _parse_evidence(raw: str | None) -> MatterEvidence | None:
    if not raw:
        return None
    try:
        return MatterEvidence.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as error:
        logger.warning("任务来源证据解析失败：%s", error)
        return None


def _row_to_task(row) -> TaskRecord:
    return TaskRecord(
        id=row["id"],
        matter_id=row["matter_id"],
        title=row["title"],
        description=row["description"],
        deadline=row["deadline"],
        deadline_source=row["deadline_source"],
        priority=row["priority"],
        status=row["status"],
        origin=row["origin"],
        source_evidence=_parse_evidence(row["source_evidence_json"]),
        is_demo=bool(row["is_demo"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_task(
    payload: TaskCreate,
    *,
    origin: str = "manual",
    step_key: str | None = None,
    evidence: MatterEvidence | None = None,
) -> TaskRecord:
    """新增任务。生成任务时携带 step_key，唯一索引会拦截重复步骤。"""
    now = _now()
    deadline = payload.deadline or None
    source = payload.deadline_source or ("manual" if deadline else "none")
    if not deadline:
        source = "none"
    evidence_json = evidence.model_dump_json() if evidence else None

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                matter_id, title, description, deadline, deadline_source,
                priority, status, source_evidence_json, step_key, origin,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.matter_id,
                payload.title,
                payload.description,
                deadline,
                source,
                payload.priority,
                payload.status,
                evidence_json,
                step_key,
                origin,
                now,
                now,
            ),
        )
        task_id = int(cursor.lastrowid)
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} {_FROM} WHERE t.id = ?", (task_id,)
        ).fetchone()

    return _row_to_task(row)


def try_create_generated_task(
    matter_id: int,
    title: str,
    description: str,
    priority: str,
    deadline: str | None,
    step_key: str,
    evidence: MatterEvidence,
) -> TaskRecord | None:
    """生成任务专用：命中唯一索引时返回 None，表示该步骤已存在。"""
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO tasks (
                matter_id, title, description, deadline, deadline_source,
                priority, status, source_evidence_json, step_key, origin,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, 'generated', ?, ?)
            """,
            (
                matter_id,
                title,
                description,
                deadline,
                "document" if deadline else "none",
                priority,
                evidence.model_dump_json(),
                step_key,
                now,
                now,
            ),
        )
        if cursor.rowcount == 0:
            return None
        task_id = int(cursor.lastrowid)
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} {_FROM} WHERE t.id = ?", (task_id,)
        ).fetchone()

    return _row_to_task(row)


def list_tasks(
    matter_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[TaskRecord]:
    conditions: list[str] = []
    params: list[Any] = []
    if matter_id is not None:
        conditions.append("t.matter_id = ?")
        params.append(matter_id)
    if status is not None:
        conditions.append("t.status = ?")
        params.append(status)
    if priority is not None:
        conditions.append("t.priority = ?")
        params.append(priority)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = (
        f"SELECT {_SELECT_COLUMNS} {_FROM} {where} "
        "ORDER BY datetime(t.created_at) DESC, t.id DESC"
    )
    sql, params = apply_pagination(sql, params, limit, offset)

    if conn is not None:
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_task(row) for row in rows]

    with get_connection() as own:
        rows = own.execute(sql, params).fetchall()

    return [_row_to_task(row) for row in rows]


def get_task(task_id: int) -> TaskRecord | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} {_FROM} WHERE t.id = ?", (task_id,)
        ).fetchone()
    return _row_to_task(row) if row else None


def update_task(task_id: int, payload: TaskUpdate) -> TaskRecord | None:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return None

    if "deadline" in data:
        data["deadline"] = data["deadline"] or None
        if not data["deadline"]:
            # 清空截止日期时来源回到 none。
            data["deadline_source"] = "none"
        elif data.get("deadline_source") in (None, "suggested"):
            # 用户确认（应用系统建议）或手动填写时统一按 manual 保存；
            # suggested 不能直接落库，否则永远不会参与风险判断。
            data["deadline_source"] = "manual"

    data["updated_at"] = _now()
    assignments = ", ".join(f"{column} = ?" for column in data)
    params = list(data.values()) + [task_id]

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?", params
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} {_FROM} WHERE t.id = ?", (task_id,)
        ).fetchone()

    return _row_to_task(row)


def delete_task(task_id: int) -> bool:
    """删除任务；保留其关联风险的历史记录。

    risks.task_id 原本是 ON DELETE CASCADE，删除任务会连带删除风险历史。
    这里先把风险与任务解绑并标记为已解决，再删除任务，
    使风险记录、标题与判断依据仍可追溯。
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE risks SET status = 'resolved', resolved_at = ?, task_id = NULL "
            "WHERE task_id = ? AND status <> 'resolved'",
            (now_in_timezone().isoformat(timespec="milliseconds"), task_id),
        )
        conn.execute(
            "UPDATE risks SET task_id = NULL WHERE task_id = ?", (task_id,)
        )
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0


def count_tasks(matter_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM tasks WHERE matter_id = ?", (matter_id,)
        ).fetchone()
    return int(row["total"])
