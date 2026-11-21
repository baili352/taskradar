"""WAL 与 SQLite Backup API 备份测试。

覆盖：
- get_connection() 后 journal_mode 为 wal，且连接期间存在 -wal / -shm；
- 已提交但尚未 checkpoint 的记录，备份文件中必须能读到；
- 两个线程并发写入不抛异常且总数正确。

所有数据库均位于系统临时目录，不读写真实业务数据。
"""

import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-p6wal-"))
os.environ.setdefault("DATABASE_PATH", str(_TMP_ROOT / "test.db"))
os.environ.setdefault("MATERIAL_UPLOAD_DIR", str(_TMP_ROOT / "uploads"))

from app.db import database  # noqa: E402
from app.db.backup import backup_database  # noqa: E402
from app.db.database import get_connection  # noqa: E402
from app.services.risks.dates import now_in_timezone  # noqa: E402


def _insert_matter(conn, name: str) -> None:
    now = now_in_timezone().isoformat(timespec="milliseconds")
    conn.execute(
        "INSERT INTO matters (name, created_at, updated_at) VALUES (?, ?, ?)",
        (name, now, now),
    )


class WalBackupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="p6wal-", dir=_TMP_ROOT)
        self.root = Path(self.temp_dir.name)
        self.db_patch = mock.patch.object(
            database.settings, "database_path", str(self.root / "test.db")
        )
        self.upload_patch = mock.patch.object(
            database.settings, "material_upload_dir", str(self.root / "uploads")
        )
        self.db_patch.start()
        self.upload_patch.start()
        database.init_database()

    def tearDown(self) -> None:
        self.upload_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_journal_mode_is_wal(self) -> None:
        db_path = database.get_database_path()
        with get_connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(str(mode).lower(), "wal")
            # -wal / -shm 在 WAL 模式首次写入时创建，因此先写入再检查。
            _insert_matter(conn, "WAL 写入验证")
            conn.commit()
            self.assertTrue(Path(f"{db_path}-wal").exists(), "WAL 模式下应生成 -wal 文件")
            self.assertTrue(Path(f"{db_path}-shm").exists(), "WAL 模式下应生成 -shm 文件")

    def test_backup_contains_data_still_in_wal(self) -> None:
        target = self.root / "backup" / "taskradar-backup.db"
        with get_connection() as conn:
            _insert_matter(conn, "仍在 WAL 中的记录")
            # 先提交但保持连接打开：数据可能仍在 -wal 中，尚未 checkpoint 回主库。
            conn.commit()
            backup_database(str(target))

        self.assertTrue(target.exists())
        self.assertGreater(target.stat().st_size, 0)
        with closing(sqlite3.connect(target)) as backup_conn:
            row = backup_conn.execute(
                "SELECT COUNT(*) FROM matters WHERE name = ?", ("仍在 WAL 中的记录",)
            ).fetchone()
        self.assertEqual(int(row[0]), 1, "备份必须包含仍在 -wal 中的已提交记录")

    def test_concurrent_writers(self) -> None:
        per_thread = 25
        errors: list[Exception] = []

        def worker(prefix: str) -> None:
            try:
                for index in range(per_thread):
                    with get_connection() as conn:
                        _insert_matter(conn, f"{prefix}-{index}")
            except Exception as exc:  # noqa: BLE001 - 收集后统一断言
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(prefix,)) for prefix in ("A", "B")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [], f"并发写入不应抛异常：{errors}")
        with get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0]
        self.assertEqual(int(total), per_thread * 2, "两线程写入的记录都应落库")


if __name__ == "__main__":
    unittest.main()
