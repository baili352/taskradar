"""演示数据原地刷新测试。

覆盖：
- 已初始化时普通 seed 保持幂等，数量、截止日期与初始化时间都不变；
- refresh=True 会清空重建，三个演示事项的截止日期按调用当天重新计算；
- 刷新前后正式数据（is_demo = 0）的事项、任务、材料、风险与材料文件完全不变；
- 刷新后 demo/ 目录只保留当前被引用的文件；
- 风险阶段失败时整体回滚，刷新前的演示数据与 demo/ 文件原样保留。

所有数据库与上传目录均位于系统临时目录，不读写真实业务数据。
运行方式：在 backend 目录执行
    .venv\\Scripts\\python.exe -m unittest tests.test_p5_demo_refresh -v
"""

import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-p5refresh-"))
# 单独运行时生效；被 discover 与其他测试模块一起加载时沿用已初始化的临时库。
os.environ.setdefault("DATABASE_PATH", str(_TMP_ROOT / "test.db"))
os.environ.setdefault("MATERIAL_UPLOAD_DIR", str(_TMP_ROOT / "uploads"))

from app.db import database  # noqa: E402
from app.db.materials import attach_file, create_material  # noqa: E402
from app.db.matters import create_matter  # noqa: E402
from app.db.tasks import create_task  # noqa: E402
from app.schemas.material import MaterialCreate  # noqa: E402
from app.schemas.matter import MatterCreate  # noqa: E402
from app.schemas.task import TaskCreate  # noqa: E402
from app.services.demo.seed import (  # noqa: E402
    DEMO_DIR_NAME,
    clear_demo_data,
    seed_demo_data,
)
from app.services.materials.storage import (  # noqa: E402
    get_upload_root,
    resolve_stored_file,
    save_material_file,
)
from app.services.risks.dates import now_in_timezone, today_in_timezone  # noqa: E402


