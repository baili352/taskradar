"""第五阶段第二批 P2 修复的专项回归测试。

覆盖：
- P2-01 风险 GET 只读、POST 刷新与幂等、已读/已解决记录保留；
- P2-02 已完成事项不再生成积压与材料风险，重新打开后可恢复；
- P2-03 事项截止日期更新与清除、来源标记；
- P2-05 人工确认接口与前端默认值（源码核对）；
- P2-04 设置页文案核对（源码核对）；
- 任务与材料原有功能回归。

全部使用临时数据库（DATABASE_PATH 指向系统临时目录），
不读取、不写入 backend/data 下的真实数据库与上传目录。
运行方式：在 backend 目录执行
    .venv\\Scripts\\python.exe -m unittest tests.test_p2_fixes -v
"""

import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-p2-"))
# 单独运行时生效；被 discover 与其他测试模块一起加载时沿用已初始化的临时库。
os.environ.setdefault("DATABASE_PATH", str(_TMP_ROOT / "test.db"))
os.environ.setdefault("MATERIAL_UPLOAD_DIR", str(_TMP_ROOT / "uploads"))

from app.api.routes import risks as risk_routes  # noqa: E402
from app.api.routes.materials import confirm_verification  # noqa: E402
from app.db import database  # noqa: E402
from app.db.materials import (  # noqa: E402
    attach_file,
    create_material,
    get_material,
    list_materials,
    progress_for_matter,
)
from app.db.matters import create_matter, update_matter  # noqa: E402
from app.db.risks import list_risks  # noqa: E402
from app.db.tasks import create_task, list_tasks  # noqa: E402
from app.schemas.material import MaterialConfirm, MaterialCreate  # noqa: E402
from app.schemas.matter import MatterCreate, MatterUpdate  # noqa: E402
from app.schemas.task import TaskCreate, TaskUpdate  # noqa: E402
from app.services.risks.analyzer import analyze_risks  # noqa: E402
from app.services.risks.dates import today_in_timezone  # noqa: E402

TABLES = ("matters", "tasks", "materials", "material_events", "risks")


def setUpModule() -> None:
    database.init_database()
    db_path = database.get_database_path().resolve()
    if Path(tempfile.gettempdir()).resolve() not in db_path.parents:
        raise RuntimeError(f"测试数据库不在系统临时目录，已中止：{db_path}")


def tearDownModule() -> None:
    import shutil

    db_path = database.get_database_path().resolve()
    if _TMP_ROOT.resolve() in db_path.parents:
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)


def db_snapshot() -> dict[str, list[tuple]]:
    with database.get_connection() as conn:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
            for table in TABLES
        }


def make_matter(
    name: str,
    status: str = "pending",
    deadline: str | None = None,
    deadline_source: str | None = None,
):
    return create_matter(
        MatterCreate(
            name=name,
            status=status,
            deadline=deadline,
            deadline_source=deadline_source,
        )
    )


def make_task(
    matter_id: int,
    title: str,
    *,
    status: str = "pending",
    deadline: str | None = None,
    deadline_source: str | None = None,
):
    return create_task(
        TaskCreate(
            matter_id=matter_id,
            title=title,
            status=status,
            deadline=deadline,
            deadline_source=deadline_source,
        )
    )


def candidates(matter_id: int, risk_type: str | None = None) -> list[dict]:
    return [
        item
        for item in analyze_risks().candidates
        if item["matter_id"] == matter_id
        and (risk_type is None or item["risk_type"] == risk_type)
    ]


