"""第五阶段第一批 P1 修复的专项回归测试。

全部使用临时数据库（DATABASE_PATH 指向系统临时目录），
不读取、不写入 backend/data 下的真实数据库与上传目录。
运行方式：在 backend 目录执行
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-p1-"))
os.environ["DATABASE_PATH"] = str(_TMP_ROOT / "test.db")
os.environ["MATERIAL_UPLOAD_DIR"] = str(_TMP_ROOT / "uploads")

from app.db import database  # noqa: E402
from app.db.matters import create_matter  # noqa: E402
from app.db.tasks import create_task, update_task  # noqa: E402
from app.schemas.matter import MatterCreate  # noqa: E402
from app.schemas.task import TaskCreate, TaskUpdate  # noqa: E402
from app.services.documents.types import ExtractedDocument, Segment  # noqa: E402
from app.services.extraction.extractor import extract_document  # noqa: E402
from app.services.risks.analyzer import analyze_risks  # noqa: E402
from app.services.risks.dates import (  # noqa: E402
    parse_deadline,
    participates,
    today_in_timezone,
)

_TEST_MATTER = None


def setUpModule() -> None:
    database.init_database()
    db_path = database.get_database_path()
    if not str(db_path).startswith(str(_TMP_ROOT)):
        raise RuntimeError(f"测试数据库不在临时目录，已中止：{db_path}")
    global _TEST_MATTER
    _TEST_MATTER = create_matter(MatterCreate(name="P1 专项测试事项"))


def tearDownModule() -> None:
    import shutil

    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


def make_document(*texts: str) -> ExtractedDocument:
    return ExtractedDocument(
        filename="sample.txt",
        extension=".txt",
        size=1,
        segments=[
            Segment(text=text, location=f"第 {index + 1} 段", paragraph=index + 1)
            for index, text in enumerate(texts)
        ],
    )


def deadline_field(*texts: str):
    result = extract_document(make_document(*texts))
    return next(field for field in result["fields"] if field["key"] == "deadline")


def material_names(*texts: str) -> list[str]:
    result = extract_document(make_document(*texts))
    return [item["name"] for item in result["materials"]]


def risks_by_task() -> dict[int, set[str]]:
    mapping: dict[int, set[str]] = {}
    for candidate in analyze_risks().candidates:
        task_id = candidate["task_id"]
        if task_id is not None:
            mapping.setdefault(task_id, set()).add(candidate["risk_type"])
    return mapping


def new_task(**overrides):
    payload = {
        "matter_id": _TEST_MATTER.id,
        "title": "P1 测试任务",
        "description": "",
        "deadline": None,
        "priority": "medium",
        "status": "pending",
    }
    payload.update(overrides)
    return create_task(TaskCreate(**payload))


class DeadlineSourceTest(unittest.TestCase):
    """P1-01：截止日期来源必须与风险判断规则一致。"""

    def test_document_participates(self):
        self.assertTrue(participates("document", "2026-01-01"))

    def test_manual_participates(self):
        self.assertTrue(participates("manual", "2026-01-01"))

    def test_suggested_not_participates(self):
        self.assertFalse(participates("suggested", "2026-01-01"))

    def test_none_and_blank_not_participates(self):
        self.assertFalse(participates("none", "2026-01-01"))
        self.assertFalse(participates("manual", None))
        self.assertFalse(participates("manual", ""))

    def test_document_overdue_risk_created(self):
        past = (today_in_timezone() - timedelta(days=2)).isoformat()
        task = new_task(title="原文日期逾期", deadline=past, deadline_source="document")
        self.assertIn("overdue", risks_by_task().get(task.id, set()))

    def test_manual_overdue_risk_created(self):
        past = (today_in_timezone() - timedelta(days=2)).isoformat()
        task = new_task(title="手动日期逾期", deadline=past, deadline_source="manual")
        self.assertIn("overdue", risks_by_task().get(task.id, set()))

    def test_manual_due_soon_risk_created(self):
        soon = (today_in_timezone() + timedelta(days=2)).isoformat()
        task = new_task(title="手动日期即将截止", deadline=soon, deadline_source="manual")
        self.assertIn("due_soon", risks_by_task().get(task.id, set()))

    def test_create_with_suggested_source_does_not_participate(self):
        past = (today_in_timezone() - timedelta(days=2)).isoformat()
        task = new_task(title="创建时标记为建议", deadline=past, deadline_source="suggested")
        self.assertEqual(task.deadline_source, "suggested")
        self.assertNotIn(task.id, risks_by_task())

    def test_legacy_suggested_does_not_create_risk(self):
        past = (today_in_timezone() - timedelta(days=2)).isoformat()
        task = new_task(title="历史建议日期", deadline=past, deadline_source="manual")
        updated = update_task(task.id, TaskUpdate(deadline_source="suggested"))
        self.assertEqual(updated.deadline_source, "suggested")
        self.assertNotIn(task.id, risks_by_task())

    def test_legacy_suggested_due_soon_does_not_create_risk(self):
        soon = (today_in_timezone() + timedelta(days=2)).isoformat()
        task = new_task(title="历史建议临近日期", deadline=soon, deadline_source="manual")
        update_task(task.id, TaskUpdate(deadline_source="suggested"))
        self.assertNotIn(task.id, risks_by_task())

    def test_apply_suggestion_becomes_manual_and_participates(self):
        past = (today_in_timezone() - timedelta(days=1)).isoformat()
        task = new_task(title="待应用建议任务")
        applied = update_task(
            task.id,
            TaskUpdate(deadline=past, deadline_source="suggested"),
        )
        self.assertEqual(applied.deadline_source, "manual")
        self.assertEqual(applied.deadline, past)
        self.assertIn("overdue", risks_by_task().get(task.id, set()))

    def test_apply_suggestion_due_soon_is_high(self):
        soon = (today_in_timezone() + timedelta(days=2)).isoformat()
        task = new_task(title="应用建议后即将截止")
        update_task(task.id, TaskUpdate(deadline=soon, deadline_source="suggested"))
        candidates = [
            item
            for item in analyze_risks().candidates
            if item["task_id"] == task.id and item["risk_type"] == "due_soon"
        ]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["risk_level"], "high")

    def test_unapplied_suggestion_has_no_risk(self):
        task = new_task(title="未应用建议任务")
        self.assertNotIn(task.id, risks_by_task())

    def test_clearing_deadline_resets_source(self):
        past = (today_in_timezone() - timedelta(days=2)).isoformat()
        task = new_task(title="待清空日期", deadline=past, deadline_source="manual")
        cleared = update_task(task.id, TaskUpdate(deadline=None))
        self.assertEqual(cleared.deadline_source, "none")
        self.assertNotIn(task.id, risks_by_task())


class CrossYearInferenceTest(unittest.TestCase):
    """P1-02：跨段年份推断回归。"""

    def test_december_to_january(self):
        field = deadline_field("2025年12月20日发布通知", "报名截止：1月5日。")
        self.assertEqual(field["value"], "2026年1月5日")
        self.assertEqual(parse_deadline(field["value"]).status, "ok")

    def test_november_to_february(self):
        field = deadline_field("2025年11月20日发布通知", "报名截止：2月5日。")
        self.assertEqual(field["value"], "2026年2月5日")

    def test_same_year_within_year(self):
        field = deadline_field("2025年3月20日发布通知", "报名截止：4月5日。")
        self.assertEqual(field["value"], "2025年4月5日")

    def test_conflicting_years_stay_unverified(self):
        field = deadline_field(
            "2024年3月1日发布通知",
            "2025年12月20日再次发布",
            "报名截止：1月5日。",
        )
        self.assertEqual(field["value"], "1月5日")
        self.assertEqual(parse_deadline(field["value"]).status, "unverified")

    def test_complete_date_is_unchanged(self):
        field = deadline_field("报名截止：2026年11月20日。")
        self.assertEqual(field["value"], "2026年11月20日")

    def test_no_year_context_stays_unverified(self):
        field = deadline_field("报名截止：1月5日。")
        self.assertEqual(field["value"], "1月5日")
        self.assertEqual(parse_deadline(field["value"]).status, "unverified")

    def test_cross_year_range_resolves_both_ends(self):
        field = deadline_field("2025年11月20日发布通知", "报名时间：11月25日至2月5日。")
        self.assertEqual(field["value"], "2026年2月5日")

    def test_cross_year_keeps_evidence_segment(self):
        field = deadline_field("2025年12月20日发布通知", "报名截止：1月5日。")
        self.assertTrue(field["note"])
        self.assertIn("第 1 段", field["note"])
        self.assertEqual(len(field["evidence"]), 1)
        self.assertEqual(field["evidence"][0]["location"], "第 2 段")


class MaterialNameTest(unittest.TestCase):
    """P1-03：材料名称误判与正常材料保留。"""

    def test_title_is_not_material(self):
        names = material_names("关于提交材料的通知")
        self.assertNotIn("关于", names)
        self.assertEqual(names, [])

    def test_submit_student_materials_title_is_not_material(self):
        names = material_names("关于报送学生材料的通知")
        self.assertNotIn("关于", names)
        self.assertNotIn("学生材料", names)
        self.assertEqual(names, [])

    def test_application_form_is_recognized(self):
        self.assertIn("报名表", material_names("请填写报名表并提交"))

    def test_id_copy_is_recognized(self):
        self.assertIn("身份证复印件", material_names("需提交身份证复印件"))

    def test_project_proposal_is_recognized(self):
        self.assertIn("项目申报书", material_names("请提交项目申报书"))

    def test_generic_materials_are_not_fabricated(self):
        self.assertEqual(material_names("请准备相关材料"), [])

    def test_normal_materials_are_preserved(self):
        self.assertIn("学生证扫描件", material_names("请提交学生证扫描件"))
        self.assertIn("成绩单", material_names("请提供成绩单"))
        self.assertIn("个人简历", material_names("请附上个人简历"))

    def test_material_evidence_is_preserved(self):
        result = extract_document(make_document("需提交身份证复印件"))
        material = next(item for item in result["materials"] if item["name"] == "身份证复印件")
        self.assertEqual(material["evidence"]["location"], "第 1 段")
        self.assertIn("身份证复印件", material["evidence"]["text"])


class ExistingFeatureRegressionTest(unittest.TestCase):
    """原有功能回归：事项、任务生成、材料生成、风险刷新、文档解析。"""

    def _make_matter(self) -> "object":
        from app.db.matters import create_matter as create
        from app.schemas.matter import (
            MatterEvidence,
            MatterField,
            MatterMaterial,
            MatterProcessStep,
        )

        evidence = MatterEvidence(text="请提交报名表和身份证复印件。", location="第 1 段")
        return create(
            MatterCreate(
                name="回归测试事项",
                matter_type="申报",
                deadline="2026年12月31日",
                materials=[
                    MatterMaterial(name="报名表", evidence=evidence),
                    MatterMaterial(name="身份证复印件", evidence=evidence),
                ],
                process=[
                    MatterProcessStep(index=1, text="第一步：填写报名表。", evidence=evidence),
                    MatterProcessStep(index=2, text="第二步：提交身份证复印件。", evidence=evidence),
                ],
                fields=[
                    MatterField(
                        key="deadline",
                        label="截止日期",
                        value="2026年12月31日",
                        status="found",
                        evidence=[evidence],
                    )
                ],
            )
        )

    def test_matter_create_and_read_round_trip(self):
        from app.db.matters import get_matter

        matter = self._make_matter()
        loaded = get_matter(matter.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "回归测试事项")
        self.assertEqual(len(loaded.materials), 2)
        self.assertEqual(len(loaded.process), 2)
        self.assertEqual(loaded.fields[0].value, "2026年12月31日")

    def test_task_generation_and_dedup(self):
        from app.api.routes.tasks import generate_tasks

        matter = self._make_matter()
        first = generate_tasks(matter.id)
        second = generate_tasks(matter.id)
        self.assertEqual(first.created, 2)
        self.assertEqual(second.created, 0)

    def test_material_generation_and_dedup(self):
        from app.api.routes.materials import generate_materials

        matter = self._make_matter()
        first = generate_materials(matter.id)
        second = generate_materials(matter.id)
        self.assertEqual(first.created, 2)
        self.assertEqual(second.created, 0)

    def test_risk_refresh_runs_on_temp_db(self):
        from app.services.risks.service import refresh_risks

        sync_result, summary, outcome = refresh_risks()
        self.assertIsInstance(sync_result, dict)
        self.assertGreaterEqual(summary.total_risks, 0)
        self.assertIsInstance(outcome.candidates, list)

    def test_txt_utf8_and_gb18030(self):
        from app.services.documents.reader import read_document

        max_bytes = 10 * 1024 * 1024
        utf8 = read_document("a.txt", "请提交报名表".encode("utf-8"), max_bytes)
        gb = read_document("b.txt", "请提交报名表".encode("gb18030"), max_bytes)
        self.assertIn("报名表", utf8.segments[0].text)
        self.assertIn("报名表", gb.segments[0].text)

    def test_docx_parsing(self):
        import io

        from docx import Document as DocxDocument

        from app.services.documents.reader import read_document

        buffer = io.BytesIO()
        document = DocxDocument()
        document.add_paragraph("请提交项目申报书")
        document.save(buffer)
        parsed = read_document("c.docx", buffer.getvalue(), 10 * 1024 * 1024)
        self.assertTrue(any("项目申报书" in segment.text for segment in parsed.segments))

    def test_pdf_parsing(self):
        import fitz

        from app.services.documents.reader import read_document

        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Submit the application form")
        parsed = read_document("d.pdf", pdf.tobytes(), 10 * 1024 * 1024)
        joined = "".join(segment.text for segment in parsed.segments)
        self.assertIn("application", joined)

    def test_corrupted_and_empty_documents_are_rejected(self):
        from app.services.documents.errors import DocumentError
        from app.services.documents.reader import read_document

        max_bytes = 10 * 1024 * 1024
        with self.assertRaises(DocumentError):
            read_document("bad.pdf", b"not a pdf", max_bytes)
        with self.assertRaises(DocumentError):
            read_document("empty.txt", b"", max_bytes)
        with self.assertRaises(DocumentError):
            read_document("shell.exe", b"MZ", max_bytes)

    def test_oversized_document_is_rejected(self):
        from app.services.documents.errors import DocumentError
        from app.services.documents.reader import read_document

        with self.assertRaises(DocumentError):
            read_document("big.txt", b"a" * 2048, 1024)


class HandoverStepAndDeadlineConflictTest(unittest.TestCase):
    """E2E 缺陷回归：交至类步骤漏识别、多截止日期未提示冲突。"""

    def test_handover_step_ending_with_office_is_kept(self):
        result = extract_document(
            make_document(
                "关于举办2026年大学生竞赛的通知",
                "一、报名时间",
                "2026年3月1日至2026年3月31日",
                "二、报名方式",
                "1. 登录竞赛平台填写报名表。",
                "2. 提交项目申报书和推荐表。",
                "3. 将纸质材料交至教务处创新创业办公室。",
            )
        )
        self.assertEqual(
            [step["text"] for step in result["process"]],
            [
                "登录竞赛平台填写报名表",
                "提交项目申报书和推荐表",
                "将纸质材料交至教务处创新创业办公室",
            ],
        )

    def test_submit_to_office_step_is_kept(self):
        result = extract_document(
            make_document(
                "一、申报时间",
                "2026年5月6日至2026年5月26日",
                "二、申报流程",
                "1. 下载并填写项目申请书。",
                "2. 将材料提交至学院科研办公室。",
            )
        )
        self.assertIn("将材料提交至学院科研办公室", [step["text"] for step in result["process"]])

    def test_pure_organization_line_is_still_signature(self):
        from app.services.extraction.sections import detect_metadata_line

        self.assertEqual(detect_metadata_line("教务处办公室"), "signature")

    def test_multiple_deadlines_are_reported(self):
        result = extract_document(
            make_document(
                "一、报名时间",
                "2026年5月1日至2026年5月10日",
                "二、报名方式",
                "1. 填写优秀学生申请表。",
                "三、注意事项",
                "截止时间：2026年6月20日，逾期不予受理。",
            )
        )
        deadline = next(field for field in result["fields"] if field["key"] == "deadline")
        self.assertEqual(deadline["value"], "2026年5月10日")
        self.assertIn("2026年5月10日", deadline["note"])
        self.assertIn("2026年6月20日", deadline["note"])
        self.assertIn("请核实", deadline["note"])

    def test_title_material_is_not_extracted(self):
        result = extract_document(
            make_document(
                "关于提交2026年国家奖学金材料的通知",
                "全体本科生：",
                "一、提交材料",
                "《国家奖学金申请表》、成绩单、获奖证书复印件。",
                "二、注意事项",
                "标题中的“材料”不是材料名称，请按材料清单逐项准备。",
            )
        )
        self.assertEqual(
            [material["name"] for material in result["materials"]],
            ["国家奖学金申请表", "成绩单", "获奖证书复印件"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
