"""第五阶段第三批 P2-06～P2-11 专项回归测试。

所有数据库和上传文件均位于系统临时目录，不读取或修改真实业务数据。
运行方式：在 backend 目录执行
    .venv\\Scripts\\python.exe -m unittest tests.test_p3_fixes -v
"""

import asyncio
import io
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest import mock

import fitz
from docx import Document as DocxDocument
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-p3-"))
os.environ.setdefault("DATABASE_PATH", str(_TMP_ROOT / "test.db"))
os.environ.setdefault("MATERIAL_UPLOAD_DIR", str(_TMP_ROOT / "uploads"))

from app.api.routes import analysis, materials as material_routes, risks as risk_routes  # noqa: E402
from app.db import database  # noqa: E402
from app.db.materials import create_material, get_material  # noqa: E402
from app.db.matters import create_matter, update_matter  # noqa: E402
from app.db.tasks import create_task  # noqa: E402
from app.schemas.material import MaterialCreate  # noqa: E402
from app.schemas.matter import MatterCreate, MatterUpdate  # noqa: E402
from app.schemas.task import TaskCreate  # noqa: E402
from app.services.documents import validators  # noqa: E402
from app.services.documents.docx_reader import read_docx  # noqa: E402
from app.services.documents.errors import DocumentError  # noqa: E402
from app.services.documents.pdf_reader import read_pdf  # noqa: E402
from app.services.documents.txt_reader import read_txt  # noqa: E402
from app.services.materials.storage import resolve_stored_file  # noqa: E402


def setUpModule() -> None:
    db_path = database.get_database_path().resolve()
    if Path(tempfile.gettempdir()).resolve() not in db_path.parents:
        raise RuntimeError(f"测试数据库不在系统临时目录，已中止：{db_path}")


def tearDownModule() -> None:
    import shutil

    db_path = database.get_database_path().resolve()
    if _TMP_ROOT.resolve() in db_path.parents:
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)


def _schema4_matters_sql() -> str:
    """由当前表定义构造模拟 v4 结构；它不是历史真实数据库样本。"""
    return database._MATTERS_TABLE_SQL.replace(
        "    deadline_source    TEXT NOT NULL DEFAULT 'none',\n", ""
    )


