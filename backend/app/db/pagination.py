"""列表查询的分页子句拼接。

统一处理 limit / offset 组合，避免各模块重复实现时漏掉「只有 offset」的情况：
SQLite 的 OFFSET 必须依附于 LIMIT，用 LIMIT -1 表示不限制行数。
"""

from typing import Any


def apply_pagination(
    sql: str,
    params: list[Any],
    limit: int | None,
    offset: int,
) -> tuple[str, list[Any]]:
    """返回追加分页子句后的 SQL 与参数。

    - 不传 limit 且 offset 为 0：不追加任何子句，保持原全量查询；
    - 不传 limit 但 offset > 0：追加 ``LIMIT -1 OFFSET ?``，让 offset 生效；
    - 传 limit：追加 ``LIMIT ?``，offset > 0 时再追加 ``OFFSET ?``。
    """
    if limit is None:
        if not offset:
            return sql, params
        return f"{sql} LIMIT -1 OFFSET ?", [*params, offset]

    sql = f"{sql} LIMIT ?"
    params = [*params, limit]
    if offset:
        return f"{sql} OFFSET ?", [*params, offset]
    return sql, params
