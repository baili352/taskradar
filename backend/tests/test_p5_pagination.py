"""P5 分页回归测试：任务与材料列表的 limit / offset 参数。

覆盖：
- 不传分页参数返回全部（响应仍是数组）；
- limit 截断、limit + offset 偏移，顺序与原有稳定排序一致；
- 非法 limit / offset 由 FastAPI 校验返回 422。

所有数据库与上传目录均位于系统临时目录，不读写真实业务数据。
运行方式：在 backend 目录执行
    .venv\\Scripts\\python.exe -m unittest tests.test_p5_pagination -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-p5-"))
# 单独运行时生效；被 discover 与其他测试模块一起加载时沿用已初始化的临时库。
os.environ.setdefault("DATABASE_PATH", str(_TMP_ROOT / "test.db"))
os.environ.setdefault("MATERIAL_UPLOAD_DIR", str(_TMP_ROOT / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.db import database  # noqa: E402
from app.db.materials import create_material  # noqa: E402
from app.db.matters import create_matter  # noqa: E402
from app.db.tasks import create_task  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.material import MaterialCreate  # noqa: E402
from app.schemas.matter import MatterCreate  # noqa: E402
from app.schemas.task import TaskCreate  # noqa: E402


def setUpModule() -> None:
    if Path(tempfile.gettempdir()).resolve() not in _TMP_ROOT.resolve().parents:
        raise RuntimeError(f"测试临时目录不在系统临时目录，已中止：{_TMP_ROOT}")


def tearDownModule() -> None:
    import shutil

    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


class PaginationTest(unittest.TestCase):
    """每个用例使用独立临时库，并直接通过 HTTP 接口验证参数校验。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="p5-", dir=_TMP_ROOT)
        root = Path(self.temp_dir.name)
        self.db_patch = mock.patch.object(
            database.settings, "database_path", str(root / "test.db")
        )
        self.upload_patch = mock.patch.object(
            database.settings, "material_upload_dir", str(root / "uploads")
        )
        self.db_patch.start()
        self.upload_patch.start()
        database.init_database()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.upload_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def _seed(self, task_count: int, material_count: int) -> tuple[int, list[int], list[int]]:
        matter = create_matter(MatterCreate(name="分页测试事项"))
        task_ids = [
            create_task(TaskCreate(matter_id=matter.id, title=f"任务 {index}")).id
            for index in range(task_count)
        ]
        material_ids = [
            create_material(matter.id, MaterialCreate(name=f"材料 {index}"))["id"]
            for index in range(material_count)
        ]
        return matter.id, task_ids, material_ids

    def _get(self, url: str):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertIsInstance(data, list, "响应结构应保持为数组")
        return data

    def test_tasks_without_pagination_returns_all(self) -> None:
        matter_id, task_ids, _ = self._seed(task_count=5, material_count=0)
        data = self._get(f"/api/tasks?matter_id={matter_id}")
        self.assertEqual(len(data), 5)
        # 稳定顺序：created_at 降序、id 降序。
        self.assertEqual([item["id"] for item in data], list(reversed(task_ids)))

    def test_tasks_limit_and_offset(self) -> None:
        matter_id, task_ids, _ = self._seed(task_count=5, material_count=0)
        expected = list(reversed(task_ids))

        limited = self._get(f"/api/tasks?matter_id={matter_id}&limit=2")
        self.assertEqual([item["id"] for item in limited], expected[:2])

        shifted = self._get(f"/api/tasks?matter_id={matter_id}&limit=2&offset=2")
        self.assertEqual([item["id"] for item in shifted], expected[2:4])

        boundary = self._get(f"/api/tasks?matter_id={matter_id}&limit=500")
        self.assertEqual(len(boundary), 5)

    def test_tasks_offset_without_limit_skips_rows(self) -> None:
        matter_id, _, _ = self._seed(task_count=5, material_count=0)
        full = self._get(f"/api/tasks?matter_id={matter_id}")
        shifted = self._get(f"/api/tasks?matter_id={matter_id}&offset=2")

        self.assertEqual(len(shifted), len(full) - 2)
        self.assertEqual(shifted[0]["id"], full[2]["id"])
        self.assertEqual(
            [item["id"] for item in shifted],
            [item["id"] for item in full][2:],
        )

    def test_materials_offset_without_limit_skips_rows(self) -> None:
        matter_id, _, _ = self._seed(task_count=0, material_count=4)
        full = self._get(f"/api/materials?matter_id={matter_id}")
        shifted = self._get(f"/api/materials?matter_id={matter_id}&offset=1")

        self.assertEqual(len(shifted), len(full) - 1)
        self.assertEqual(shifted[0]["id"], full[1]["id"])

    def test_offset_beyond_total_returns_empty_array(self) -> None:
        matter_id, _, _ = self._seed(task_count=2, material_count=2)
        for path in (
            f"/api/tasks?matter_id={matter_id}&offset=10",
            f"/api/materials?matter_id={matter_id}&offset=10",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), [])

    def test_tasks_invalid_pagination_rejected(self) -> None:
        for query in ("limit=0", "limit=501", "offset=-1"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/tasks?{query}")
                self.assertEqual(response.status_code, 422, response.text)

    def test_materials_without_pagination_returns_all(self) -> None:
        matter_id, _, material_ids = self._seed(task_count=0, material_count=4)
        data = self._get(f"/api/materials?matter_id={matter_id}")
        self.assertEqual(len(data), 4)
        self.assertEqual(
            [item["id"] for item in data], list(reversed(material_ids))
        )

    def test_materials_limit_and_offset(self) -> None:
        matter_id, _, material_ids = self._seed(task_count=0, material_count=4)
        expected = list(reversed(material_ids))

        limited = self._get(f"/api/materials?matter_id={matter_id}&limit=2")
        self.assertEqual([item["id"] for item in limited], expected[:2])

        shifted = self._get(
            f"/api/materials?matter_id={matter_id}&limit=2&offset=2"
        )
        self.assertEqual([item["id"] for item in shifted], expected[2:4])

        boundary = self._get(f"/api/materials?matter_id={matter_id}&limit=500")
        self.assertEqual(len(boundary), 4)

    def test_materials_invalid_pagination_rejected(self) -> None:
        for query in ("limit=0", "limit=501", "offset=-1"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/materials?{query}")
                self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
