"""SQLite 连接与初始化。

第一阶段建立的 app_meta 表必须保留；后续阶段只追加新表，
并通过 schema_version 记录结构版本，不重置、不删除已有数据。

注意：项目现有架构使用 Python 标准库 sqlite3，而不是 SQLAlchemy，
因此事项与任务持久化继续沿用同一套连接方式。
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager, closing
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 7

# journal_mode 切换需要独占锁且不走 busy 等待；并发首次连接时用锁串行化，
# 避免两个线程同时切换抛出 database is locked。
_PRAGMA_LOCK = threading.Lock()

_MATTERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS matters (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL,
    matter_type        TEXT NOT NULL DEFAULT '',
    qualification      TEXT NOT NULL DEFAULT '',
    registration_start TEXT,
    deadline           TEXT,
    deadline_source    TEXT NOT NULL DEFAULT 'none',
    materials_json     TEXT NOT NULL DEFAULT '[]',
    process_json       TEXT NOT NULL DEFAULT '[]',
    notes_json         TEXT NOT NULL DEFAULT '[]',
    fields_json        TEXT NOT NULL DEFAULT '[]',
    source_filename    TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'pending',
    analysis_mode      TEXT NOT NULL DEFAULT 'rule_based',
    is_demo            INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
)
"""

_MATTERS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_matters_created_at ON matters (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_matters_status ON matters (status)",
)

_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id            INTEGER NOT NULL REFERENCES matters (id) ON DELETE CASCADE,
    title                TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    deadline             TEXT,
    deadline_source      TEXT NOT NULL DEFAULT 'none',
    priority             TEXT NOT NULL DEFAULT 'medium',
    status               TEXT NOT NULL DEFAULT 'pending',
    source_evidence_json TEXT,
    step_key             TEXT,
    origin               TEXT NOT NULL DEFAULT 'manual',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
)
"""

_TASKS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_tasks_matter ON tasks (matter_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status)",
    # 同一事项下同一流程步骤只允许一条任务，数据库层面兜底防重复生成。
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_matter_step "
    "ON tasks (matter_id, step_key) WHERE step_key IS NOT NULL",
)

_MATERIALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS materials (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                   INTEGER NOT NULL REFERENCES matters (id) ON DELETE CASCADE,
    name                        TEXT NOT NULL,
    description                 TEXT NOT NULL DEFAULT '',
    status                      TEXT NOT NULL DEFAULT 'missing',
    file_path                   TEXT,
    original_filename           TEXT,
    file_size                   INTEGER,
    file_type                   TEXT,
    verification_result         TEXT,
    verification_evidence_json  TEXT,
    verified_at                 TEXT,
    source_evidence_json        TEXT,
    step_key                    TEXT,
    origin                      TEXT NOT NULL DEFAULT 'manual',
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL
)
"""

_MATERIALS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_materials_matter ON materials (matter_id)",
    "CREATE INDEX IF NOT EXISTS idx_materials_status ON materials (status)",
    # 同一事项下同一材料要求只生成一条，数据库层兜底防重复。
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_materials_matter_step "
    "ON materials (matter_id, step_key) WHERE step_key IS NOT NULL",
)

_MATERIAL_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS material_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL REFERENCES materials (id) ON DELETE CASCADE,
    action      TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
)
"""

_MATERIAL_EVENTS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_material_events_material "
    "ON material_events (material_id)",
)

_RISKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS risks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT NOT NULL,
    risk_type     TEXT NOT NULL,
    risk_level    TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    matter_id     INTEGER NOT NULL REFERENCES matters (id) ON DELETE CASCADE,
    task_id       INTEGER REFERENCES tasks (id) ON DELETE CASCADE,
    material_id   INTEGER REFERENCES materials (id) ON DELETE CASCADE,
    evidence_json TEXT,
    suggestion    TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'active',
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    read_at       TEXT,
    resolved_at   TEXT
)
"""