class DemoRefreshTest(unittest.TestCase):
    """幂等、刷新与正式数据隔离三组断言。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="p5refresh-", dir=_TMP_ROOT)
        self.root = Path(self.temp_dir.name)
        self.db_patch = mock.patch.object(
            database.settings, "database_path", str(self.root / "test.db")
        )
        self.upload_patch = mock.patch.object(
            database.settings,
            "material_upload_dir",
            str(self.root / "uploads"),
        )
        self.db_patch.start()
        self.upload_patch.start()
        database.init_database()

    def tearDown(self) -> None:
        self.upload_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    # ---- 查询辅助 -------------------------------------------------------

    def _demo_matters(self):
        with database.get_connection() as conn:
            return conn.execute(
                "SELECT id, name, deadline, created_at FROM matters "
                "WHERE is_demo = 1 ORDER BY id"
            ).fetchall()

    def _demo_counts(self) -> dict[str, int]:
        with database.get_connection() as conn:
            def count(sql: str) -> int:
                return int(conn.execute(sql).fetchone()[0])

            return {
                "matters": count("SELECT COUNT(*) FROM matters WHERE is_demo = 1"),
                "tasks": count(
                    "SELECT COUNT(*) FROM tasks t JOIN matters m ON m.id = t.matter_id "
                    "WHERE m.is_demo = 1"
                ),
                "materials": count(
                    "SELECT COUNT(*) FROM materials ma JOIN matters m ON m.id = ma.matter_id "
                    "WHERE m.is_demo = 1"
                ),
                "risks": count(
                    "SELECT COUNT(*) FROM risks r JOIN matters m ON m.id = r.matter_id "
                    "WHERE m.is_demo = 1"
                ),
            }

    def _real_counts(self) -> dict[str, int]:
        with database.get_connection() as conn:
            def count(sql: str) -> int:
                return int(conn.execute(sql).fetchone()[0])

            return {
                "matters": count("SELECT COUNT(*) FROM matters WHERE is_demo = 0"),
                "tasks": count(
                    "SELECT COUNT(*) FROM tasks t JOIN matters m ON m.id = t.matter_id "
                    "WHERE m.is_demo = 0"
                ),
                "materials": count(
                    "SELECT COUNT(*) FROM materials ma JOIN matters m ON m.id = ma.matter_id "
                    "WHERE m.is_demo = 0"
                ),
                "risks": count(
                    "SELECT COUNT(*) FROM risks r JOIN matters m ON m.id = r.matter_id "
                    "WHERE m.is_demo = 0"
                ),
            }

    def _create_real_data(self) -> dict:
        """写入一条正式事项、任务、材料（含真实文件）与风险。"""
        matter = create_matter(MatterCreate(name="正式事项：刷新隔离验证"))
        create_task(TaskCreate(matter_id=matter.id, title="正式任务", deadline="2026-12-31"))

        material = create_material(matter.id, MaterialCreate(name="正式材料"))
        content = "正式材料内容，刷新演示数据时不得改变。".encode("utf-8")
        relative = save_material_file(matter.id, ".txt", content)
        attach_file(
            material_id=material["id"],
            file_path=relative,
            original_filename="正式材料.txt",
            file_size=len(content),
            file_type="TXT",
        )

        now = now_in_timezone().isoformat(timespec="milliseconds")
        with database.get_connection() as conn:
            conn.execute(
                "INSERT INTO risks (fingerprint, risk_type, risk_level, title, description, "
                "matter_id, status, first_seen_at, last_seen_at) "
                "VALUES ('test-real-refresh', 'deadline_approaching', 'low', "
                "'正式风险', '', ?, 'active', ?, ?)",
                (matter.id, now, now),
            )

        stored = resolve_stored_file(relative)
        self.assertIsNotNone(stored)
        return {
            "matter_id": matter.id,
            "file_path": relative,
            "file_bytes": Path(stored).read_bytes(),
        }

    # ---- 用例 -----------------------------------------------------------

    def test_seed_without_refresh_keeps_demo_data(self) -> None:
        first = seed_demo_data()
        self.assertTrue(first.seeded)
        self.assertFalse(first.refreshed)

        counts_before = self._demo_counts()
        deadlines_before = [row["deadline"] for row in self._demo_matters()]
        seeded_at_before = first.seeded_at

        second = seed_demo_data()
        self.assertTrue(second.seeded)
        self.assertFalse(second.refreshed, "非 refresh 调用不应标记为刷新")
        self.assertEqual(self._demo_counts(), counts_before)
        self.assertEqual(
            [row["deadline"] for row in self._demo_matters()], deadlines_before
        )
        self.assertEqual(second.seeded_at, seeded_at_before)

    def test_refresh_recomputes_deadlines_and_keeps_counts(self) -> None:
        seed_demo_data()
        counts_before = self._demo_counts()
        seeded_at_before = self._demo_matters()[0]["created_at"]

        # 模拟演示日期随天数漂移：把所有演示截止日期整体前移 5 天。
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE matters SET deadline = date(deadline, '-5 day') WHERE is_demo = 1"
            )
        drifted = [row["deadline"] for row in self._demo_matters()]
        self.assertNotEqual(drifted, [None, None, None])

        status = seed_demo_data(refresh=True)
        self.assertTrue(status.seeded)
        self.assertTrue(status.refreshed, "已初始化后 refresh=True 应标记为刷新")

        today = today_in_timezone()
        expected = [
            (today + timedelta(days=12)).isoformat(),
            (today + timedelta(days=-2)).isoformat(),
            (today + timedelta(days=21)).isoformat(),
        ]
        rows = self._demo_matters()
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["deadline"] for row in rows], expected)
        self.assertEqual(self._demo_counts(), counts_before)
        self.assertGreaterEqual(rows[0]["created_at"], seeded_at_before)

        # 刷新后 demo/ 只保留当前被引用的文件，不残留旧文件名。
        with database.get_connection() as conn:
            referenced = {
                Path(row[0]).name
                for row in conn.execute(
                    "SELECT file_path FROM materials WHERE file_path LIKE 'demo/%'"
                ).fetchall()
                if row[0]
            }
        folder = get_upload_root() / DEMO_DIR_NAME
        self.assertEqual({path.name for path in folder.iterdir()}, referenced)

    def test_refresh_does_not_touch_real_data(self) -> None:
        real = self._create_real_data()
        real_counts_before = self._real_counts()

        seed_demo_data()
        self.assertEqual(self._real_counts(), real_counts_before)

        status = seed_demo_data(refresh=True)
        self.assertTrue(status.refreshed)
        self.assertEqual(self._real_counts(), real_counts_before, "正式数据数量不应变化")

        stored = resolve_stored_file(real["file_path"])
        self.assertIsNotNone(stored, "正式材料文件不应被删除")
        self.assertEqual(Path(stored).read_bytes(), real["file_bytes"], "正式文件内容不应变化")

        # 刷新后仍可按正式事项 id 取到事项本身。
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT is_demo FROM matters WHERE id = ?", (real["matter_id"],)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(int(row["is_demo"]), 0)

    def test_refresh_failure_rolls_back_and_keeps_old_demo_data(self) -> None:
        """风险阶段失败时不得清空旧演示数据，也不得留下孤立文件。"""
        seed_demo_data()
        matters_before = [
            (row["id"], row["name"], row["deadline"], row["created_at"])
            for row in self._demo_matters()
        ]
        counts_before = self._demo_counts()
        folder = get_upload_root() / DEMO_DIR_NAME
        files_before = {path.name for path in folder.iterdir()}

        with mock.patch(
            "app.services.demo.seed._seed_risk_rows",
            side_effect=RuntimeError("模拟风险写入失败"),
        ):
            with self.assertRaises(RuntimeError):
                seed_demo_data(refresh=True)

        rows_after = self._demo_matters()
        self.assertEqual(len(rows_after), 3, "刷新失败后演示事项数量必须保持不变")
        self.assertEqual(
            [
                (row["id"], row["name"], row["deadline"], row["created_at"])
                for row in rows_after
            ],
            matters_before,
            "刷新失败后演示事项、截止日期与创建时间必须与刷新前完全一致",
        )
        self.assertEqual(self._demo_counts(), counts_before, "演示任务、材料、风险应整体回滚")

        self.assertEqual(
            {path.name for path in folder.iterdir()},
            files_before,
            "刷新失败后 demo/ 不应新增未被引用的孤立文件",
        )


if __name__ == "__main__":
    unittest.main()