def risk_row(fingerprint: str):
    with database.get_connection() as conn:
        return conn.execute(
            "SELECT * FROM risks WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()


class RiskReadOnlyTest(unittest.TestCase):
    """P2-01：GET 只读，POST 刷新才写库；重复刷新不产生重复风险。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.matter = make_matter("P2-01 只读事项", "in_progress")
        make_task(cls.matter.id, "P2-01 未完成任务")
        create_material(cls.matter.id, MaterialCreate(name="P2-01 报名表"))
        risk_routes.refresh_risk_alerts()

    def assert_snapshot_unchanged(self, action) -> None:
        before = db_snapshot()
        action()
        after = db_snapshot()
        self.assertEqual(before, after, "GET 请求不应改变任何数据表")

    def test_risks_route_registered(self) -> None:
        from app.main import app

        routes = {
            (route.path, method)
            for route in app.routes
            for method in getattr(route, "methods", set())
        }
        self.assertIn(("/api/risks", "GET"), routes)
        self.assertIn(("/api/risks/summary", "GET"), routes)
        self.assertIn(("/api/risks/refresh", "POST"), routes)
        self.assertIn(("/api/matters/{matter_id}/risks", "GET"), routes)

    def test_get_risk_list_is_readonly(self) -> None:
        self.assert_snapshot_unchanged(
            lambda: risk_routes.query_risks(
                risk_type=None,
                level=None,
                status="unresolved",
                matter_id=None,
                task_id=None,
                material_id=None,
                limit=100,
                offset=0,
            )
        )

    def test_get_risk_summary_is_readonly(self) -> None:
        self.assert_snapshot_unchanged(risk_routes.query_risk_summary)

    def test_get_matter_risks_is_readonly(self) -> None:
        self.assert_snapshot_unchanged(
            lambda: risk_routes.query_matter_risks(self.matter.id)
        )

    def test_post_refresh_creates_and_is_idempotent(self) -> None:
        overdue = (today_in_timezone() - timedelta(days=2)).isoformat()
        task = make_task(
            self.matter.id,
            "P2-01 逾期任务",
            deadline=overdue,
            deadline_source="document",
        )
        fingerprint = f"overdue|matter:{self.matter.id}|task:{task.id}"

        first = risk_routes.refresh_risk_alerts()
        self.assertGreaterEqual(first.created, 1)
        self.assertIsNotNone(risk_row(fingerprint))

        second = risk_routes.refresh_risk_alerts()
        self.assertEqual(second.created, 0)

        with database.get_connection() as conn:
            duplicates = conn.execute(
                "SELECT COUNT(*) AS total FROM risks WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()["total"]
        self.assertEqual(duplicates, 1)

    def test_read_state_survives_refresh(self) -> None:
        _total, items = list_risks(matter_id=self.matter.id, status="unresolved")
        target = items[0]
        updated = risk_routes.mark_read(target["id"])
        self.assertEqual(updated.status, "read")

        risk_routes.refresh_risk_alerts()
        row = risk_row(target["fingerprint"])
        self.assertEqual(row["status"], "read")
        self.assertIsNotNone(row["read_at"])

    def test_resolved_history_survives_done_and_reopen(self) -> None:
        risk_routes.refresh_risk_alerts()
        fingerprint = f"material_missing|matter:{self.matter.id}|material:" + str(
            list_materials(matter_id=self.matter.id)[0]["id"]
        )
        row = risk_row(fingerprint)
        self.assertIsNotNone(row)
        first_seen = row["first_seen_at"]

        # 标记事项完成后，材料风险应被归档而不是删除。
        update_matter(self.matter.id, MatterUpdate(status="done"))
        risk_routes.refresh_risk_alerts()
        resolved = risk_row(fingerprint)
        self.assertEqual(resolved["status"], "resolved")
        self.assertIsNotNone(resolved["resolved_at"])

        # 重新打开事项后风险恢复，首次发现时间保持不变。
        update_matter(self.matter.id, MatterUpdate(status="in_progress"))
        risk_routes.refresh_risk_alerts()
        revived = risk_row(fingerprint)
        self.assertEqual(revived["status"], "active")
        self.assertEqual(revived["first_seen_at"], first_seen)


class CompletedMatterRiskTest(unittest.TestCase):
    """P2-02：已完成事项不再产生积压与材料风险。"""

    def test_done_matter_with_unfinished_tasks_has_no_backlog(self) -> None:
        matter = make_matter("P2-02 已完成多个任务", "done")
        make_task(matter.id, "任务一")
        make_task(matter.id, "任务二")
        self.assertEqual(candidates(matter.id, "backlog"), [])

    def test_done_matter_with_missing_material_has_no_material_risk(self) -> None:
        matter = make_matter("P2-02 已完成缺失材料", "done")
        create_material(matter.id, MaterialCreate(name="成绩单"))
        self.assertEqual(candidates(matter.id, "material_missing"), [])

    def test_done_matter_with_overdue_task_has_no_task_risk(self) -> None:
        matter = make_matter("P2-02 已完成逾期任务", "done")
        overdue = (today_in_timezone() - timedelta(days=3)).isoformat()
        make_task(matter.id, "逾期任务", deadline=overdue, deadline_source="document")
        self.assertEqual(candidates(matter.id), [])

    def test_pending_matter_with_unfinished_tasks_has_backlog(self) -> None:
        matter = make_matter("P2-02 未完成多个任务", "in_progress")
        make_task(matter.id, "任务一")
        make_task(matter.id, "任务二")
        self.assertEqual(len(candidates(matter.id, "backlog")), 1)

    def test_pending_matter_with_missing_material_has_material_risk(self) -> None:
        matter = make_matter("P2-02 未完成缺失材料", "pending")
        create_material(matter.id, MaterialCreate(name="学生证"))
        self.assertEqual(len(candidates(matter.id, "material_missing")), 1)

    def test_mark_done_resolves_existing_risks(self) -> None:
        matter = make_matter("P2-02 状态切换事项", "in_progress")
        make_task(matter.id, "任务一")
        make_task(matter.id, "任务二")
        material = create_material(matter.id, MaterialCreate(name="报名表"))
        risk_routes.refresh_risk_alerts()

        backlog_fp = f"backlog|matter:{matter.id}"
        material_fp = f"material_missing|matter:{matter.id}|material:{material['id']}"
        self.assertEqual(risk_row(backlog_fp)["status"], "active")
        self.assertEqual(risk_row(material_fp)["status"], "active")

        update_matter(matter.id, MatterUpdate(status="done"))
        risk_routes.refresh_risk_alerts()
        self.assertEqual(risk_row(backlog_fp)["status"], "resolved")
        self.assertEqual(risk_row(material_fp)["status"], "resolved")
        self.assertEqual(candidates(matter.id), [])

    def test_reopen_matter_recalculates_risks(self) -> None:
        matter = make_matter("P2-02 重新打开事项", "done")
        make_task(matter.id, "任务一")
        make_task(matter.id, "任务二")
        risk_routes.refresh_risk_alerts()
        self.assertEqual(candidates(matter.id, "backlog"), [])

        update_matter(matter.id, MatterUpdate(status="in_progress"))
        risk_routes.refresh_risk_alerts()
        backlog_fp = f"backlog|matter:{matter.id}"
        self.assertEqual(len(candidates(matter.id, "backlog")), 1)
        self.assertEqual(risk_row(backlog_fp)["status"], "active")

        # 其他未完成事项的风险不受影响。
        other = make_matter("P2-02 其他未完成事项", "in_progress")
        make_task(other.id, "任务甲")
        make_task(other.id, "任务乙")
        risk_routes.refresh_risk_alerts()
        self.assertEqual(len(candidates(other.id, "backlog")), 1)
        self.assertEqual(risk_row(backlog_fp)["status"], "active")


class MatterDeadlineUpdateTest(unittest.TestCase):
    """P2-03：截止日期修改、清除、来源标记与证据保留。"""

    def test_update_deadline_marks_manual(self) -> None:
        matter = make_matter("P2-03 修改截止日期")
        updated = update_matter(
            matter.id, MatterUpdate(deadline="2026-12-01", deadline_source="manual")
        )
        self.assertEqual(updated.deadline, "2026-12-01")
        self.assertEqual(updated.deadline_source, "manual")

    def test_update_deadline_without_source_defaults_to_manual(self) -> None:
        matter = make_matter("P2-03 默认来源")
        updated = update_matter(matter.id, MatterUpdate(deadline="2026年12月5日"))
        self.assertEqual(updated.deadline, "2026年12月5日")
        self.assertEqual(updated.deadline_source, "manual")

    def test_clear_deadline_resets_source(self) -> None:
        matter = make_matter("P2-03 清除截止日期", deadline="2026-12-01")
        updated = update_matter(matter.id, MatterUpdate(deadline=None))
        self.assertIsNone(updated.deadline)
        self.assertEqual(updated.deadline_source, "none")

    def test_suggested_deadline_stays_unconfirmed(self) -> None:
        matter = make_matter("P2-03 建议日期")
        updated = update_matter(
            matter.id, MatterUpdate(deadline="2026-12-10", deadline_source="suggested")
        )
        self.assertEqual(updated.deadline_source, "suggested")
        from app.services.risks.dates import participates

        self.assertFalse(participates(updated.deadline_source, updated.deadline))

    def test_deadline_update_keeps_original_evidence(self) -> None:
        matter = create_matter(
            MatterCreate(
                name="P2-03 证据保留",
                materials=[
                    {
                        "name": "报名表",
                        "evidence": {
                            "text": "请提交报名表",
                            "location": "第 2 段",
                            "paragraph": 2,
                        },
                    }
                ],
                process=[
                    {
                        "index": 1,
                        "text": "填写报名表",
                        "evidence": {
                            "text": "填写报名表",
                            "location": "第 3 段",
                            "paragraph": 3,
                        },
                    }
                ],
            )
        )
        updated = update_matter(matter.id, MatterUpdate(deadline="2026-12-20"))
        self.assertEqual(len(updated.materials), 1)
        self.assertEqual(updated.materials[0].evidence.text, "请提交报名表")
        self.assertEqual(len(updated.process), 1)
        self.assertEqual(updated.process[0].evidence.location, "第 3 段")


class VerificationConfirmTest(unittest.TestCase):
    """P2-05：人工确认必须显式给出结论并记录备注。"""

    def test_manual_confirm_records_result_note_and_event(self) -> None:
        matter = make_matter("P2-05 人工确认事项")
        material = create_material(matter.id, MaterialCreate(name="身份证复印件"))
        attach_file(material["id"], "uploads/test.pdf", "test.pdf", 1024, ".pdf")

        confirmed = confirm_verification(
            material["id"],
            MaterialConfirm(status="qualified", note="已核对原件，姓名一致。"),
        )
        self.assertEqual(confirmed["status"], "qualified")
        verification = confirmed["verification"]
        self.assertIsNotNone(verification)
        self.assertEqual(verification.source, "manual")
        self.assertEqual(verification.result, "qualified")
        self.assertEqual(verification.reviewer_note, "已核对原件，姓名一致。")
        detail = get_material(material["id"], with_events=True)
        actions = [event.action for event in detail["events"]]
        self.assertIn("confirmed", actions)

    def test_frontend_default_is_not_qualified(self) -> None:
        source = (PROJECT / "frontend/src/pages/VerificationPage.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("useState<MaterialVerificationResult | ''>('')", source)
        self.assertIn("setConfirmStatus('')", source)
        self.assertIn("请选择核验结果（必选）", source)
        self.assertIn("disabled={confirming || !confirmStatus}", source)
        self.assertIn("请填写确认说明", source)
        self.assertIn("不代表材料真实性的证明", source)


class SettingsCopyTest(unittest.TestCase):
    """P2-04：设置页不得再出现与真实系统不符的描述。"""

    def test_settings_copy_matches_local_sqlite(self) -> None:
        source = (PROJECT / "frontend/src/pages/SettingsPage.tsx").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "界面演示",
            "示例数据直接写在页面代码中",
            "不会写入数据库",
            "当前没有真实业务数据",
            "重置演示数据",
            "恢复示例数据",
            "不会上传到服务器",
        ):
            self.assertNotIn(forbidden, source)

        for required in (
            "backend/data/taskradar.db",
            "backend/data/uploads/materials",
            "没有云端同步",
            "不提供自动备份",
            "不调用大模型",
            "不代表对材料真实性的证明",
        ):
            self.assertIn(required, source)


class TaskMaterialRegressionTest(unittest.TestCase):
    """任务与材料原有功能回归。"""

    def test_task_lifecycle(self) -> None:
        matter = make_matter("回归任务事项")
        task = make_task(
            matter.id,
            "回归任务",
            deadline="2026-12-01",
            deadline_source="manual",
        )
        self.assertEqual(task.deadline_source, "manual")

        updated = update_task_status(task.id, "done")
        self.assertEqual(updated.status, "done")
        self.assertIn(task.id, [item.id for item in list_tasks(matter_id=matter.id)])

    def test_material_lifecycle_and_progress(self) -> None:
        matter = make_matter("回归材料事项")
        material = create_material(matter.id, MaterialCreate(name="报名表"))
        self.assertEqual(material["status"], "missing")

        pending = attach_file(material["id"], "uploads/a.pdf", "a.pdf", 2048, ".pdf")
        self.assertEqual(pending["status"], "pending")

        progress = progress_for_matter(matter.id)
        self.assertEqual(progress["total"], 1)
        self.assertEqual(progress["provided"], 1)
        self.assertEqual(progress["pending"], 1)

        confirmed = confirm_verification(
            material["id"], MaterialConfirm(status="qualified", note="人工核对通过。")
        )
        self.assertEqual(confirmed["status"], "qualified")
        progress_after = progress_for_matter(matter.id)
        self.assertEqual(progress_after["qualified"], 1)


def update_task_status(task_id: int, status: str):
    from app.db.tasks import update_task

    return update_task(task_id, TaskUpdate(status=status))


if __name__ == "__main__":
    unittest.main(verbosity=2)