_RISKS_INDEX_SQL = (
    # 稳定指纹保证同一风险不会被重复创建。
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_risks_fingerprint ON risks (fingerprint)",
    "CREATE INDEX IF NOT EXISTS idx_risks_status ON risks (status)",
    "CREATE INDEX IF NOT EXISTS idx_risks_type ON risks (risk_type)",
    "CREATE INDEX IF NOT EXISTS idx_risks_level ON risks (risk_level)",
    "CREATE INDEX IF NOT EXISTS idx_risks_matter ON risks (matter_id)",
    "CREATE INDEX IF NOT EXISTS idx_risks_task ON risks (task_id)",
    "CREATE INDEX IF NOT EXISTS idx_risks_material ON risks (material_id)",
)

# schema_version 7：登录注册。用户与登录会话独立于业务数据，
# 不改变事项/任务/材料/风险的归属与查询。
_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
)
"""

_SESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
)
"""

_SESSIONS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at)",
)


def get_database_path() -> Path:
    """返回数据库文件的绝对路径，相对路径基于 backend 目录解析。"""
    path = Path(settings.database_path)
    if not path.is_absolute():
        path = settings.base_dir / path
    return path


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """提供带行工厂的连接，退出时提交并关闭。

    WAL 模式下读不阻塞写，最近提交的数据可能仍在 -wal 文件中，
    因此备份必须走 SQLite Backup API，不能直接复制 .db 文件。
    """
    conn = sqlite3.connect(get_database_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        # 开启外键约束，避免产生指向不存在事项的任务。
        conn.execute("PRAGMA foreign_keys = ON")
        # 并发读写与崩溃安全：WAL 提升读写并发，NORMAL 在 WAL 下足够安全；
        # busy_timeout 让并发写入排队等待，而不是立刻抛 database is locked。
        with _PRAGMA_LOCK:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_matter_deadline_source(conn: sqlite3.Connection) -> None:
    """第四阶段第四步迁移：为事项补充截止日期来源，不重建表、不丢数据。

    历史事项的截止日期来源需要尽量准确：有来源文件（source_filename 非空）
    说明由文档解析得到，回填为 document；手动创建的事项截止日期由用户填写，
    回填为 manual，避免把它们误标成原文日期而参与错误的到期判断。
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(matters)")}
    if "deadline_source" in columns:
        return
    conn.execute(
        "ALTER TABLE matters ADD COLUMN deadline_source TEXT NOT NULL DEFAULT 'none'"
    )
    conn.execute(
        "UPDATE matters SET deadline_source = 'document' "
        "WHERE deadline IS NOT NULL AND TRIM(deadline) <> '' "
        "AND TRIM(COALESCE(source_filename, '')) <> ''"
    )
    conn.execute(
        "UPDATE matters SET deadline_source = 'manual' "
        "WHERE deadline IS NOT NULL AND TRIM(deadline) <> '' "
        "AND TRIM(COALESCE(source_filename, '')) = ''"
    )


def _ensure_matter_demo_flag(conn: sqlite3.Connection) -> None:
    """第五阶段第三步迁移：为事项补充演示数据标记。

    历史事项默认 is_demo = 0，全部按正式数据对待；
    演示数据只通过显式的初始化接口写入，且清理时只删除 is_demo = 1 的事项。
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(matters)")}
    if "is_demo" in columns:
        return
    conn.execute(
        "ALTER TABLE matters ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0"
    )


def _has_user_tables(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone() is not None


def _read_schema_version(conn: sqlite3.Connection) -> int:
    """在任何结构变更前读取版本；缺少元数据的历史库按版本 1 处理。"""
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_meta'"
    ).fetchone()
    if not has_meta:
        return 1
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return 1
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("数据库 schema_version 无效，已停止初始化以避免覆盖数据。") from exc


def _matter_deadline_migration_needed(conn: sqlite3.Connection) -> bool:
    has_matters = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'matters'"
    ).fetchone()
    if not has_matters:
        return False
    columns = {row[1] for row in conn.execute("PRAGMA table_info(matters)")}
    return "deadline_source" not in columns


