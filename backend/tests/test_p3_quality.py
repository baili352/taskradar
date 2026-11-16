"""第四批 P3 收尾问题的专项回归测试。

所有数据库与上传目录均位于系统临时目录，不读写真实业务数据。
运行方式：在 backend 目录执行
    .venv\\Scripts\\python.exe -m unittest tests.test_p3_quality -v
"""

import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.api.routes import materials as material_routes  # noqa: E402
from app.db import database  # noqa: E402
from app.db.materials import (  # noqa: E402
    create_generated_materials,
    create_material,
    get_material,
    list_materials,
)
from app.db.matters import create_matter, list_matters  # noqa: E402
from app.db.risks import get_risk, list_risks, mark_risk_read, sync_risks  # noqa: E402
from app.db.tasks import create_task, delete_task  # noqa: E402
from app.schemas.material import MaterialCreate  # noqa: E402
from app.schemas.matter import MatterCreate  # noqa: E402
from app.schemas.task import TaskCreate  # noqa: E402
from app.services.documents.docx_reader import read_docx  # noqa: E402
from app.services.documents.errors import DocumentError  # noqa: E402
from app.services.documents.types import ExtractedDocument, Segment  # noqa: E402
from app.services.materials.storage import (  # noqa: E402
    resolve_stored_file,
    save_material_file,
)
from app.services.materials.verifier import verify_material  # noqa: E402
from app.services.risks.dates import (  # noqa: E402
    ensure_aware,
    is_overdue,
    now_in_timezone,
    parse_deadline,
)

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-p3q-"))


def _document(*texts: str) -> ExtractedDocument:
    return ExtractedDocument(
        filename="sample.txt",
        extension=".txt",
        size=10,
        segments=[
            Segment(text=text, location=f"第 {index + 1} 段", paragraph=index + 1)
            for index, text in enumerate(texts)
        ],
    )


def _candidate(matter_id: int, task_id: int | None = None, suffix: str = "overdue"):
    return {
        "fingerprint": f"{suffix}|matter:{matter_id}"
        + (f"|task:{task_id}" if task_id is not None else ""),
        "risk_type": suffix,
        "risk_level": "high",
        "title": "P3 风险测试",
        "description": "测试用风险",
        "matter_id": matter_id,
        "task_id": task_id,
        "material_id": None,
        "evidence": {"rule": "测试规则"},
        "suggestion": "处理建议",
    }


