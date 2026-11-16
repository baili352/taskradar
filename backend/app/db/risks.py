"""风险提醒表的真实读写。

设计：
- 指纹唯一，重复刷新只更新状态与依据，不会重复创建；
- 风险消失时标记为 resolved 并保留历史；
- 风险重新出现时恢复为 active，first_seen_at 保持不变。
"""

import json
import logging
from typing import Any

from app.db.database import get_connection
from app.services.risks.dates import now_in_timezone

logger = logging.getLogger(__name__)

_SELECT_COLUMNS = """
    r.id, r.fingerprint, r.risk_type, r.risk_level, r.title, r.description,
    r.matter_id, COALESCE(mt.name, '') AS matter_name,
    r.task_id, t.title AS task_title,
    r.material_id, mat.name AS material_name,
    r.evidence_json, r.suggestion, r.status,
    COALESCE(mt.is_demo, 0) AS is_demo,
    r.first_seen_at, r.last_seen_at, r.read_at, r.resolved_at
"""

_FROM = """
FROM risks r
LEFT JOIN matters mt ON mt.id = r.matter_id
LEFT JOIN tasks t ON t.id = r.task_id
LEFT JOIN materials mat ON mat.id = r.material_id
"""

_LEVEL_ORDER_SQL = (
    "CASE r.risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"
)
# 显式状态权重，避免依赖字符串排序（active < read < resolved 只是巧合）。
_STATUS_ORDER_SQL = (
    "CASE r.status WHEN 'active' THEN 0 WHEN 'read' THEN 1 ELSE 2 END"
)


def _now() -> str:
    return now_in_timezone().isoformat(timespec="milliseconds")


