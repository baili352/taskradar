"""SQLite 数据库备份。

WAL 模式下最近提交的写入可能只存在于 `-wal` 文件中，尚未 checkpoint 回主库；
直接复制 `.db` 文件会静默丢掉这部分数据。SQLite Backup API 由引擎负责读取
主库与 WAL 中的全部已提交内容并写入目标副本，因此备份统一走这里。

用法（在 backend 目录下）：
    .\\.venv\\Scripts\\python.exe -c "from app.db.backup import backup_database; backup_database(r'D:\\backup\\taskradar.db')"
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from app.db.database import get_database_path


def backup_database(target_path: str) -> None:
    """把当前数据库完整备份到 target_path。

    使用 Connection.backup()，目标文件只包含已提交的数据；
    调用方无需处理 `-wal` / `-shm` 文件。
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(get_database_path())) as source, closing(
        sqlite3.connect(target)
    ) as destination:
        source.backup(destination)
