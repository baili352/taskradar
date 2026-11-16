"""材料清单与核验记录的真实读写（标准库 sqlite3）。"""

import json
import logging
from datetime import datetime
from typing import Any

from app.db.database import get_connection
from app.schemas.material import (
    MaterialCreate,
    MaterialEventRecord,
    MaterialUpdate,
    MaterialVerification,
)
from app.schemas.matter import MatterEvidence

logger = logging.getLogger(__name__)

_SELECT_COLUMNS = """
    m.id, m.matter_id, COALESCE(mt.name, '') AS matter_name,
    m.name, m.description, m.status,
    m.file_path, m.original_filename, m.file_size, m.file_type,
    m.verification_result, m.verification_evidence_json, m.verified_at,
    m.source_evidence_json, m.origin,
    COALESCE(mt.is_demo, 0) AS is_demo,
    m.created_at, m.updated_at
"""

_FROM = "FROM materials m LEFT JOIN matters mt ON mt.id = m.matter_id"


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def _parse_evidence(raw: str | None) -> MatterEvidence | None:
    if not raw:
        return None
    try:
        return MatterEvidence.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as error:
        logger.warning("材料来源证据解析失败：%s", error)
        return None


def _parse_verification(raw: str | None) -> MaterialVerification | None:
    if not raw:
        return None
    try:
        return MaterialVerification.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as error:
        logger.warning("材料核验记录解析失败：%s", error)
        return None


def _row_to_material(row) -> dict:
    return {
        "id": row["id"],
        "matter_id": row["matter_id"],
        "matter_name": row["matter_name"],
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "file_path": row["file_path"],
        "original_filename": row["original_filename"],
        "file_size": row["file_size"],
        "file_type": row["file_type"],
        "verification": _parse_verification(row["verification_evidence_json"]),
        "source_evidence": _parse_evidence(row["source_evidence_json"]),
        "origin": row["origin"],
        "is_demo": bool(row["is_demo"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "events": [],
    }


def _fetch(conn, material_id: int):
    return conn.execute(
        f"SELECT {_SELECT_COLUMNS} {_FROM} WHERE m.id = ?", (material_id,)
    ).fetchone()


def add_event(material_id: int, action: str, detail: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO material_events (material_id, action, detail, created_at) "
            "VALUES (?, ?, ?, ?)",
            (material_id, action, detail, _now()),
        )


def create_material(matter_id: int, payload: MaterialCreate) -> dict:
    now = _now()
    evidence_json = (
        payload.source_evidence.model_dump_json() if payload.source_evidence else None
    )
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO materials (
                matter_id, name, description, status, source_evidence_json,
                origin, created_at, updated_at
            ) VALUES (?, ?, ?, 'missing', ?, 'manual', ?, ?)
            """,
            (matter_id, payload.name, payload.description, evidence_json, now, now),
        )
        material_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO material_events (material_id, action, detail, created_at) "
            "VALUES (?, 'created', '手动新增材料', ?)",
            (material_id, now),
        )
        row = _fetch(conn, material_id)
    return _row_to_material(row)


def try_create_generated_material(
    matter_id: int,
    name: str,
    description: str,
    evidence: MatterEvidence | None,
    step_key: str,
) -> dict | None:
    """命中唯一索引时返回 None，表示该材料要求已生成过。"""
    now = _now()
    evidence_json = evidence.model_dump_json() if evidence else None
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO materials (
                matter_id, name, description, status, source_evidence_json,
                step_key, origin, created_at, updated_at
            ) VALUES (?, ?, ?, 'missing', ?, ?, 'generated', ?, ?)
            """,
            (matter_id, name, description, evidence_json, step_key, now, now),
        )
        if cursor.rowcount == 0:
            return None
        material_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO material_events (material_id, action, detail, created_at) "
            "VALUES (?, 'generated', '由事项材料要求生成', ?)",
            (material_id, now),
        )
        row = _fetch(conn, material_id)
    return _row_to_material(row)


def list_materials(
    matter_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    conditions: list[str] = []
    params: list[Any] = []
    if matter_id is not None:
        conditions.append("m.matter_id = ?")
        params.append(matter_id)
    if status is not None:
        conditions.append("m.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_SELECT_COLUMNS} {_FROM} {where} "
            "ORDER BY datetime(m.created_at) DESC, m.id DESC",
            params,
        ).fetchall()
    return [_row_to_material(row) for row in rows]


def get_material(material_id: int, with_events: bool = False) -> dict | None:
    with get_connection() as conn:
        row = _fetch(conn, material_id)
        if row is None:
            return None
        material = _row_to_material(row)
        if with_events:
            events = conn.execute(
                "SELECT id, action, detail, created_at FROM material_events "
                "WHERE material_id = ? ORDER BY id ASC",
                (material_id,),
            ).fetchall()
            material["events"] = [
                MaterialEventRecord(
                    id=event["id"],
                    action=event["action"],
                    detail=event["detail"],
                    created_at=event["created_at"],
                )
                for event in events
            ]
    return material


def update_material(material_id: int, payload: MaterialUpdate) -> dict | None:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return None
    data["updated_at"] = _now()
    assignments = ", ".join(f"{column} = ?" for column in data)
    params = list(data.values()) + [material_id]

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE materials SET {assignments} WHERE id = ?", params
        )
        if cursor.rowcount == 0:
            return None
        conn.execute(
            "INSERT INTO material_events (material_id, action, detail, created_at) "
            "VALUES (?, 'updated', '修改材料信息', ?)",
            (material_id, data["updated_at"]),
        )
        row = _fetch(conn, material_id)
    return _row_to_material(row)


