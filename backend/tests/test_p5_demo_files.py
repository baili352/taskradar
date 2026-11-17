"""演示数据材料文件与清理逻辑一致性测试（方案 A：seed 写文件，clear 回收目录）。

覆盖：
- seed 后演示材料在上传根目录的 demo/ 下确有可读文件，且数据库记录可解析；
- clear 后 demo/ 目录被回收；
- 正式数据（is_demo = 0）的事项、材料与文件不受影响；
- 清理范围限定在 demo/，不触碰上传根目录外的文件或同名前缀目录。

所有数据库与上传目录均位于系统临时目录，不读写真实业务数据。
运行方式：在 backend 目录执行
    .venv\\Scripts\\python.exe -m unittest tests.test_p5_demo_files -v
"""

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-p5demo-"))
# 单独运行时生效；被 discover 与其他测试模块一起加载时沿用已初始化的临时库。
os.environ.setdefault("DATABASE_PATH", str(_TMP_ROOT / "test.db"))
os.environ.setdefault("MATERIAL_UPLOAD_DIR", str(_TMP_ROOT / "uploads"))

from app.db import database  # noqa: E402
from app.db.materials import attach_file, create_material, get_material  # noqa: E402
from app.db.matters import create_matter, get_matter  # noqa: E402
from app.schemas.material import MaterialCreate  # noqa: E402
from app.schemas.matter import MatterCreate  # noqa: E402
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

_DEMO_PATH_PATTERN = re.compile(rf"^{DEMO_DIR_NAME}/[^/]+$")


class DemoMaterialFileTest(unittest.TestCase):
    """三步验证：seed → 文件存在 → clear → 目录回收。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="p5demo-", dir=_TMP_ROOT)
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

    def _demo_material_rows(self):
        with database.get_connection() as conn:
            return conn.execute(
                "SELECT m.id, m.file_path, m.original_filename "
                "FROM materials m JOIN matters mt ON mt.id = m.matter_id "
                "WHERE mt.is_demo = 1 ORDER BY m.id"
            ).fetchall()

    def test_seed_writes_demo_files_and_clear_removes_directory(self) -> None:
        status = seed_demo_data()
        self.assertTrue(status.seeded)
        self.assertEqual(status.matters, 3)

        demo_dir = get_upload_root() / DEMO_DIR_NAME
        self.assertTrue(demo_dir.is_dir(), "seed 后应创建 demo/ 目录")
        files_on_disk = sorted(path.name for path in demo_dir.iterdir())
        self.assertTrue(files_on_disk, "seed 后 demo/ 目录不应为空")

        rows = self._demo_material_rows()
        with_files = [row for row in rows if row["file_path"]]
        self.assertTrue(with_files, "演示材料中应存在带文件的记录")
        self.assertEqual(len(files_on_disk), len(with_files))

        for row in with_files:
            with self.subTest(material_id=row["id"]):
                self.assertRegex(row["file_path"], _DEMO_PATH_PATTERN)
                path = resolve_stored_file(row["file_path"])
                self.assertIsNotNone(path, "演示材料文件应可通过受控路径解析")
                self.assertEqual(path.parent, demo_dir)
                # 文件内容真实可读，而不是只有数据库记录。
                self.assertTrue(path.read_text(encoding="utf-8").strip())

        # 准备正式数据与干扰文件，验证清理不会误伤。
        real_matter = create_matter(MatterCreate(name="正式事项"))
        real_material = create_material(
            real_matter.id, MaterialCreate(name="正式材料")
        )
        content = "正式材料内容".encode("utf-8")
        relative = save_material_file(real_matter.id, ".txt", content)
        attach_file(
            material_id=real_material["id"],
            file_path=relative,
            original_filename="正式材料.txt",
            file_size=len(content),
            file_type="TXT",
        )
        real_file = resolve_stored_file(relative)
        self.assertIsNotNone(real_file)

        outside_file = self.root / "outside.txt"
        outside_file.write_text("上传根目录之外的文件", encoding="utf-8")
        lookalike = get_upload_root() / f"{DEMO_DIR_NAME}-backup"
        lookalike.mkdir()
        (lookalike / "keep.txt").write_text("同名前缀目录", encoding="utf-8")

        cleared, removed = clear_demo_data()
        self.assertEqual(removed, 3)
        self.assertFalse(cleared.seeded)
        self.assertFalse(demo_dir.exists(), "清理后 demo/ 目录应被回收")

        self.assertTrue(real_file.is_file(), "正式材料文件不应被删除")
        self.assertIsNotNone(get_material(real_material["id"]))
        self.assertIsNotNone(get_matter(real_matter.id))
        self.assertTrue(outside_file.is_file(), "上传根目录外的文件不应被触碰")
        self.assertTrue(lookalike.joinpath("keep.txt").is_file())

    def test_clear_without_seed_is_safe_and_idempotent(self) -> None:
        status, removed = clear_demo_data()
        self.assertEqual(removed, 0)
        self.assertFalse(status.seeded)
        self.assertFalse((get_upload_root() / DEMO_DIR_NAME).exists())

        # 再次清理同样不报错、不产生目录。
        again, removed_again = clear_demo_data()
        self.assertEqual(removed_again, 0)
        self.assertFalse(again.seeded)


if __name__ == "__main__":
    unittest.main()
