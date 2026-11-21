"""参赛演示数据的初始化与清理。

约束：
- 演示事项统一写入 matters.is_demo = 1，正式数据 is_demo = 0，二者互不影响；
- 演示材料文件写入上传目录下的独立 demo/ 子目录，清理时整体删除；
- 风险只针对演示事项生成并直接写入，不触发正式数据的风险同步；
- 不生成任何用户数量、节省时间、准确率等虚构指标。
"""

import json
import logging
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.db.database import get_connection
from app.schemas.dashboard import DemoStatus
from app.services.materials.storage import get_upload_root, sanitize_filename
from app.services.risks.analyzer import analyze_risks
from app.services.risks.dates import now_in_timezone, today_in_timezone

logger = logging.getLogger(__name__)

DEMO_DIR_NAME = "demo"


def _iso(days: int) -> str:
    return (today_in_timezone() + timedelta(days=days)).isoformat()


def _now() -> str:
    return now_in_timezone().isoformat(timespec="milliseconds")


def _evidence(text: str, location: str) -> dict:
    return {"text": text, "location": location}


def _material(name: str, description: str, evidence: dict) -> dict:
    return {"name": name, "status": "found", "evidence": evidence}


def _process(index: int, text: str, evidence: dict) -> dict:
    return {"index": index, "text": text, "evidence": evidence}


def _note(text: str, evidence: dict) -> dict:
    return {"text": text, "evidence": evidence}


def _field(
    key: str,
    label: str,
    value: str | None,
    status: str,
    evidence: list[dict] | None = None,
    note: str | None = None,
) -> dict:
    return {
        "key": key,
        "label": label,
        "value": value,
        "status": status,
        "evidence": evidence or [],
        "note": note,
    }