def _matter_demo_migration_needed(conn: sqlite3.Connection) -> bool:
    has_matters = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'matters'"
    ).fetchone()
    if not has_matters:
        return False
    columns = {row[1] for row in conn.execute("PRAGMA table_info(matters)")}
    return "is_demo" not in columns


def _create_migration_backup(
    conn: sqlite3.Connection, path: Path, previous_version: int
) -> Path:
    """在写事务开始前用 SQLite Backup API 创建并校验可恢复副本。"""
    backup_dir = path.parent / "migration_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / (
        f"{path.stem}.v{previous_version}-to-v{SCHEMA_VERSION}.{timestamp}{path.suffix}"
    )
    try:
        with closing(sqlite3.connect(backup_path)) as backup_conn:
            conn.backup(backup_conn)
            result = backup_conn.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise RuntimeError("迁移前备份完整性校验失败，已中止迁移。")
    except Exception:
        # 只清理本次未完成的备份，绝不触碰原数据库或历史备份。
        backup_path.unlink(missing_ok=True)
        raise
    logger.info("数据库迁移前备份已创建：%s", backup_path)
    return backup_path


def init_database() -> None:
    """原子化创建或迁移数据库；任何一步失败都不会留下半完成结构。"""
    path = get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # autocommit 模式下显式开启写事务，确保 DDL、数据回填和版本号同生共死。
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        previous_version = _read_schema_version(conn)
        if previous_version > SCHEMA_VERSION:
            raise RuntimeError("数据库结构版本高于当前程序支持版本，已停止启动。")

        has_existing_data = _has_user_tables(conn)
        if has_existing_data and (
            previous_version < SCHEMA_VERSION
            or _matter_deadline_migration_needed(conn)
            or _matter_demo_migration_needed(conn)
        ):
            _create_migration_backup(conn, path, previous_version)

        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            # 保留已有 app_meta 记录，仅补齐缺失的版本键。
            conn.execute(
                "INSERT OR IGNORE INTO app_meta (key, value) VALUES (?, ?)",
                ("schema_version", "1"),
            )
            conn.execute(_MATTERS_TABLE_SQL)
            for statement in _MATTERS_INDEX_SQL:
                conn.execute(statement)
            conn.execute(_TASKS_TABLE_SQL)
            for statement in _TASKS_INDEX_SQL:
                conn.execute(statement)
            conn.execute(_MATERIALS_TABLE_SQL)
            for statement in _MATERIALS_INDEX_SQL:
                conn.execute(statement)
            conn.execute(_MATERIAL_EVENTS_TABLE_SQL)
            for statement in _MATERIAL_EVENTS_INDEX_SQL:
                conn.execute(statement)

            # schema_version 4 -> 5：追加事项截止日期来源与风险提醒表。
            _ensure_matter_deadline_source(conn)
            # schema_version 5 -> 6：追加演示数据标记，正式数据默认不受影响。
            _ensure_matter_demo_flag(conn)
            conn.execute(_RISKS_TABLE_SQL)
            for statement in _RISKS_INDEX_SQL:
                conn.execute(statement)

            # schema_version 6 -> 7：登录注册所需的用户与会话表。
            conn.execute(_USERS_TABLE_SQL)
            conn.execute(_SESSIONS_TABLE_SQL)
            for statement in _SESSIONS_INDEX_SQL:
                conn.execute(statement)

            if previous_version != SCHEMA_VERSION:
                conn.execute(
                    "UPDATE app_meta SET value = ? WHERE key = ?",
                    (str(SCHEMA_VERSION), "schema_version"),
                )
            conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            logger.exception("数据库初始化或迁移失败，事务已回滚：%s", path)
            raise


def check_database() -> bool:
    """健康检查用：确认数据库可连接且可查询。"""
    try:
        with sqlite3.connect(get_database_path()) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