class _TempDatabaseCase(unittest.TestCase):
    """每个用例独立临时库与上传目录，避免相互影响。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="p3q-", dir=_TMP_ROOT)
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


class DateParsingTest(unittest.TestCase):
    """P3-01 / P3-05 / P3-19：日期边界、时区归一与真实日期校验。"""

    def test_iso_boundary_rejects_numeric_prefix(self) -> None:
        self.assertEqual(parse_deadline("12026-01-01").status, "unverified")

    def test_iso_boundary_rejects_longer_number(self) -> None:
        self.assertEqual(parse_deadline("2026-01-011").status, "unverified")

    def test_valid_iso_and_chinese_dates_still_parse(self) -> None:
        self.assertEqual(parse_deadline("2026-01-05").status, "ok")
        self.assertEqual(parse_deadline("2026年1月5日").status, "ok")
        self.assertEqual(parse_deadline("2026-01-05 10:30").status, "ok")

    def test_invalid_calendar_dates_rejected(self) -> None:
        for text in ("2026-02-30", "2026年2月30日", "2026-13-01", "2026-04-31"):
            with self.subTest(text=text):
                self.assertEqual(parse_deadline(text).status, "unverified")

    def test_naive_datetime_is_normalized(self) -> None:
        info = parse_deadline("2020-01-01")
        naive_now = datetime(2026, 1, 1, 12, 0, 0)
        self.assertEqual(
            ensure_aware(naive_now).utcoffset(),
            now_in_timezone().utcoffset(),
        )
        self.assertTrue(is_overdue(info, naive_now))

    def test_aware_and_naive_compare_without_type_error(self) -> None:
        info = parse_deadline("2030-01-01")
        self.assertFalse(is_overdue(info, datetime(2026, 1, 1, 0, 0, 0)))
        self.assertFalse(is_overdue(info, now_in_timezone()))


class RiskSystemTest(_TempDatabaseCase):
    """P3-02 / P3-03 / P3-04 / P3-11：已读、排序、并发刷新与历史保留。"""

    def test_mark_read_keeps_last_seen_at(self) -> None:
        matter = create_matter(MatterCreate(name="已读测试事项"))
        sync_risks([_candidate(matter.id)])
        total, items = list_risks(status="all")
        self.assertEqual(total, 1)
        before = items[0]
        result, after = mark_risk_read(before["id"])
        self.assertEqual(result, "ok")
        self.assertEqual(after["status"], "read")
        self.assertEqual(after["last_seen_at"], before["last_seen_at"])
        self.assertIsNotNone(after["read_at"])

    def test_list_ordering_is_stable(self) -> None:
        matter = create_matter(MatterCreate(name="排序测试事项"))
        sync_risks([_candidate(matter.id, suffix=name) for name in ("a", "b", "c")])
        _, first = list_risks(status="all")
        _, second = list_risks(status="all")
        self.assertEqual([item["id"] for item in first], [item["id"] for item in second])
        self.assertEqual(len(first), 3)

    def test_concurrent_refresh_does_not_raise_unique_conflict(self) -> None:
        matter = create_matter(MatterCreate(name="并发刷新事项"))
        candidate = _candidate(matter.id)
        errors: list[Exception] = []

        def worker() -> None:
            try:
                sync_risks([candidate])
            except Exception as error:  # noqa: BLE001 - 测试需要捕获全部异常
                errors.append(error)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        total, items = list_risks(status="all")
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["status"], "active")

    def test_delete_task_preserves_risk_history(self) -> None:
        matter = create_matter(MatterCreate(name="任务删除事项"))
        task = create_task(
            TaskCreate(matter_id=matter.id, title="待删除任务", description="")
        )
        sync_risks([_candidate(matter.id, task.id, "overdue")])
        _, items = list_risks(status="all")
        risk_id = items[0]["id"]

        self.assertTrue(delete_task(task.id))

        preserved = get_risk(risk_id)
        self.assertIsNotNone(preserved)
        self.assertEqual(preserved["status"], "resolved")
        self.assertIsNone(preserved["task_id"])
        self.assertEqual(preserved["title"], "P3 风险测试")


class MaterialGenerationTest(_TempDatabaseCase):
    """P3-12 / P3-15：批量生成事务与文件删除一致性。"""

    def _candidates(self) -> list[dict[str, object]]:
        return [
            {
                "name": "报名表",
                "description": "需填写姓名",
                "evidence": None,
                "step_key": "material:one",
            },
            {
                "name": "身份证复印件",
                "description": "需提交复印件",
                "evidence": None,
                "step_key": "material:two",
            },
        ]

    def test_batch_generation_succeeds_together(self) -> None:
        matter = create_matter(MatterCreate(name="批量生成事项"))
        created, skipped = create_generated_materials(matter.id, self._candidates())
        self.assertEqual(len(created), 2)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(list_materials(matter_id=matter.id)), 2)

    def test_batch_generation_rolls_back_on_error(self) -> None:
        matter = create_matter(MatterCreate(name="批量回滚事项"))
        calls = {"count": 0}
        original = material_routes.create_generated_materials

        def failing(matter_id: int, candidates):  # type: ignore[no-untyped-def]
            # 复用真实实现，但在第二次取回记录时模拟失败。
            real_fetch = __import__(
                "app.db.materials", fromlist=["_fetch"]
            )._fetch

            def fetch(conn, material_id):  # type: ignore[no-untyped-def]
                calls["count"] += 1
                if calls["count"] == 2:
                    raise sqlite3.OperationalError("模拟批量写入中断")
                return real_fetch(conn, material_id)

            with mock.patch("app.db.materials._fetch", fetch):
                return original(matter_id, candidates)

        with self.assertRaises(sqlite3.OperationalError):
            failing(matter.id, self._candidates())
        self.assertEqual(list_materials(matter_id=matter.id), [])

    def test_delete_material_removes_file_and_record(self) -> None:
        matter = create_matter(MatterCreate(name="删除一致性事项"))
        material = create_material(matter.id, MaterialCreate(name="报名表"))
        stored = save_material_file(material["id"], ".txt", "姓名：测试".encode("utf-8"))
        from app.db.materials import attach_file  # 局部导入避免顶部过长

        attach_file(
            material["id"],
            file_path=stored,
            original_filename="报名表.txt",
            file_size=14,
            file_type="txt",
        )
        path = resolve_stored_file(stored)
        self.assertTrue(path and path.is_file())

        response = material_routes.remove_material(material["id"])
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(get_material(material["id"]))
        self.assertFalse(path.exists())

    def test_delete_material_keeps_record_when_file_delete_fails(self) -> None:
        matter = create_matter(MatterCreate(name="删除失败保留事项"))
        material = create_material(matter.id, MaterialCreate(name="报名表"))
        stored = save_material_file(material["id"], ".txt", "姓名：测试".encode("utf-8"))
        from app.db.materials import attach_file  # 局部导入避免顶部过长

        attach_file(
            material["id"],
            file_path=stored,
            original_filename="报名表.txt",
            file_size=14,
            file_type="txt",
        )

        with mock.patch.object(
            material_routes, "delete_stored_file", return_value=False
        ):
            with self.assertRaises(HTTPException) as ctx:
                material_routes.remove_material(material["id"])
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIsNotNone(get_material(material["id"]))
        self.assertTrue(resolve_stored_file(stored).is_file())


class MatterListQueryTest(_TempDatabaseCase):
    """P3-16：事项筛选与分页下推到 SQL。"""

    def test_filter_and_pagination(self) -> None:
        for name in ("甲事项", "乙事项", "丙事项"):
            create_matter(MatterCreate(name=name))

        self.assertEqual(len(list_matters()), 3)
        self.assertEqual(len(list_matters(limit=1)), 1)
        self.assertEqual(len(list_matters(limit=1, offset=2)), 1)
        self.assertEqual(len(list_matters(keyword="乙")), 1)
        self.assertEqual(len(list_matters(status="pending")), 3)
        self.assertEqual(len(list_matters(status="done")), 0)


class VerifierMatchingTest(unittest.TestCase):
    """P3-13：关键词空白归一与否定表述不误判。"""

    def test_negated_phrase_is_not_flagged(self) -> None:
        verification = verify_material(
            {"name": "身份证复印件"},
            _document("身份证复印件，有效期至 2030 年，未过期。"),
        )
        self.assertNotIn("suspicious_phrases", {
            check.key for check in verification.checks if check.status == "unknown"
        })
        self.assertEqual(verification.result, "qualified")

    def test_real_suspicious_phrase_is_flagged(self) -> None:
        verification = verify_material(
            {"name": "身份证复印件"},
            _document("身份证复印件，已过期。"),
        )
        checks = {check.key: check for check in verification.checks}
        self.assertIn("suspicious_phrases", checks)
        self.assertEqual(checks["suspicious_phrases"].status, "unknown")
        self.assertEqual(verification.result, "uncertain")

    def test_keyword_with_spaces_still_matches(self) -> None:
        verification = verify_material(
            {"name": "成绩单"},
            _document("成绩 单：姓名 张三"),
        )
        checks = {check.key: check for check in verification.checks}
        self.assertEqual(checks["keyword_coverage"].status, "pass")


class DocumentErrorMessageTest(unittest.TestCase):
    """P3-17：损坏文档的统一安全提示，不泄漏内部信息。"""

    def test_corrupted_docx_message_is_fixed(self) -> None:
        with self.assertRaises(DocumentError) as ctx:
            read_docx("坏文件.docx", b"not-a-zip")
        self.assertEqual(ctx.exception.code, "invalid_document")
        self.assertIn("DOCX", ctx.exception.message)
        self.assertNotIn("Temp", ctx.exception.message)
        self.assertNotIn("Traceback", ctx.exception.message)
        self.assertNotIn(str(BACKEND), ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