def _create_schema4_copy(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO app_meta VALUES ('schema_version', '4')")
        conn.execute(_schema4_matters_sql())
        conn.execute(
            "INSERT INTO matters (name, deadline, source_filename, created_at, updated_at) "
            "VALUES ('有截止日期', '2026-12-01', '通知.docx', '2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO matters (name, deadline, source_filename, created_at, updated_at) "
            "VALUES ('手动截止日期', '2026-12-05', '', '2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO matters (name, deadline, created_at, updated_at) "
            "VALUES ('无截止日期', NULL, '2026-01-01', '2026-01-01')"
        )
        conn.commit()


def _schema_version(path: Path) -> str:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(
            "SELECT value FROM app_meta WHERE key = 'schema_version'"
        ).fetchone()[0]


def _matter_columns(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(matters)")}


class MigrationAtomicityTest(unittest.TestCase):
    """P2-06：模拟 v4 临时库的正常迁移、失败回滚与可恢复备份。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="migration-", dir=_TMP_ROOT
        )
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "copy.db"
        self.path_patch = mock.patch.object(
            database.settings, "database_path", str(self.db_path)
        )
        self.path_patch.start()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def _backups(self) -> list[Path]:
        return sorted((self.root / "migration_backups").glob("*.db"))

    def test_normal_migration_backup_restart_and_repeat(self) -> None:
        _create_schema4_copy(self.db_path)
        database.init_database()

        self.assertEqual(_schema_version(self.db_path), "6")
        self.assertIn("deadline_source", _matter_columns(self.db_path))
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT name, deadline_source FROM matters ORDER BY id"
            ).fetchall()
            self.assertEqual(
                rows,
                [
                    ("有截止日期", "document"),
                    ("手动截止日期", "manual"),
                    ("无截止日期", "none"),
                ],
            )
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(_schema_version(backups[0]), "4")
        self.assertNotIn("deadline_source", _matter_columns(backups[0]))
        with closing(sqlite3.connect(backups[0])) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0], 3)

        # 再次启动及字段已存在时应幂等，不重复备份或回填。
        database.init_database()
        self.assertEqual(len(self._backups()), 1)
        self.assertEqual(_schema_version(self.db_path), "6")
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0], 3
            )

    def test_interrupted_migration_rolls_back_then_restart_succeeds(self) -> None:
        _create_schema4_copy(self.db_path)

        def interrupt_after_alter(conn: sqlite3.Connection) -> None:
            conn.execute(
                "ALTER TABLE matters ADD COLUMN deadline_source "
                "TEXT NOT NULL DEFAULT 'none'"
            )
            raise RuntimeError("模拟补字段后、回填前中断")

        with mock.patch.object(
            database, "_ensure_matter_deadline_source", side_effect=interrupt_after_alter
        ):
            with self.assertRaisesRegex(RuntimeError, "模拟"):
                database.init_database()

        self.assertEqual(_schema_version(self.db_path), "4")
        self.assertNotIn("deadline_source", _matter_columns(self.db_path))
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0], 3)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(len(self._backups()), 1)

        # 故障修复后再次启动可从原状态完整迁移。
        database.init_database()
        self.assertEqual(_schema_version(self.db_path), "6")
        self.assertIn("deadline_source", _matter_columns(self.db_path))
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT deadline_source FROM matters WHERE name = '有截止日期'"
                ).fetchone()[0],
                "document",
            )

    def test_current_schema_startup_preserves_content_without_backup(self) -> None:
        database.init_database()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO matters (name, created_at, updated_at) "
                "VALUES ('现有事项', '2026-01-01', '2026-01-01')"
            )
            conn.commit()
        with closing(sqlite3.connect(self.db_path)) as conn:
            before = conn.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
            ).fetchall()

        database.init_database()

        self.assertEqual(_schema_version(self.db_path), "6")
        self.assertEqual(self._backups(), [])
        with closing(sqlite3.connect(self.db_path)) as conn:
            after = conn.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
            ).fetchall()
            self.assertEqual(before, after)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0], 1)


def _docx_bytes(text: str) -> bytes:
    document = DocxDocument()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pdf_bytes(page_texts: list[str]) -> bytes:
    pdf = fitz.open()
    for text in page_texts:
        page = pdf.new_page()
        page.insert_text((72, 72), text)
    content = pdf.tobytes()
    pdf.close()
    return content


def _zip_bytes(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", payload)
    return buffer.getvalue()


class DocumentResourceLimitTest(unittest.TestCase):
    """P2-07：资源上限只拦截异常文档，正常 TXT/DOCX/PDF 保持可读。"""

    def test_normal_documents_remain_readable(self) -> None:
        self.assertEqual(read_txt("a.txt", "正常文本".encode()).segments[0].text, "正常文本")
        self.assertEqual(read_docx("a.docx", _docx_bytes("normal docx")).segments[0].text, "normal docx")
        self.assertEqual(read_pdf("a.pdf", _pdf_bytes(["normal pdf"])).segments[0].text, "normal pdf")

    def test_docx_uncompressed_size_limit(self) -> None:
        with mock.patch(
            "app.services.documents.docx_reader.DOCX_MAX_UNCOMPRESSED_BYTES", 10
        ):
            with self.assertRaises(DocumentError) as caught:
                read_docx("large.docx", _zip_bytes(b"x" * 11))
        self.assertEqual(caught.exception.code, "docx_uncompressed_too_large")
        self.assertEqual(caught.exception.status_code, 413)

    def test_docx_compression_ratio_limit(self) -> None:
        with mock.patch(
            "app.services.documents.docx_reader.DOCX_MAX_COMPRESSION_RATIO", 1
        ):
            with self.assertRaises(DocumentError) as caught:
                read_docx("ratio.docx", _zip_bytes(b"x" * 4096))
        self.assertEqual(caught.exception.code, "docx_compression_ratio_too_high")
        self.assertEqual(caught.exception.status_code, 413)

    def test_pdf_page_limit(self) -> None:
        with mock.patch("app.services.documents.pdf_reader.PDF_MAX_PAGES", 1):
            with self.assertRaises(DocumentError) as caught:
                read_pdf("pages.pdf", _pdf_bytes(["one", "two"]))
        self.assertEqual(caught.exception.code, "pdf_too_many_pages")
        self.assertEqual(caught.exception.status_code, 413)

    def test_extracted_text_limits(self) -> None:
        with mock.patch.object(validators, "MAX_EXTRACTED_TEXT_CHARS", 5):
            for filename, content, reader in (
                ("long.txt", b"123456", read_txt),
                ("long.docx", _docx_bytes("123456"), read_docx),
                ("long.pdf", _pdf_bytes(["123456"]), read_pdf),
            ):
                with self.subTest(filename=filename):
                    with self.assertRaises(DocumentError) as caught:
                        reader(filename, content)
                    self.assertEqual(caught.exception.code, "text_too_large")
                    self.assertEqual(caught.exception.status_code, 413)


class SafeErrorResponseTest(unittest.TestCase):
    """P2-08：响应不含底层异常，服务端日志保留定位堆栈。"""

    def test_docx_internal_error_is_safe_but_logged(self) -> None:
        secret = r"C:\private\server.db SQL SELECT secret_token"
        with mock.patch(
            "app.services.documents.docx_reader.Document",
            side_effect=RuntimeError(secret),
        ):
            with self.assertLogs("app.services.documents.docx_reader", level="ERROR") as logs:
                with self.assertRaises(DocumentError) as caught:
                    read_docx("broken.docx", _docx_bytes("content"))
        self.assertNotIn(secret, caught.exception.message)
        self.assertIn(secret, "\n".join(logs.output))

    def test_analysis_unexpected_error_response_is_sanitized(self) -> None:
        secret = r"D:\private\taskradar.db SELECT * FROM secrets"
        upload = UploadFile(file=io.BytesIO(b"safe upload"), filename="a.txt")
        with mock.patch.object(analysis, "read_document", side_effect=RuntimeError(secret)):
            with self.assertLogs("app.api.routes.analysis", level="ERROR") as logs:
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(analysis.analyze_document(upload))
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(caught.exception.detail["code"], "document_read_failed")
        self.assertNotIn(secret, str(caught.exception.detail))
        self.assertIn(secret, "\n".join(logs.output))

    def test_analysis_parser_uses_threadpool(self) -> None:
        calls = []
        original_run = analysis.run_in_threadpool

        async def spy_run(func, *args):
            calls.append(func)
            return await original_run(func, *args)

        parser = analysis.read_document
        upload = UploadFile(file=io.BytesIO(b"normal text"), filename="a.txt")
        with mock.patch.object(analysis, "run_in_threadpool", new=spy_run):
            response = asyncio.run(analysis.analyze_document(upload))
        self.assertEqual(response.document.char_count, len("normal text"))
        self.assertIn(parser, calls)

    def test_risk_database_error_response_is_sanitized(self) -> None:
        secret = r"C:\private\server.db near SELECT: syntax error"
        with mock.patch.object(
            risk_routes, "get_risk", side_effect=sqlite3.OperationalError(secret)
        ):
            with self.assertLogs("app.api.routes.risks", level="ERROR") as logs:
                with self.assertRaises(HTTPException) as caught:
                    risk_routes.query_risk(1)
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(
            caught.exception.detail,
            {"code": "database_error", "message": "读取风险详情失败，请稍后重试。"},
        )
        self.assertNotIn(secret, str(caught.exception.detail))
        self.assertIn(secret, "\n".join(logs.output))

    def test_material_database_error_response_is_sanitized(self) -> None:
        secret = r"D:\private\server.db INSERT INTO secrets VALUES (1)"
        error = sqlite3.OperationalError(secret)
        with self.assertLogs("app.api.routes.materials", level="ERROR") as logs:
            response_error = material_routes._database_error("读取材料失败", error)
        self.assertEqual(
            response_error.detail,
            {"code": "database_error", "message": "读取材料失败，请稍后重试。"},
        )
        self.assertNotIn(secret, response_error.detail["message"])
        self.assertIn(secret, "\n".join(logs.output))


class RiskNormalWorkflowTest(unittest.TestCase):
    """整体回归：风险刷新、列表、详情与事项摘要均读取真实临时数据。"""

    def test_refresh_and_read_risk_detail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="risk-flow-", dir=_TMP_ROOT) as root:
            with mock.patch.object(
                database.settings, "database_path", str(Path(root) / "copy.db")
            ):
                database.init_database()
                matter = create_matter(MatterCreate(name="风险详情回归"))
                task = create_task(
                    TaskCreate(
                        matter_id=matter.id,
                        title="已逾期任务",
                        deadline="2020-01-01",
                        deadline_source="manual",
                    )
                )
                refreshed = risk_routes.refresh_risk_alerts()
                self.assertGreaterEqual(refreshed.created, 1)
                listed = risk_routes.query_risks(
                    risk_type=None,
                    level=None,
                    status="unresolved",
                    matter_id=matter.id,
                    task_id=None,
                    material_id=None,
                    limit=100,
                    offset=0,
                )
                risk = next(item for item in listed.items if item.task_id == task.id)
                detail = risk_routes.query_risk(risk.id)
                self.assertEqual(detail.id, risk.id)
                self.assertEqual(detail.task_id, task.id)
                matter_risks = risk_routes.query_matter_risks(matter.id)
                self.assertEqual(matter_risks.summary.matter_id, matter.id)


class MaterialFileWorkflowTest(unittest.TestCase):
    """整体回归：上传、线程池解析、核验、记录与受控文件删除。"""

    def test_upload_verify_and_delete_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="material-file-", dir=_TMP_ROOT) as root:
            db_patch = mock.patch.object(
                database.settings, "database_path", str(Path(root) / "copy.db")
            )
            upload_patch = mock.patch.object(
                database.settings, "material_upload_dir", str(Path(root) / "uploads")
            )
            with db_patch, upload_patch:
                database.init_database()
                matter = create_matter(MatterCreate(name="材料文件回归"))
                material = create_material(
                    matter.id, MaterialCreate(name="报名表", description="需填写姓名")
                )
                upload = UploadFile(
                    file=io.BytesIO("报名表\n姓名：测试人员".encode()),
                    filename="报名表.txt",
                )
                uploaded = asyncio.run(
                    material_routes.upload_material_file(material["id"], upload)
                )
                self.assertEqual(uploaded["status"], "pending")
                stored_path = resolve_stored_file(uploaded["file_path"])
                self.assertIsNotNone(stored_path)
                self.assertTrue(stored_path.is_file())

                verified = asyncio.run(
                    material_routes.run_verification(material["id"])
                )
                self.assertIsNotNone(verified["verification"])
                self.assertEqual(verified["verification"].source, "rule")

                response = material_routes.remove_material(material["id"])
                self.assertEqual(response.status_code, 204)
                self.assertIsNone(get_material(material["id"]))
                self.assertFalse(stored_path.exists())


class MatterPatchSemanticsTest(unittest.TestCase):
    """P2-11：PATCH 缺省列表不清空，显式 [] 才执行主动清空。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="matter-patch-", dir=_TMP_ROOT)
        self.db_path = Path(self.temp_dir.name) / "copy.db"
        self.path_patch = mock.patch.object(
            database.settings, "database_path", str(self.db_path)
        )
        self.path_patch.start()
        database.init_database()
        evidence = {"text": "原文依据", "location": "第 1 段"}
        self.matter = create_matter(
            MatterCreate.model_validate(
                {
                    "name": "原名称",
                    "status": "pending",
                    "qualification": "原资格",
                    "materials": [{"name": "材料", "evidence": evidence}],
                    "process": [{"index": 1, "text": "流程", "evidence": evidence}],
                    "notes": [{"text": "注意", "evidence": evidence}],
                    "fields": [
                        {
                            "key": "name",
                            "label": "名称",
                            "value": "原名称",
                            "status": "found",
                            "evidence": [evidence],
                        }
                    ],
                }
            )
        )

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def _assert_lists_unchanged(self, updated) -> None:
        for field in ("materials", "process", "notes", "fields"):
            self.assertEqual(getattr(updated, field), getattr(self.matter, field))

    def test_only_name_preserves_arrays(self) -> None:
        updated = update_matter(self.matter.id, MatterUpdate(name="新名称"))
        self.assertEqual(updated.name, "新名称")
        self._assert_lists_unchanged(updated)

    def test_only_status_preserves_arrays(self) -> None:
        updated = update_matter(self.matter.id, MatterUpdate(status="done"))
        self.assertEqual(updated.status, "done")
        self._assert_lists_unchanged(updated)

    def test_omitted_materials_preserves_original_value(self) -> None:
        updated = update_matter(self.matter.id, MatterUpdate(matter_type="新类型"))
        self.assertEqual(updated.matter_type, "新类型")
        self._assert_lists_unchanged(updated)

    def test_explicit_empty_materials_clears_only_materials(self) -> None:
        updated = update_matter(self.matter.id, MatterUpdate(materials=[]))
        self.assertEqual(updated.materials, [])
        for field in ("process", "notes", "fields"):
            self.assertEqual(getattr(updated, field), getattr(self.matter, field))

    def test_multiple_fields_preserve_arrays(self) -> None:
        updated = update_matter(
            self.matter.id,
            MatterUpdate(name="多字段", status="in_progress", qualification="新资格"),
        )
        self.assertEqual(updated.name, "多字段")
        self.assertEqual(updated.status, "in_progress")
        self.assertEqual(updated.qualification, "新资格")
        self._assert_lists_unchanged(updated)

    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            MatterUpdate.model_validate({"name": "合法名称", "unknown": "拒绝"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
