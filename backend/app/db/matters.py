"""事项表读写（标准库 sqlite3）。

所有分析结果（材料、流程、注意事项、字段证据）以 JSON 文本保存，
读取时还原为结构化对象，原文证据不会在持久化过程中丢失。
"""

import json
import logging
from datetime import datetime
from typing import Any

from app.db.database import get_connection
from app.schemas.matter import MatterCreate, MatterRecord, MatterUpdate

logger = logging.getLogger(__name__)

_LIST_COLUMNS = {
    "materials": "materials_json",
    "process": "process_json",
    "notes": "notes_json",
    "fields": "fields_json",
}

_INSERT_SQL = """
INSERT INTO matters (
    name, matter_type, qualification, registration_start, deadline, deadline_source,
    materials_json, process_json, notes_json, fields_json,
    source_filename, status, analysis_mode, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _now() -> str:
    # 毫秒精度，保证同一秒内的更新也能体现 updated_at 变化。
    return datetime.now().isoformat(timespec="milliseconds")


def _load_list(raw: str, matter_id: int, column: str) -> list:
    try:
        value = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        logger.warning("事项 %s 的 %s 不是合法 JSON，已按空列表处理", matter_id, column)
        return []
    return value if isinstance(value, list) else []


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "matter_type": row["matter_type"],
        "qualification": row["qualification"],
        "registration_start": row["registration_start"],
        "deadline": row["deadline"],
        "deadline_source": row["deadline_source"],
        "materials": _load_list(row["materials_json"], row["id"], "materials_json"),
        "process": _load_list(row["process_json"], row["id"], "process_json"),
        "notes": _load_list(row["notes_json"], row["id"], "notes_json"),
        "fields": _load_list(row["fields_json"], row["id"], "fields_json"),
        "source_filename": row["source_filename"],
        "status": row["status"],
        "analysis_mode": row["analysis_mode"],
        "is_demo": bool(row["is_demo"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _dumps(items: list) -> str:
    return json.dumps(items, ensure_ascii=False)


def create_matter(payload: MatterCreate) -> MatterRecord:
    now = _now()
    # 截止日期来源：调用方未显式提供时，默认按“用户手动设置”处理。
    deadline = payload.deadline or None
    deadline_source = payload.deadline_source or ("manual" if deadline else "none")
    with get_connection() as conn:
        cursor = conn.execute(
            _INSERT_SQL,
            (
                payload.name,
                payload.matter_type,
                payload.qualification,
                payload.registration_start,
                deadline,
                deadline_source,
                _dumps([item.model_dump() for item in payload.materials]),
                _dumps([item.model_dump() for item in payload.process]),
                _dumps([item.model_dump() for item in payload.notes]),
                _dumps([item.model_dump() for item in payload.fields]),
                payload.source_filename,
                payload.status,
                payload.analysis_mode,
                now,
                now,
            ),
        )
        matter_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM matters WHERE id = ?", (matter_id,)).fetchone()

    return MatterRecord(**_row_to_dict(row))


def list_matters(
    status: str | None = None,
    keyword: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[MatterRecord]:
    """查询事项列表，筛选与分页尽量下推到 SQL，避免无必要的全表读取。"""
    conditions: list[str] = []
    params: list[Any] = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    text = (keyword or "").strip()
    if text:
        conditions.append("name LIKE ?")
        params.append(f"%{text}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM matters {where} ORDER BY datetime(created_at) DESC, id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
        if offset:
            sql += " OFFSET ?"
            params.append(offset)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [MatterRecord(**_row_to_dict(row)) for row in rows]


def get_matter(matter_id: int) -> MatterRecord | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM matters WHERE id = ?", (matter_id,)).fetchone()
    return MatterRecord(**_row_to_dict(row)) if row else None


def update_matter(matter_id: int, payload: MatterUpdate) -> MatterRecord | None:
    data = payload.model_dump(exclude_unset=True)

    if "deadline" in data:
        data["deadline"] = data["deadline"] or None
        if "deadline_source" not in data:
            # 用户手动修改截止日期时标记为 manual；清空时回到 none。
            data["deadline_source"] = "manual" if data["deadline"] else "none"

    assignments: list[str] = []
    values: list[object] = []

    for key, value in data.items():
        if key in _LIST_COLUMNS:
            assignments.append(f"{_LIST_COLUMNS[key]} = ?")
            values.append(_dumps([item for item in value] if isinstance(value, list) else []))
            continue
        assignments.append(f"{key} = ?")
        values.append(value)

    if not assignments:
        return get_matter(matter_id)

    assignments.append("updated_at = ?")
    values.append(_now())
    values.append(matter_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE matters SET {', '.join(assignments)} WHERE id = ?",
            tuple(values),
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM matters WHERE id = ?", (matter_id,)).fetchone()

    return MatterRecord(**_row_to_dict(row))