def _build_matters() -> list[dict[str, Any]]:
    """三份演示通知及其结构化的提取结果。日期相对今天生成，保证演示可复现。"""
    activity_deadline = _iso(12)
    contest_deadline = _iso(-2)
    recruit_deadline = _iso(21)

    activity = {
        "name": "【演示】校园开放日志愿服务活动",
        "matter_type": "活动通知",
        "qualification": "面向全校在读学生，需完成志愿服务岗前培训",
        "registration_start": _iso(1),
        "deadline": activity_deadline,
        "deadline_source": "document",
        "source_filename": "演示_活动通知.txt",
        "status": "in_progress",
        "materials": [
            _material("志愿者报名表", "需本人签字", _evidence("填写《志愿者报名表》并交至校团委办公室。", "活动通知 第3段")),
            _material("志愿服务承诺书", "需本人签字", _evidence("提交《志愿服务承诺书》一份。", "活动通知 第3段")),
            _material("培训签到表", "岗前培训现场签到", _evidence("培训当天完成签到，签到表由工作人员统一收取。", "活动通知 第4段")),
            _material("活动安全预案", "由活动负责人提交", _evidence("活动负责人需提交安全预案。", "活动通知 第5段")),
        ],
        "process": [
            _process(1, "在线填写并提交志愿者报名表", _evidence("第一步：填写《志愿者报名表》。", "活动通知 第3段")),
            _process(2, "参加岗前培训并完成签到", _evidence("第二步：参加岗前培训。", "活动通知 第4段")),
            _process(3, "领取志愿者证与物资", _evidence("第三步：领取志愿者证与活动物资。", "活动通知 第4段")),
            _process(4, "活动当天按时到岗", _evidence("请于活动当天 8:30 前到岗。", "活动通知 第2段")),
        ],
        "notes": [
            _note("活动当天需统一着装。", _evidence("活动当天请统一穿着志愿者马甲。", "活动通知 第6段")),
            _note("无故缺席将取消后续志愿服务资格。", _evidence("无故缺席者取消本学期志愿服务资格。", "活动通知 第7段")),
        ],
        "fields": [
            _field("activity_name", "活动名称", "校园开放日志愿服务活动", "found", [_evidence("校园开放日志愿服务活动通知", "标题")]),
            _field("organizer", "主办单位", "校团委", "found", [_evidence("主办单位：校团委", "活动通知 第1段")]),
            _field("deadline", "报名截止时间", activity_deadline, "found", [_evidence(f"报名截止时间为 {activity_deadline}。", "活动通知 第2段")]),
            _field("location", "活动地点", "学校中心广场", "found", [_evidence("活动地点：学校中心广场。", "活动通知 第2段")]),
            _field("quota", "招募人数", None, "pending", [], "原文只写了“若干名”，未给出明确人数，需要人工核实。"),
            _field("contact", "联系方式", "校团委办公室 王老师", "found", [_evidence("联系人：校团委办公室 王老师。", "活动通知 第8段")]),
        ],
    }

    contest = {
        "name": "【演示】大学生创新创业竞赛",
        "matter_type": "竞赛通知",
        "qualification": "全日制在校本科生，3—5 人组队参赛",
        "registration_start": _iso(-20),
        "deadline": contest_deadline,
        "deadline_source": "document",
        "source_filename": "演示_竞赛通知.txt",
        "status": "pending",
        "materials": [
            _material("参赛报名表", "需全部成员签字", _evidence("提交《参赛报名表》，全体成员签字。", "竞赛通知 第4段")),
            _material("项目作品说明书", "不超过 20 页", _evidence("提交项目作品说明书，篇幅不超过 20 页。", "竞赛通知 第5段")),
            _material("指导教师推荐信", "需教师签字", _evidence("提交指导教师推荐信。", "竞赛通知 第6段")),
        ],
        "process": [
            _process(1, "完成组队并确认成员信息", _evidence("第一步：完成组队。", "竞赛通知 第3段")),
            _process(2, "提交作品终稿", _evidence("第二步：提交作品终稿。", "竞赛通知 第4段")),
            _process(3, "完成报名缴费", _evidence("第三步：缴纳报名费。", "竞赛通知 第5段")),
            _process(4, "参加现场答辩", _evidence("第四步：参加现场答辩。", "竞赛通知 第7段")),
        ],
        "notes": [
            _note("作品须为原创，不得抄袭。", _evidence("作品须为原创作品。", "竞赛通知 第8段")),
        ],
        "fields": [
            _field("contest_name", "竞赛名称", "大学生创新创业竞赛", "found", [_evidence("大学生创新创业竞赛通知", "标题")]),
            _field("deadline", "作品提交截止", contest_deadline, "found", [_evidence(f"作品提交截止时间为 {contest_deadline}。", "竞赛通知 第4段")]),
            _field("team_size", "团队人数", "3—5 人", "found", [_evidence("每队 3—5 人。", "竞赛通知 第3段")]),
            _field("fee", "报名费", None, "pending", [], "原文未写明报名费金额，需要向组织方确认。"),
            _field("defense_date", "答辩时间", "11 月下旬", "pending", [_evidence("答辩安排在 11 月下旬。", "竞赛通知 第7段")], "原文未给出具体日期，需要人工核实。"),
        ],
    }

    recruit = {
        "name": "【演示】区属事业单位公开招聘",
        "matter_type": "招聘通知",
        "qualification": "本科及以上学历，专业不限，年龄 35 周岁以下",
        "registration_start": _iso(0),
        "deadline": recruit_deadline,
        "deadline_source": "document",
        "source_filename": "演示_招聘通知.txt",
        "status": "pending",
        "materials": [
            _material("个人简历", "需附近期照片", _evidence("提交个人简历一份，附一寸照片。", "招聘通知 第3段")),
            _material("学历学位证书", "需扫描件", _evidence("提供学历、学位证书扫描件。", "招聘通知 第3段")),
            _material("身份证复印件", "正反面复印", _evidence("提供身份证正反面复印件。", "招聘通知 第3段")),
        ],
        "process": [
            _process(1, "在线注册并填报个人信息", _evidence("第一步：登录报名系统填报信息。", "招聘通知 第2段")),
            _process(2, "上传报名材料", _evidence("第二步：上传报名材料。", "招聘通知 第3段")),
            _process(3, "查询资格初审结果", _evidence("第三步：查询资格初审结果。", "招聘通知 第4段")),
            _process(4, "参加笔试与面试", _evidence("第四步：参加笔试和面试。", "招聘通知 第5段")),
        ],
        "notes": [
            _note("每人限报一个岗位。", _evidence("每名考生限报一个岗位。", "招聘通知 第6段")),
        ],
        "fields": [
            _field("employer", "招聘单位", "区属事业单位", "found", [_evidence("区属事业单位公开招聘公告", "标题")]),
            _field("deadline", "报名截止时间", recruit_deadline, "found", [_evidence(f"报名截止时间为 {recruit_deadline}。", "招聘通知 第2段")]),
            _field("headcount", "招聘人数", None, "pending", [], "原文未给出各岗位招聘人数，需要查看岗位表。"),
            _field("written_exam", "笔试时间", None, "pending", [], "原文仅说明“另行通知”，无法判断具体时间。"),
            _field("contact", "咨询电话", "区人社局 考务科", "found", [_evidence("咨询电话：区人社局考务科。", "招聘通知 第8段")]),
        ],
    }

    return [activity, contest, recruit]