def attach_file(
    material_id: int,
    file_path: str,
    original_filename: str,
    file_size: int,
    file_type: str,
) -> dict | None:
    """保存文件元信息，状态回到「待核验」并清空旧核验结论。"""
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE materials SET
                file_path = ?, original_filename = ?, file_size = ?, file_type = ?,
                status = 'pending', verification_result = NULL,
                verification_evidence_json = NULL, verified_at = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (file_path, original_filename, file_size, file_type, now, material_id),
        )
        if cursor.rowcount == 0:
            return None
        conn.execute(
            "INSERT INTO material_events (material_id, action, detail, created_at) "
            "VALUES (?, 'file_uploaded', ?, ?)",
            (material_id, f"上传文件：{original_filename}", now),
        )
        row = _fetch(conn, material_id)
    return _row_to_material(row)


def save_verification(
    material_id: int, verification: MaterialVerification
) -> dict | None:
    """保存核验记录，并把材料状态同步为核验结论。"""
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE materials SET
                status = ?, verification_result = ?,
                verification_evidence_json = ?, verified_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                verification.result,
                verification.result,
                verification.model_dump_json(),
                verification.verified_at,
                now,
                material_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        action = "verified" if verification.source == "rule" else "confirmed"
        conn.execute(
            "INSERT INTO material_events (material_id, action, detail, created_at) "
            "VALUES (?, ?, ?, ?)",
            (material_id, action, verification.summary, now),
        )
        row = _fetch(conn, material_id)
    return _row_to_material(row)


def create_generated_materials(
    matter_id: int, candidates: list[dict[str, object]]
) -> tuple[list[dict], int]:
    """在同一事务中批量生成材料，返回 (已创建材料, 跳过数量)。

    任何一步失败都会让整个事务回滚，不会出现“只生成了一部分”的中间状态。
    """
    now = _now()
    created: list[dict] = []
    skipped = 0
    with get_connection() as conn:
        for candidate in candidates:
            evidence = candidate.get("evidence")
            evidence_json = (
                evidence.model_dump_json()
                if isinstance(evidence, MatterEvidence)
                else None
            )
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO materials (
                    matter_id, name, description, status, source_evidence_json,
                    step_key, origin, created_at, updated_at
                ) VALUES (?, ?, ?, 'missing', ?, ?, 'generated', ?, ?)
                """,
                (
                    matter_id,
                    str(candidate["name"]),
                    str(candidate["description"]),
                    evidence_json,
                    str(candidate["step_key"]),
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 0:
                skipped += 1
                continue
            material_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO material_events (material_id, action, detail, created_at) "
                "VALUES (?, 'generated', '由事项材料要求生成', ?)",
                (material_id, now),
            )
            created.append(_row_to_material(_fetch(conn, material_id)))
    return created, skipped


def delete_material(material_id: int) -> tuple[bool, str | None]:
    """删除记录，返回 (是否找到并删除, 文件相对路径)。

    未上传文件的材料 file_path 为 NULL，因此不能用 None 表示“材料不存在”。
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT file_path FROM materials WHERE id = ?", (material_id,)
        ).fetchone()
        if row is None:
            return False, None
        conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    return True, row["file_path"]


def progress_for_matter(matter_id: int) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS total FROM materials WHERE matter_id = ? "
            "GROUP BY status",
            (matter_id,),
        ).fetchall()
        uploaded = conn.execute(
            "SELECT COUNT(*) AS total FROM materials "
            "WHERE matter_id = ? AND file_path IS NOT NULL",
            (matter_id,),
        ).fetchone()["total"]

    counts = {row["status"]: int(row["total"]) for row in rows}
    total = sum(counts.values())
    return {
        "matter_id": matter_id,
        "total": total,
        "missing": counts.get("missing", 0),
        "provided": int(uploaded),
        "pending": counts.get("pending", 0),
        "qualified": counts.get("qualified", 0),
        "incomplete": counts.get("incomplete", 0),
        "conflict": counts.get("conflict", 0),
        "uncertain": counts.get("uncertain", 0),
        "prepared_percent": round(uploaded / total * 100) if total else 0,
        "verified_percent": round(counts.get("qualified", 0) / total * 100)
        if total
        else 0,
    }
