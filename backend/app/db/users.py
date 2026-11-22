"""用户与登录会话的读写。

密码只保存 PBKDF2 哈希；会话只保存令牌的 SHA-256 摘要，
即使数据库文件泄露也无法直接还原密码或冒用登录态。
"""

from datetime import datetime

from app.db.database import get_connection


def create_user(username: str, password_hash: str, created_at: str) -> dict:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, created_at),
        )
        return {"id": int(cursor.lastrowid), "username": username}


def get_user_by_username(username: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, created_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def count_users() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return int(row[0]) if row else 0


def create_session(
    user_id: int, token_hash: str, created_at: str, expires_at: str
) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token_hash, user_id, created_at, expires_at),
        )


def get_user_by_session(token_hash: str) -> dict | None:
    """按令牌摘要取用户；过期会话视为未登录，不返回用户。"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT u.id, u.username, s.expires_at "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ?",
            (token_hash,),
        ).fetchone()
    if row is None:
        return None
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at <= datetime.now(expires_at.tzinfo):
        return None
    return {"id": int(row["id"]), "username": row["username"]}


def delete_session(token_hash: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def purge_expired_sessions(now_iso: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_iso,))