def _matter_insert_sql() -> str:
    return (
        "INSERT INTO matters (name, matter_type, qualification, registration_start, "
        "deadline, deadline_source, materials_json, process_json, notes_json, "
        "fields_json, source_filename, status, analysis_mode, is_demo, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rule_based', 1, ?, ?)"
    )


def _demo_folder() -> Path:
    return get_upload_root() / DEMO_DIR_NAME


def _write_demo_file(name: str, content: str) -> tuple[str, int]:
    folder = _demo_folder()
    folder.mkdir(parents=True, exist_ok=True)
    # 统一清理文件名，确保写入位置始终位于 demo/ 目录内，避免路径穿越。
    path = folder / sanitize_filename(name)
    data = content.encode("utf-8")
    path.write_bytes(data)
    return f"{DEMO_DIR_NAME}/{path.name}", len(data)


def _task(title: str, days: int | None, priority: str, status: str) -> dict:
    return {"title": title, "days": days, "priority": priority, "status": status}


def _task_deadline(days: int | None) -> str | None:
    return _iso(days) if days is not None else None


def _material_row(name: str, description: str, status: str, file_text: str | None) -> dict:
    return {
        "name": name,
        "description": description,
        "status": status,
        "file_text": file_text,
    }


def _insert_matter(conn, matter: dict, now: str) -> int:
    cursor = conn.execute(
        _matter_insert_sql(),
        (
            matter["name"],
            matter["matter_type"],
            matter["qualification"],
            matter["registration_start"],
            matter["deadline"],
            matter["deadline_source"],
            json.dumps(matter["materials"], ensure_ascii=False),
            json.dumps(matter["process"], ensure_ascii=False),
            json.dumps(matter["notes"], ensure_ascii=False),
            json.dumps(matter["fields"], ensure_ascii=False),
            matter["source_filename"],
            matter["status"],
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _insert_task(
    conn,
    matter_id: int,
    task: dict,
    now: str | None = None,
    evidence: dict | None = None,
) -> int:
    now = now or _now()
    deadline = _task_deadline(task["days"])
    cursor = conn.execute(
        "INSERT INTO tasks (matter_id, title, description, deadline, deadline_source, "
        "priority, status, source_evidence_json, step_key, origin, created_at, updated_at) "
        "VALUES (?, ?, '', ?, ?, ?, ?, ?, NULL, 'generated', ?, ?)",
        (
            matter_id,
            task["title"],
            deadline,
            "document" if deadline else "none",
            task["priority"],
            task["status"],
            json.dumps(evidence, ensure_ascii=False) if evidence else None,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _insert_material(
    conn, matter_id: int, row: dict, now: str
) -> int:
    file_path = None
    size = None
    if row["file_text"] is not None:
        file_path, size = _write_demo_file(
            f"matter-{matter_id}-{row['name']}.txt", row["file_text"]
        )
    cursor = conn.execute(
        "INSERT INTO materials (matter_id, name, description, status, file_path, "
        "original_filename, file_size, file_type, origin, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'generated', ?, ?)",
        (
            matter_id,
            row["name"],
            row["description"],
            row["status"],
            file_path,
            f"{row['name']}.txt" if file_path else None,
            size,
            "TXT" if file_path else None,
            now,
            now,
        ),
    )
    material_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT INTO material_events (material_id, action, detail, created_at) "
        "VALUES (?, 'generated', '演示数据：由事项材料要求生成', ?)",
        (material_id, now),
    )
    return material_id


def _seed_risk_rows(conn, demo_matter_ids: set[int]) -> int:
    """只为演示事项写入风险，不触碰正式数据的风险记录。"""
    outcome = analyze_risks()
    now = _now()
    inserted = 0
    for candidate in outcome.candidates:
        if candidate["matter_id"] not in demo_matter_ids:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO risks (fingerprint, risk_type, risk_level, title, "
            "description, matter_id, task_id, material_id, evidence_json, suggestion, "
            "status, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                candidate["fingerprint"],
                candidate["risk_type"],
                candidate["risk_level"],
                candidate["title"],
                candidate.get("description", ""),
                candidate["matter_id"],
                candidate.get("task_id"),
                candidate.get("material_id"),
                json.dumps(candidate["evidence"], ensure_ascii=False),
                candidate.get("suggestion", ""),
                now,
                now,
            ),
        )
        inserted += 1
    return inserted


def _mark_demo_history(conn, matter_id: int) -> None:
    """给演示数据补一条已读风险与一条已解决风险，展示完整状态流转。"""
    now = _now()
    conn.execute(
        "UPDATE risks SET status = 'read', read_at = ? WHERE matter_id = ? "
        "AND status = 'active' AND risk_type = 'material_pending'",
        (now, matter_id),
    )
    task_row = conn.execute(
        "SELECT id, title, deadline FROM tasks WHERE matter_id = ? AND status = 'done' "
        "ORDER BY id ASC LIMIT 1",
        (matter_id,),
    ).fetchone()
    if task_row is not None:
        conn.execute(
            "INSERT OR IGNORE INTO risks (fingerprint, risk_type, risk_level, title, "
            "description, matter_id, task_id, material_id, evidence_json, suggestion, "
            "status, first_seen_at, last_seen_at, resolved_at) "
            "VALUES (?, 'due_soon', 'low', ?, '任务完成后，该提醒已自动解除。', ?, ?, "
            "NULL, '{}', '', 'resolved', ?, ?, ?)",
            (
                f"demo-resolved|task:{task_row['id']}",
                f"任务即将截止：{task_row['title']}",
                matter_id,
                task_row["id"],
                now,
                now,
                now,
            ),
        )


def get_demo_status() -> DemoStatus:
    with get_connection() as conn:
        demo_matters = conn.execute(
            "SELECT COUNT(*) AS total, MAX(created_at) AS seeded_at "
            "FROM matters WHERE is_demo = 1"
        ).fetchone()
        real_matters = conn.execute(
            "SELECT COUNT(*) AS total FROM matters WHERE is_demo = 0"
        ).fetchone()
        tasks = conn.execute(
            "SELECT COUNT(*) AS total FROM tasks t "
            "JOIN matters mt ON mt.id = t.matter_id WHERE mt.is_demo = 1"
        ).fetchone()
        materials = conn.execute(
            "SELECT COUNT(*) AS total FROM materials m "
            "JOIN matters mt ON mt.id = m.matter_id WHERE mt.is_demo = 1"
        ).fetchone()
        risks = conn.execute(
            "SELECT COUNT(*) AS total FROM risks r "
            "JOIN matters mt ON mt.id = r.matter_id WHERE mt.is_demo = 1"
        ).fetchone()

    seeded = int(demo_matters["total"]) > 0
    return DemoStatus(
        available=True,
        seeded=seeded,
        matters=int(demo_matters["total"]),
        tasks=int(tasks["total"]),
        materials=int(materials["total"]),
        risks=int(risks["total"]),
        real_matters=int(real_matters["total"]),
        seeded_at=demo_matters["seeded_at"] if seeded else None,
        message=(
            "演示数据已初始化，可在总览页切换到「演示数据」查看。"
            if seeded
            else "尚未初始化演示数据。"
        ),
    )


def _prune_unreferenced_demo_files() -> None:
    """删除 demo/ 下已不再被材料记录引用的文件。

    刷新后旧文件名带有旧事项 id，写入新数据后这些文件不再被引用。
    只遍历 demo/ 的直接子文件，不递归，也不会触碰该目录之外的路径。
    """
    folder = _demo_folder()
    if not folder.is_dir():
        return
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT file_path FROM materials WHERE file_path LIKE ?",
            (f"{DEMO_DIR_NAME}/%",),
        ).fetchall()
    referenced = {Path(row["file_path"]).name for row in rows if row["file_path"]}
    for path in folder.iterdir():
        if not path.is_file() or path.name in referenced:
            continue
        try:
            path.unlink()
        except OSError:
            logger.warning("删除演示残留文件失败：%s", path.name)


def seed_demo_data(refresh: bool = False) -> DemoStatus:
    """初始化演示数据。

    - refresh=False：保持幂等语义，已存在演示数据时直接返回，不重复写入；
    - refresh=True：在与写入相同的事务内删除 is_demo = 1 的事项（任务、材料、
      风险由外键级联删除），再按调用当天重新计算日期写入；插入失败整体回滚，
      不会留下半套数据。
    """
    status = get_demo_status()
    if status.seeded and not refresh:
        return status
    replaced = status.seeded

    matters = _build_matters()
    now = _now()
    demo_matter_ids: set[int] = set()

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if replaced:
            # 复用清理语义：只删除演示事项，正式数据不参与。
            conn.execute("DELETE FROM matters WHERE is_demo = 1")
        activity_id = _insert_matter(conn, matters[0], now)
        contest_id = _insert_matter(conn, matters[1], now)
        recruit_id = _insert_matter(conn, matters[2], now)
        demo_matter_ids = {activity_id, contest_id, recruit_id}

        # 事项一：活动通知
        _insert_task(conn, activity_id, _task("提交志愿者报名表", 3, "high", "pending"))
        _insert_task(conn, activity_id, _task("参加岗前培训", 6, "medium", "pending"))
        _insert_task(conn, activity_id, _task("确认活动物资清单", None, "low", "pending"))
        _insert_task(conn, activity_id, _task("领取志愿者证", None, "low", "done"))
        _insert_material(conn, activity_id, _material_row("志愿者报名表", "需本人签字", "missing", None), now)
        _insert_material(
            conn,
            activity_id,
            _material_row("志愿服务承诺书", "需本人签字", "pending", "本人自愿参加校园开放日志愿服务活动，并遵守相关安排。"),
            now,
        )
        _insert_material(
            conn,
            activity_id,
            _material_row("培训签到表", "岗前培训现场签到", "qualified", "岗前培训签到表：姓名 张同学，签到时间 09:00。"),
            now,
        )
        _insert_material(
            conn,
            activity_id,
            _material_row("活动安全预案", "由活动负责人提交", "uncertain", "安全预案内容待补充，现场疏散路线未写明。"),
            now,
        )

        # 事项二：竞赛通知（含逾期）
        _insert_task(conn, contest_id, _task("提交作品终稿", -2, "high", "pending"))
        _insert_task(conn, contest_id, _task("完成报名缴费", -1, "high", "pending"))
        _insert_task(conn, contest_id, _task("组队信息确认", None, "medium", "done"))
        _insert_material(
            conn,
            contest_id,
            _material_row("参赛报名表", "需全部成员签字", "conflict", "参赛报名表：团队人数 4 人，成员名单与系统登记不一致。"),
            now,
        )
        _insert_material(
            conn,
            contest_id,
            _material_row("项目作品说明书", "不超过 20 页", "qualified", "项目作品说明书，共 16 页，含项目简介与实施计划。"),
            now,
        )
        _insert_material(conn, contest_id, _material_row("指导教师推荐信", "需教师签字", "missing", None), now)

        # 事项三：招聘通知
        _insert_task(conn, recruit_id, _task("在线投递简历", 5, "medium", "pending"))
        _insert_task(conn, recruit_id, _task("准备面试材料", 18, "low", "pending"))
        _insert_task(conn, recruit_id, _task("参加招聘宣讲会", None, "low", "pending"))
        _insert_material(conn, recruit_id, _material_row("个人简历", "需附近期照片", "missing", None), now)
        _insert_material(
            conn,
            recruit_id,
            _material_row("学历学位证书", "需扫描件", "pending", "学历证书扫描件：本科，专业为公共管理。"),
            now,
        )
        _insert_material(
            conn,
            recruit_id,
            _material_row("身份证复印件", "正反面复印", "incomplete", "身份证复印件：仅提供正面，缺少反面。"),
            now,
        )

    risk_count = 0
    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            risk_count = _seed_risk_rows(conn, demo_matter_ids)
            _mark_demo_history(conn, activity_id)
    except Exception:
        # 风险阶段失败时不留半套数据：连同刚写入的事项一起清理后再抛出。
        clear_demo_data()
        raise

    if replaced:
        # 旧文件名带旧事项 id，已不再被引用，删除这些残留文件。
        _prune_unreferenced_demo_files()

    logger.info(
        "演示数据%s完成：%s 个事项，%s 条风险",
        "刷新" if replaced else "初始化",
        len(demo_matter_ids),
        risk_count,
    )
    result = get_demo_status()
    result.refreshed = replaced
    return result


def clear_demo_data() -> tuple[DemoStatus, int]:
    """只删除 is_demo = 1 的事项及其级联数据，并清理 demo 上传目录。"""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id FROM matters WHERE is_demo = 1"
        ).fetchall()
        removed = len(rows)
        if removed:
            conn.execute("DELETE FROM matters WHERE is_demo = 1")

    folder = _demo_folder()
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)

    logger.info("演示数据已清理：删除 %s 个演示事项", removed)
    return get_demo_status(), removed