def _parse_evidence(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("风险证据不是合法 JSON：%s", raw[:80])
        return None
    return value if isinstance(value, dict) else None


def _row_to_risk(row) -> dict:
    return {
        "id": row["id"],
        "fingerprint": row["fingerprint"],
        "risk_type": row["risk_type"],
        "risk_level": row["risk_level"],
        "title": row["title"],
        "description": row["description"],
        "matter_id": row["matter_id"],
        "matter_name": row["matter_name"],
        "task_id": row["task_id"],
        "task_title": row["task_title"],
        "material_id": row["material_id"],
        "material_name": row["material_name"],
        "evidence": _parse_evidence(row["evidence_json"]),
        "suggestion": row["suggestion"],
        "status": row["status"],
        "is_demo": bool(row["is_demo"]),
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "read_at": row["read_at"],
        "resolved_at": row["resolved_at"],
    }


def _status_clause(status: str | None, params: list[Any]) -> str:
    if status in (None, "all"):
        return ""
    if status == "unresolved":
        return " AND r.status IN ('active', 'read')"
    params.append(status)
    return " AND r.status = ?"


def _build_filters(
    *,
    risk_type: str | None = None,
    level: str | None = None,
    status: str | None = None,
    matter_id: int | None = None,
    task_id: int | None = None,
    material_id: int | None = None,
) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if risk_type:
        conditions.append("r.risk_type = ?")
        params.append(risk_type)
    if level:
        conditions.append("r.risk_level = ?")
        params.append(level)
    if matter_id is not None:
        conditions.append("r.matter_id = ?")
        params.append(matter_id)
    if task_id is not None:
        conditions.append("r.task_id = ?")
        params.append(task_id)
    if material_id is not None:
        conditions.append("r.material_id = ?")
        params.append(material_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else "WHERE 1 = 1"
    where += _status_clause(status, params)
    return where, params


def sync_risks(candidates: list[dict]) -> dict:
    """把本次分析结果与数据库对齐，返回创建/更新/恢复/解决数量。"""
    now = _now()
    created = updated = revived = resolved = 0

    with get_connection() as conn:
        # 立即获取写锁，串行化并发刷新，避免两个刷新同时读到“不存在”后
        # 同时插入同一 fingerprint 触发唯一索引冲突。
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id, fingerprint, status FROM risks"
        ).fetchall()
        existing = {row["fingerprint"]: row for row in rows}
        seen: set[str] = set()

        for candidate in candidates:
            fingerprint = candidate["fingerprint"]
            seen.add(fingerprint)
            evidence_json = (
                json.dumps(candidate["evidence"], ensure_ascii=False)
                if candidate.get("evidence") is not None
                else None
            )
            values = (
                candidate["risk_type"],
                candidate["risk_level"],
                candidate["title"],
                candidate.get("description", ""),
                candidate["matter_id"],
                candidate.get("task_id"),
                candidate.get("material_id"),
                evidence_json,
                candidate.get("suggestion", ""),
            )
            row = existing.get(fingerprint)
            if row is None:
                conn.execute(
                    """
                    INSERT INTO risks (
                        fingerprint, risk_type, risk_level, title, description,
                        matter_id, task_id, material_id, evidence_json, suggestion,
                        status, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (fingerprint, *values, now, now),
                )
                created += 1
                continue

            if row["status"] == "resolved":
                # 风险重新出现：恢复为活动状态，保留首次发现时间。
                conn.execute(
                    """
                    UPDATE risks SET
                        risk_type = ?, risk_level = ?, title = ?, description = ?,
                        matter_id = ?, task_id = ?, material_id = ?,
                        evidence_json = ?, suggestion = ?,
                        status = 'active', read_at = NULL, resolved_at = NULL,
                        last_seen_at = ?
                    WHERE id = ?
                    """,
                    (*values, now, row["id"]),
                )
                revived += 1
            else:
                # 已读状态保持不变，只刷新判断依据与最后出现时间。
                conn.execute(
                    """
                    UPDATE risks SET
                        risk_type = ?, risk_level = ?, title = ?, description = ?,
                        matter_id = ?, task_id = ?, material_id = ?,
                        evidence_json = ?, suggestion = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (*values, now, row["id"]),
                )
                updated += 1

        for fingerprint, row in existing.items():
            if fingerprint in seen or row["status"] == "resolved":
                continue
            conn.execute(
                "UPDATE risks SET status = 'resolved', resolved_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            resolved += 1

    return {
        "created": created,
        "updated": updated,
        "revived": revived,
        "resolved": resolved,
    }


def list_risks(
    *,
    risk_type: str | None = None,
    level: str | None = None,
    status: str | None = "unresolved",
    matter_id: int | None = None,
    task_id: int | None = None,
    material_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    where, params = _build_filters(
        risk_type=risk_type,
        level=level,
        status=status,
        matter_id=matter_id,
        task_id=task_id,
        material_id=material_id,
    )
    with get_connection() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS total {_FROM} {where}", params
        ).fetchone()
        rows = conn.execute(
            f"SELECT {_SELECT_COLUMNS} {_FROM} {where} "
            f"ORDER BY {_LEVEL_ORDER_SQL}, {_STATUS_ORDER_SQL}, "
            "datetime(r.last_seen_at) DESC, r.id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return int(total_row["total"]), [_row_to_risk(row) for row in rows]


def get_risk(risk_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} {_FROM} WHERE r.id = ?", (risk_id,)
        ).fetchone()
    return _row_to_risk(row) if row else None


def mark_risk_read(risk_id: int) -> tuple[str, dict | None]:
    """返回 (结果, 记录)：not_found / resolved / ok。"""
    now = _now()
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} {_FROM} WHERE r.id = ?", (risk_id,)
        ).fetchone()
        if row is None:
            return "not_found", None
        if row["status"] == "resolved":
            return "resolved", _row_to_risk(row)
        if row["status"] == "active":
            # 标记已读只写入 read_at，不修改 last_seen_at：
            # 最后出现时间由风险分析刷新维护，不能因用户阅读而前移。
            conn.execute(
                "UPDATE risks SET status = 'read', read_at = ? WHERE id = ?",
                (now, risk_id),
            )
            row = conn.execute(
                f"SELECT {_SELECT_COLUMNS} {_FROM} WHERE r.id = ?", (risk_id,)
            ).fetchone()
        return "ok", _row_to_risk(row)


def count_risks() -> dict:
    """统计未解决风险与历史风险数量，供仪表盘使用。"""
    with get_connection() as conn:
        level_rows = conn.execute(
            "SELECT risk_level, COUNT(*) AS total FROM risks "
            "WHERE status IN ('active', 'read') GROUP BY risk_level"
        ).fetchall()
        type_rows = conn.execute(
            "SELECT risk_type, COUNT(*) AS total FROM risks "
            "WHERE status IN ('active', 'read') GROUP BY risk_type"
        ).fetchall()
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS total FROM risks GROUP BY status"
        ).fetchall()
        matter_row = conn.execute(
            "SELECT COUNT(DISTINCT matter_id) AS total FROM risks "
            "WHERE status IN ('active', 'read')"
        ).fetchone()

    by_level = {row["risk_level"]: int(row["total"]) for row in level_rows}
    by_type = {row["risk_type"]: int(row["total"]) for row in type_rows}
    by_status = {row["status"]: int(row["total"]) for row in status_rows}

    active = by_status.get("active", 0)
    read = by_status.get("read", 0)
    resolved = by_status.get("resolved", 0)
    return {
        "active": active,
        "read": read,
        "resolved": resolved,
        "total_unresolved": active + read,
        "total_risks": active + read + resolved,
        "high": by_level.get("high", 0),
        "medium": by_level.get("medium", 0),
        "low": by_level.get("low", 0),
        "by_type": by_type,
        "matters_with_risks": int(matter_row["total"]),
    }
