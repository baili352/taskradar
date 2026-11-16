"""TaskRadar 第五阶段第二步：API 端到端测试驱动。

对 12 份测试文档执行 17 步流程，并覆盖边界场景。
所有写入均发生在 e2e_tests/data 下的独立数据库与上传目录。
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import request, upload_file  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MATERIALS = ROOT / "materials"
EVIDENCE = ROOT / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

CHECKS: list[dict] = []
STARTED = datetime.now().isoformat(timespec="seconds")


def add_check(
    category: str,
    name: str,
    ok: bool | None,
    expected: str,
    actual: str,
    case: str = "",
    repro: str = "",
    evidence: str = "",
    status: str | None = None,
) -> None:
    result = status or ("PASS" if ok else "FAIL")
    CHECKS.append(
        {
            "category": category,
            "case": case,
            "name": name,
            "result": result,
            "expected": expected,
            "actual": actual,
            "repro": repro,
            "evidence": evidence,
        }
    )
    print(f"[{result}] {category} | {case} | {name} -> {actual}")


def norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "")


def read_source_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    if suffix == ".docx":
        from docx import Document

        document = Document(path)
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    if suffix == ".pdf":
        import fitz

        pdf = fitz.open(path)
        try:
            return "\n".join(page.get_text("text") for page in pdf)
        finally:
            pdf.close()
    return ""


@dataclass
class Case:
    filename: str
    expected_start: str | None
    expected_deadline: str | None
    expected_type: str | None
    expected_process: int
    expected_materials: list[str]
    title: str
    material_file: str = "material_ok.txt"
    confirm_status: str = "qualified"
    extra: dict = field(default_factory=dict)


CASES: list[Case] = [
    Case("d01_校园活动通知.txt", None, None, None, 3, ["报名表", "学生证复印件"], "关于开展2026年校园文化节活动的通知"),
    Case("d02_竞赛通知.docx", "2026年3月1日", "2026年3月31日", "活动赛事", 3, ["项目申报书", "推荐", "承诺书"], "关于举办2026年大学生创新创业竞赛的通知", confirm_status="incomplete"),
    Case("d03_跨年度申报通知.txt", "2026年12月1日", "2027年1月15日", "材料申报", 3, ["社会实践项目申请书", "实践方案", "安全承诺书"], "关于2027年寒假社会实践项目申报的通知"),
    Case("d04_多材料申报通知.docx", "2026年5月6日", "2026年5月26日", "材料申报", 4, ["学生科研项目申请书", "项目汇总表", "承诺书", "成绩单复印件"], "关于2026年度学生科研项目申报的通知", material_file="material_suspicious.txt"),
    Case("d05_招聘公告.txt", "2026年5月6日", "2026年5月20日", "招聘招录", 3, ["应聘报名表", "个人简历", "学历学位证书复印件", "身份证复印件"], "某大学2026年公开招聘工作人员公告"),
    Case("d06_日期模糊通知.txt", None, "5月20日", "材料申报", 3, ["资助申请表", "家庭情况说明"], "关于2026年春季学期资助申请的通知"),
    Case("d07_多流程办事通知.docx", "2026年9月1日", "2026年9月30日", "证件办理", 4, ["一卡通补办申请表", "身份证复印件"], "关于办理2026年校园一卡通补办的通知"),
    Case("d08_无材料要求通知.txt", None, None, "活动赛事", 2, [], "关于举办2026年秋季运动会的通知"),
    Case("d09_标题含材料关键词通知.txt", "2026年9月10日", "2026年9月25日", "材料申报", 3, ["国家奖学金申请表", "成绩单", "获奖证书复印件"], "关于提交2026年国家奖学金材料的通知"),
    Case("d10_信息冲突通知.docx", "2026年5月1日", "2026年5月10日", "活动赛事", 2, ["优秀学生申请表", "成绩单复印件", "获奖证明"], "关于2026年优秀学生评选工作的通知"),
    Case("d11_空流程通知.txt", None, None, "会议培训", 0, [], "关于举办2026年学术讲座的通知"),
    Case("d12_非法日期通知.txt", None, "2026年2月30日", "材料申报", 2, ["事项申请表"], "关于2026年2月30日事项申报的通知"),
]


def build_payload(analysis: dict, filename: str) -> dict:
    fields = {item["key"]: item for item in analysis["fields"]}
    title = fields.get("title", {}).get("value") or Path(filename).stem
    deadline = fields.get("deadline", {}).get("value")
    return {
        "name": title,
        "matter_type": fields.get("matter_type", {}).get("value") or "",
        "qualification": fields.get("qualification", {}).get("value") or "",
        "registration_start": fields.get("registration_start", {}).get("value"),
        "deadline": deadline,
        "deadline_source": "document" if deadline else "none",
        "materials": analysis["materials"],
        "process": analysis["process"],
        "notes": analysis["notes"],
        "fields": analysis["fields"],
        "source_filename": filename,
        "status": "pending",
    }


def risk_types(risks: list[dict]) -> list[str]:
    return [item["risk_type"] for item in risks]


def find_risk(risks: list[dict], risk_type: str, **kwargs) -> dict | None:
    for item in risks:
        if item["risk_type"] != risk_type:
            continue
        if any(item.get(key) != value for key, value in kwargs.items()):
            continue
        return item
    return None


def run_case(case: Case) -> dict:
    path = DOCS / case.filename
    source_text = read_source_text(path)
    evidence: dict = {"file": case.filename, "steps": {}, "checks": []}

    def record(step: str, value) -> None:
        evidence["steps"][step] = value

    # 1. 上传文档
    res = upload_file("/analysis/analyze", path)
    record("1_analyze", {"status": res.status, "body": res.body})
    add_check(
        "文档解析",
        "上传并解析成功",
        res.status == 200,
        "HTTP 200",
        f"HTTP {res.status}",
        case.filename,
        f"POST /api/analysis/analyze 上传 {case.filename}",
        f"evidence/{case.filename}.json#1_analyze",
    )
    if res.status != 200:
        return evidence

    analysis = res.body
    fields = {item["key"]: item for item in analysis["fields"]}

    # 2. 解析结果基础信息
    add_check(
        "文档解析",
        "文档内容被真实读取",
        analysis["document"]["char_count"] > 0,
        "char_count > 0",
        f"char_count={analysis['document']['char_count']}",
        case.filename,
        "检查 analyze 返回的 document.char_count",
    )
    expected_title = case.title
    if expected_title:
        actual_title = fields.get("title", {}).get("value")
        add_check(
            "文档解析",
            "事项名称与标题一致",
            actual_title == expected_title,
            expected_title,
            str(actual_title),
            case.filename,
        )

    # 3. 字段检查
    for key, label in (
        ("title", "事项名称"),
        ("matter_type", "事项类型"),
        ("qualification", "申请资格"),
        ("registration_start", "报名开始日期"),
        ("deadline", "截止日期"),
    ):
        item = fields.get(key)
        add_check(
            "文档解析",
            f"字段存在：{label}",
            item is not None,
            "字段存在",
            "存在" if item else "缺失",
            case.filename,
        )

    actual_start = fields.get("registration_start", {}).get("value")
    add_check(
        "文档解析",
        "报名开始日期解析",
        actual_start == case.expected_start,
        str(case.expected_start),
        str(actual_start),
        case.filename,
    )
    actual_deadline = fields.get("deadline", {}).get("value")
    add_check(
        "文档解析",
        "截止日期解析",
        actual_deadline == case.expected_deadline,
        str(case.expected_deadline),
        str(actual_deadline),
        case.filename,
    )

    # 4. 原文证据检查
    evidence_failures = []
    for field_item in analysis["fields"]:
        if field_item["status"] == "found" and not field_item["evidence"]:
            evidence_failures.append(f"字段 {field_item['key']} 缺少证据")
    for item in analysis["materials"] + analysis["process"] + analysis["notes"]:
        ev = item.get("evidence") or {}
        if not ev.get("text") or not ev.get("location"):
            evidence_failures.append(f"条目 {item.get('name') or item.get('text')} 缺少证据")
            continue
        head = norm(ev["text"])[:30]
        if head and head not in norm(source_text):
            evidence_failures.append(f"证据文本不在原文中：{head}")
    add_check(
        "文档解析",
        "每条提取结果均带原文证据",
        not evidence_failures,
        "所有 found 字段/材料/流程/备注均有可回溯证据",
        "通过" if not evidence_failures else "；".join(evidence_failures[:5]),
        case.filename,
        "逐条比对 evidence.text/location 与原文",
    )

    # 事项类型
    actual_type = fields.get("matter_type", {}).get("value")
    add_check(
        "文档解析",
        "事项类型识别",
        case.expected_type is None or actual_type == case.expected_type,
        str(case.expected_type),
        str(actual_type),
        case.filename,
    )

    # 流程步骤与材料名称覆盖
    actual_process_texts = [item["text"] for item in analysis["process"]]
    add_check(
        "文档解析",
        "流程步骤数量与原文一致",
        len(actual_process_texts) == case.expected_process,
        f"{case.expected_process} 个流程步骤",
        f"{len(actual_process_texts)} 个：{actual_process_texts}",
        case.filename,
        "核对解析出的 process 数量",
    )
    actual_material_names = [item["name"] for item in analysis["materials"]]
    missing_names = [
        keyword
        for keyword in case.expected_materials
        if not any(keyword in name for name in actual_material_names)
    ]
    add_check(
        "文档解析",
        "材料名称覆盖原文要求",
        not missing_names,
        f"包含：{case.expected_materials}",
        f"缺失：{missing_names}；实际={actual_material_names}",
        case.filename,
        "核对解析出的 materials 名称",
    )
    if case.filename == "d09_标题含材料关键词通知.txt":
        false_positive = [
            name
            for name in actual_material_names
            if "国家奖学金材料" in name or name in {"材料", "相关材料"} or name.startswith("关于")
        ]
        add_check(
            "文档解析",
            "标题中的“材料”未被误提取为材料名称",
            not false_positive,
            "材料名称均来自材料清单",
            f"误提取：{false_positive}；实际={actual_material_names}",
            case.filename,
            "检查 materials 中是否包含标题片段",
        )

    # 5. 保存事项
    payload = build_payload(analysis, case.filename)
    res = request("POST", "/matters", payload)
    record("5_create_matter", {"status": res.status, "body": res.body})
    add_check(
        "事项管理",
        "保存为事项",
        res.status == 201,
        "HTTP 201",
        f"HTTP {res.status}",
        case.filename,
        "POST /api/matters",
    )
    if res.status != 201:
        return evidence
    matter = res.body
    matter_id = matter["id"]

    # 6. 刷新/重新读取事项
    res = request("GET", f"/matters/{matter_id}")
    record("6_get_matter", {"status": res.status, "body": res.body})
    add_check(
        "事项管理",
        "刷新后事项仍存在",
        res.status == 200 and res.body["name"] == payload["name"],
        f"HTTP 200 且名称={payload['name']}",
        f"HTTP {res.status} 名称={res.body.get('name') if res.body else None}",
        case.filename,
        f"GET /api/matters/{matter_id}",
    )
    saved = res.body if res.status == 200 else {}
    add_check(
        "前后端集成",
        "保存后字段与解析结果一致",
        saved.get("deadline") == payload["deadline"]
        and saved.get("registration_start") == payload["registration_start"]
        and len(saved.get("materials", [])) == len(payload["materials"])
        and len(saved.get("process", [])) == len(payload["process"]),
        "日期、材料数、流程数与解析结果一致",
        f"deadline={saved.get('deadline')}, start={saved.get('registration_start')}, "
        f"materials={len(saved.get('materials', []))}, process={len(saved.get('process', []))}",
        case.filename,
    )

    # 7. 生成任务
    original_process = [step["text"] for step in payload["process"]]
    res = request("POST", f"/matters/{matter_id}/tasks")
    record("7_generate_tasks", {"status": res.status, "body": res.body})
    add_check(
        "任务管理",
        "按办理流程生成任务",
        res.status == 201,
        "HTTP 201",
        f"HTTP {res.status}",
        case.filename,
        f"POST /api/matters/{matter_id}/tasks",
    )
    gen = res.body or {}
    first_created = gen.get("created", 0)
    add_check(
        "任务管理",
        "任务数量与流程步骤一致",
        first_created == len(original_process),
        f"{len(original_process)} 个任务",
        f"{first_created} 个任务",
        case.filename,
        f"比对 process={len(original_process)} 与 created={first_created}",
    )
    tasks = gen.get("tasks", [])
    descriptions = [task["description"] for task in tasks]
    add_check(
        "任务管理",
        "任务来自真实流程步骤",
        set(descriptions) <= set(original_process),
        "任务描述均来自原文流程步骤",
        "全部匹配" if set(descriptions) <= set(original_process) else str(set(descriptions) - set(original_process)),
        case.filename,
        "比对任务 description 与事项 process.text",
    )
    evidence_ok = all(task.get("source_evidence") and task["source_evidence"].get("text") for task in tasks)
    add_check(
        "任务管理",
        "任务保留原文证据",
        evidence_ok,
        "每个任务有 source_evidence.text",
        "通过" if evidence_ok else "存在缺少证据的任务",
        case.filename,
    )

    # 8/9. 重复生成
    res = request("POST", f"/matters/{matter_id}/tasks")
    record("9_generate_tasks_again", {"status": res.status, "body": res.body})
    gen2 = res.body or {}
    tasks_after = request("GET", "/tasks", params={"matter_id": matter_id}).body or []
    add_check(
        "任务管理",
        "重复生成不产生重复任务",
        res.status == 201 and gen2.get("created") == 0 and len(tasks_after) == first_created,
        f"created=0 且任务总数保持 {first_created}",
        f"created={gen2.get('created')} 任务总数={len(tasks_after)}",
        case.filename,
        f"连续两次 POST /api/matters/{matter_id}/tasks",
    )

    # 10. 生成材料清单
    res = request("POST", f"/matters/{matter_id}/materials/generate")
    record("10_generate_materials", {"status": res.status, "body": res.body})
    mat_gen = res.body or {}
    expected_materials = len(payload["materials"])
    add_check(
        "材料管理",
        "按原文材料要求生成清单",
        res.status == 201 and mat_gen.get("created") == expected_materials,
        f"{expected_materials} 项材料",
        f"created={mat_gen.get('created')} skipped={mat_gen.get('skipped')}",
        case.filename,
        f"POST /api/matters/{matter_id}/materials/generate",
    )
    materials = request("GET", f"/matters/{matter_id}/materials").body or []

    # 11-13. 上传、核验、人工确认
    if materials:
        target = materials[0]
        res = upload_file(f"/materials/{target['id']}/file", MATERIALS / case.material_file)
        record("11_upload_material", {"status": res.status, "body": res.body})
        add_check(
            "材料管理",
            "上传材料测试文件",
            res.status == 200 and res.body.get("status") == "pending",
            "HTTP 200 且状态 pending",
            f"HTTP {res.status} 状态={res.body.get('status') if res.body else None}",
            case.filename,
            f"POST /api/materials/{target['id']}/file",
        )

        res = request("POST", f"/materials/{target['id']}/verify")
        record("12_verify_material", {"status": res.status, "body": res.body})
        verification = (res.body or {}).get("verification") or {}
        add_check(
            "材料管理",
            "执行规则核验",
            res.status == 200 and verification.get("result") in {"qualified", "incomplete", "conflict", "uncertain"},
            "返回合法核验结论",
            str(verification.get("result")),
            case.filename,
            f"POST /api/materials/{target['id']}/verify",
        )
        add_check(
            "材料管理",
            "核验记录包含逐项依据",
            len(verification.get("checks", [])) >= 3 and bool(verification.get("summary")),
            "至少 3 项检查且有结论说明",
            f"checks={len(verification.get('checks', []))}",
            case.filename,
        )

        res = request(
            "POST",
            f"/materials/{target['id']}/confirm",
            {"status": case.confirm_status, "note": "E2E 测试人工确认", "evidence_text": "测试用途材料样本"},
        )
        record("13_confirm_material", {"status": res.status, "body": res.body})
        add_check(
            "材料管理",
            "人工确认写入记录",
            res.status == 200 and res.body.get("status") == case.confirm_status,
            f"HTTP 200 且状态={case.confirm_status}",
            f"HTTP {res.status} 状态={res.body.get('status') if res.body else None}",
            case.filename,
            f"POST /api/materials/{target['id']}/confirm",
        )
        detail = request("GET", f"/materials/{target['id']}").body or {}
        record("13_material_detail", detail)
        events = detail.get("events") or []
        add_check(
            "材料管理",
            "人工确认记录可追溯",
            len(events) >= 1 and any("确认" in (item.get("action") or "") or "confirm" in (item.get("action") or "").lower() for item in events),
            "material_events 中存在确认记录",
            f"events={[item.get('action') for item in events]}",
            case.filename,
        )
    else:
        add_check(
            "材料管理",
            "无材料要求时给出明确提示",
            mat_gen.get("created") == 0 and "没有登记材料要求" in (mat_gen.get("message") or ""),
            "created=0 且提示未登记材料要求",
            f"created={mat_gen.get('created')} message={mat_gen.get('message')}",
            case.filename,
        )
        target = None
        for step in ("11_upload_material", "12_verify_material", "13_confirm_material"):
            add_check(
                "材料管理",
                step,
                None,
                "不适用（该事项无材料要求）",
                "未执行",
                case.filename,
                status="UNEXECUTED",
            )

    # 14. 刷新风险
    res = request("POST", "/risks/refresh")
    record("14_refresh_risks", {"status": res.status, "body": res.body})
    add_check(
        "风险预警",
        "主动刷新风险",
        res.status == 200,
        "HTTP 200",
        f"HTTP {res.status}",
        case.filename,
        "POST /api/risks/refresh",
    )
    matter_risks_res = request("GET", f"/matters/{matter_id}/risks")
    record("14_matter_risks", {"status": matter_risks_res.status, "body": matter_risks_res.body})
    summary = (matter_risks_res.body or {}).get("summary") or {}
    risks = (matter_risks_res.body or {}).get("risks") or []
    types = risk_types(risks)

    # 15. 日期 / 材料 / 任务风险
    expected_date_risk = case.filename in {"d06_日期模糊通知.txt", "d12_非法日期通知.txt"}
    has_date_risk = "date_unverified" in types
    add_check(
        "风险预警",
        "日期风险判断",
        has_date_risk == expected_date_risk,
        "应出现 date_unverified" if expected_date_risk else "不应出现 date_unverified",
        f"实际风险类型={types}",
        case.filename,
        "检查事项风险列表中的 date_unverified",
    )

    if materials:
        missing_count = sum(1 for item in risks if item["risk_type"] == "material_missing")
        # 第一项已上传并人工确认；其余材料仍为 missing。
        expected_missing = max(len(materials) - 1, 0)
        add_check(
            "风险预警",
            "材料缺失风险数量",
            missing_count == expected_missing,
            f"{expected_missing} 项 material_missing",
            f"{missing_count} 项",
            case.filename,
            "核对材料状态与 material_missing 风险数量",
        )
    else:
        add_check(
            "风险预警",
            "无材料时不产生材料风险",
            not any(item.startswith("material_") for item in types),
            "无 material_* 风险",
            f"实际={types}",
            case.filename,
        )

    unfinished = [task for task in tasks_after if task["status"] != "done"]
    expected_backlog = len(unfinished) >= 2
    has_backlog = "backlog" in types
    add_check(
        "风险预警",
        "任务积压风险判断",
        has_backlog == expected_backlog,
        f"{'应' if expected_backlog else '不应'}出现 backlog",
        f"未完成任务={len(unfinished)} 风险={types}",
        case.filename,
    )

    # 16. 修改任务状态并观察风险变化
    if tasks_after:
        first_task = tasks_after[0]
        request("PATCH", f"/tasks/{first_task['id']}", {"status": "done"})
        request("POST", "/risks/refresh")
        after_one = (request("GET", f"/matters/{matter_id}/risks").body or {}).get("risks") or []
        request("PATCH", f"/tasks/{first_task['id']}", {"status": "pending"})
        request("POST", "/risks/refresh")
        reopened = (request("GET", f"/matters/{matter_id}/risks").body or {}).get("risks") or []
        record(
            "16_task_status_change",
            {"task_id": first_task["id"], "after_done": risk_types(after_one), "after_reopen": risk_types(reopened)},
        )
        add_check(
            "风险预警",
            "任务完成/重新打开后风险同步变化",
            "backlog" not in risk_types(after_one) or len(tasks_after) > 2,
            "完成一个任务后风险列表被重新计算",
            f"完成后={risk_types(after_one)}；重开后={risk_types(reopened)}",
            case.filename,
            f"PATCH /api/tasks/{first_task['id']} status=done -> refresh -> status=pending",
        )
        # 全部完成后再检查积压风险是否消失
        for task in tasks_after:
            request("PATCH", f"/tasks/{task['id']}", {"status": "done"})
        request("POST", "/risks/refresh")
        all_done_risks = (request("GET", f"/matters/{matter_id}/risks").body or {}).get("risks") or []
        record("16_all_tasks_done_risks", risk_types(all_done_risks))
        add_check(
            "风险预警",
            "全部任务完成后积压风险消失",
            "backlog" not in risk_types(all_done_risks),
            "无 backlog 风险",
            f"实际={risk_types(all_done_risks)}",
            case.filename,
            "将所有任务标记 done 后刷新风险",
        )
        # 恢复一个任务为未完成，保留可交互数据
        request("PATCH", f"/tasks/{tasks_after[0]['id']}", {"status": "pending"})
        request("POST", "/risks/refresh")
    else:
        add_check(
            "风险预警",
            "空流程任务风险",
            not any(item in types for item in ("overdue", "due_soon", "backlog")),
            "空流程不应产生任务风险",
            f"实际={types}",
            case.filename,
        )

    # 事项完成边界：d01
    if case.filename == "d01_校园活动通知.txt":
        request("PATCH", f"/matters/{matter_id}", {"status": "done"})
        request("POST", "/risks/refresh")
        done_risks = (request("GET", f"/matters/{matter_id}/risks").body or {}).get("risks") or []
        done_summary = (request("GET", f"/matters/{matter_id}/risks").body or {}).get("summary") or {}
        record("b10_completed_matter", {"risks": risk_types(done_risks), "summary": done_summary})
        add_check(
            "风险预警",
            "已完成事项不再产生未完成风险",
            len(done_risks) == 0,
            "0 条未解决风险",
            f"{len(done_risks)} 条：{risk_types(done_risks)}",
            case.filename,
            "PATCH 事项 status=done 后刷新风险",
        )

    evidence["matter_id"] = matter_id
    evidence["task_ids"] = [task["id"] for task in tasks_after]
    evidence["material_ids"] = [item["id"] for item in materials]
    return evidence


def boundary_tests(context: dict) -> None:
    """边界场景：无截止、已读、风险重现、文件异常、材料异常等。"""

    # B01 无截止日期的事项
    res = request("POST", "/matters", {"name": "边界测试-无截止日期事项（测试用途）", "deadline_source": "none"})
    add_check(
        "事项管理",
        "边界：无截止日期事项可保存",
        res.status == 201 and res.body.get("deadline") is None,
        "HTTP 201 且 deadline 为空",
        f"HTTP {res.status}",
        "B01-无截止日期",
        "POST /api/matters，仅提供名称",
    )
    if res.status == 201:
        request("POST", "/risks/refresh")
        risks = (request("GET", f"/matters/{res.body['id']}/risks").body or {}).get("risks") or []
        add_check(
            "风险预警",
            "边界：无截止日期不产生日期风险",
            not any(item["risk_type"] in {"overdue", "due_soon", "date_unverified"} for item in risks),
            "无日期类风险",
            f"实际={risk_types(risks)}",
            "B01-无截止日期",
        )

    # B11 已读风险
    d05 = context.get("d05_招聘公告.txt", {})
    risks = (request("GET", "/risks", params={"matter_id": d05.get("matter_id"), "status": "unresolved"}).body or {}).get("items") or []
    target_risk = next((item for item in risks if item["risk_type"] == "material_missing"), None)
    if target_risk:
        before = request("GET", f"/risks/{target_risk['id']}").body or {}
        res = request("PATCH", f"/risks/{target_risk['id']}/read")
        after = request("GET", f"/risks/{target_risk['id']}").body or {}
        add_check(
            "风险预警",
            "边界：标记已读",
            res.status == 200 and after.get("status") == "read" and after.get("read_at"),
            "status=read 且 read_at 有值",
            f"status={after.get('status')} read_at={after.get('read_at')}",
            "B11-已读风险",
            f"PATCH /api/risks/{target_risk['id']}/read",
        )
        add_check(
            "风险预警",
            "边界：标记已读不改变 last_seen_at",
            before.get("last_seen_at") == after.get("last_seen_at"),
            "last_seen_at 保持不变",
            f"before={before.get('last_seen_at')} after={after.get('last_seen_at')}",
            "B11-已读风险",
        )
    else:
        add_check("风险预警", "边界：标记已读", None, "存在可读风险", "未找到 material_missing 风险", "B11-已读风险", status="UNEXECUTED")

    # B12 已解决风险重新出现（逾期风险链路）
    d02 = context.get("d02_竞赛通知.docx", {})
    task_ids = d02.get("task_ids") or []
    if task_ids:
        task_id = task_ids[0]
        request("PATCH", f"/tasks/{task_id}", {"deadline": "2026-01-01", "deadline_source": "manual", "status": "pending"})
        refresh1 = request("POST", "/risks/refresh").body or {}
        overdue = next(
            (
                item
                for item in (request("GET", "/risks", params={"matter_id": d02["matter_id"], "status": "unresolved"}).body or {}).get("items", [])
                if item["risk_type"] == "overdue" and item["task_id"] == task_id
            ),
            None,
        )
        add_check(
            "风险预警",
            "边界：逾期任务生成风险",
            overdue is not None,
            "出现 overdue 风险",
            f"overdue={'存在' if overdue else '缺失'} refresh={refresh1}",
            "B12-已解决风险重现",
            "将任务截止日期改为 2026-01-01（manual）后刷新",
        )
        if overdue:
            request("PATCH", f"/tasks/{task_id}", {"status": "done"})
            request("POST", "/risks/refresh")
            resolved = request("GET", f"/risks/{overdue['id']}").body or {}
            add_check(
                "风险预警",
                "边界：任务完成后逾期风险归档",
                resolved.get("status") == "resolved",
                "status=resolved",
                f"status={resolved.get('status')}",
                "B12-已解决风险重现",
                "任务标记 done 后刷新",
            )
            request("PATCH", f"/tasks/{task_id}", {"status": "pending"})
            refresh2 = request("POST", "/risks/refresh").body or {}
            revived = request("GET", f"/risks/{overdue['id']}").body or {}
            add_check(
                "风险预警",
                "边界：已解决风险重新出现",
                revived.get("status") in {"active", "read"} and (refresh2.get("revived") or 0) >= 1,
                "同一风险重新激活且 revived >= 1",
                f"status={revived.get('status')} revived={refresh2.get('revived')}",
                "B12-已解决风险重现",
                "重新打开任务后刷新",
            )

    # B13-B15 文件异常
    d07 = context.get("d07_多流程办事通知.docx", {})
    material_ids = d07.get("material_ids") or []
    if material_ids:
        mid = material_ids[0]
        original = request("GET", f"/materials/{mid}").body or {}
        corrupt = upload_file(f"/materials/{mid}/file", MATERIALS / "corrupt.docx")
        add_check(
            "材料管理",
            "边界：损坏文件被拒绝",
            corrupt.status == 422 and (corrupt.body or {}).get("detail", {}).get("code") == "invalid_document",
            "HTTP 422 invalid_document",
            f"HTTP {corrupt.status} {(corrupt.body or {}).get('detail')}",
            "B13-损坏文件",
            f"POST /api/materials/{mid}/file 上传 corrupt.docx",
        )
        wrong = upload_file(f"/materials/{mid}/file", MATERIALS / "wrong_format.xlsx")
        add_check(
            "材料管理",
            "边界：错误格式被拒绝",
            wrong.status == 415 and (wrong.body or {}).get("detail", {}).get("code") == "unsupported_format",
            "HTTP 415 unsupported_format",
            f"HTTP {wrong.status} {(wrong.body or {}).get('detail')}",
            "B14-格式错误",
            f"POST /api/materials/{mid}/file 上传 wrong_format.xlsx",
        )
        empty = upload_file(f"/materials/{mid}/file", MATERIALS / "empty.txt")
        add_check(
            "材料管理",
            "边界：空文件被拒绝",
            empty.status == 400 and (empty.body or {}).get("detail", {}).get("code") == "empty_file",
            "HTTP 400 empty_file",
            f"HTTP {empty.status} {(empty.body or {}).get('detail')}",
            "B15-空文件",
            f"POST /api/materials/{mid}/file 上传 empty.txt",
        )
        oversized = upload_file(f"/materials/{mid}/file", MATERIALS / "oversized.txt")
        add_check(
            "材料管理",
            "边界：超限文件被拒绝",
            oversized.status == 413 and (oversized.body or {}).get("detail", {}).get("code") == "file_too_large",
            "HTTP 413 file_too_large",
            f"HTTP {oversized.status} {(oversized.body or {}).get('detail')}",
            "B16-文件大小超限",
            f"POST /api/materials/{mid}/file 上传 10MB+ 文件",
        )
        after = request("GET", f"/materials/{mid}").body or {}
        add_check(
            "材料管理",
            "边界：失败上传不破坏已有文件记录",
            after.get("original_filename") == original.get("original_filename"),
            f"原文件名保持 {original.get('original_filename')}",
            f"当前={after.get('original_filename')}",
            "B13-B16 文件异常",
        )

    analyze_oversize = upload_file("/analysis/analyze", MATERIALS / "oversized.txt")
    add_check(
        "文档解析",
        "边界：分析接口拒绝超限文档",
        analyze_oversize.status == 413
        and (analyze_oversize.body or {}).get("detail", {}).get("code") == "file_too_large",
        "HTTP 413 file_too_large",
        f"HTTP {analyze_oversize.status} {(analyze_oversize.body or {}).get('detail')}",
        "B16-文件大小超限",
        "POST /api/analysis/analyze 上传 10MB+ 文本",
    )

    # B06 材料名称模糊 / B18 无法判断
    d08 = context.get("d08_无材料要求通知.txt", {})
    if d08.get("matter_id"):
        mid = d08["matter_id"]
        res = request("POST", f"/matters/{mid}/materials", {"name": "材料", "description": "相关材料"})
        add_check(
            "材料管理",
            "边界：模糊材料名称可登记",
            res.status == 201,
            "HTTP 201",
            f"HTTP {res.status}",
            "B06-材料名称模糊",
            f"POST /api/matters/{mid}/materials name=材料",
        )
        if res.status == 201:
            material_id = res.body["id"]
            upload_file(f"/materials/{material_id}/file", MATERIALS / "material_ok.txt")
            verify = request("POST", f"/materials/{material_id}/verify")
            add_check(
                "材料管理",
                "边界：材料无法判断时给出 uncertain",
                verify.status == 200 and (verify.body or {}).get("verification", {}).get("result") == "uncertain",
                "核验结果 uncertain",
                str((verify.body or {}).get("verification", {}).get("result")),
                "B18-材料无法判断",
                f"POST /api/materials/{material_id}/verify",
            )
            request("POST", "/risks/refresh")
            risks = (request("GET", "/risks", params={"matter_id": mid, "status": "unresolved"}).body or {}).get("items") or []
            add_check(
                "风险预警",
                "边界：无法判断材料产生低风险提醒",
                any(item["risk_type"] == "material_uncertain" and item["material_id"] == material_id for item in risks),
                "出现 material_uncertain",
                f"实际={risk_types(risks)}",
                "B18-材料无法判断",
            )

    # B17 材料信息冲突：d04 第二项材料
    d04 = context.get("d04_多材料申报通知.docx", {})
    d04_materials = d04.get("material_ids") or []
    if len(d04_materials) >= 2:
        mid = d04_materials[1]
        upload_file(f"/materials/{mid}/file", MATERIALS / "material_suspicious.txt")
        verify = request("POST", f"/materials/{mid}/verify")
        add_check(
            "材料管理",
            "边界：可疑材料不直接判定合格",
            verify.status == 200 and (verify.body or {}).get("verification", {}).get("result") in {"uncertain", "incomplete"},
            "核验结果 uncertain/incomplete",
            str((verify.body or {}).get("verification", {}).get("result")),
            "B17-材料信息冲突",
            f"POST /api/materials/{mid}/verify（文本含“已过期/失效”）",
        )
        confirm = request(
            "POST",
            f"/materials/{mid}/confirm",
            {"status": "conflict", "note": "E2E 测试：材料信息冲突", "evidence_text": "该证明材料已过期"},
        )
        add_check(
            "材料管理",
            "边界：人工可确认材料冲突",
            confirm.status == 200 and confirm.body.get("status") == "conflict",
            "status=conflict",
            f"HTTP {confirm.status} status={confirm.body.get('status') if confirm.body else None}",
            "B17-材料信息冲突",
            f"POST /api/materials/{mid}/confirm status=conflict",
        )
        request("POST", "/risks/refresh")
        risks = (request("GET", "/risks", params={"matter_id": d04["matter_id"], "status": "unresolved"}).body or {}).get("items") or []
        add_check(
            "风险预警",
            "边界：冲突材料产生高风险",
            any(item["risk_type"] == "material_conflict" and item["material_id"] == mid and item["risk_level"] == "high" for item in risks),
            "出现 high 级 material_conflict",
            f"实际={risk_types(risks)}",
            "B17-材料信息冲突",
        )

    # B14/B05 多截止日期提示（d10）
    d10 = context.get("d10_信息冲突通知.docx", {})
    analysis_10 = (d10.get("analysis") or {})
    if analysis_10:
        fields = {item["key"]: item for item in analysis_10.get("fields", [])}
        note = fields.get("deadline", {}).get("note") or ""
        add_check(
            "文档解析",
            "边界：多个截止日期应提示冲突",
            "多个截止日期" in note,
            "截止日期备注包含“多个截止日期”",
            f"note={note}",
            "B05-多个截止日期",
            "检查 d10 解析结果 deadline.note",
        )

    # B08 空流程
    d11 = context.get("d11_空流程通知.txt", {})
    if d11.get("matter_id"):
        tasks = request("GET", "/tasks", params={"matter_id": d11["matter_id"]}).body or []
        add_check(
            "任务管理",
            "边界：空流程不生成任务",
            len(tasks) == 0,
            "0 个任务",
            f"{len(tasks)} 个任务",
            "B08-空流程",
            "检查 d11 事项任务列表",
        )


def main() -> None:
    context: dict = {}
    all_evidence = []
    try:
        for case in CASES:
            print(f"\n===== 开始测试 {case.filename} =====")
            ev = run_case(case)
            # 补充解析快照用于边界测试
            if ev.get("steps", {}).get("1_analyze", {}).get("status") == 200:
                ev["analysis"] = ev["steps"]["1_analyze"]["body"]
            context[case.filename] = ev
            all_evidence.append(ev)
            (EVIDENCE / f"{case.filename}.json").write_text(
                json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        print("\n===== 开始边界测试 =====")
        boundary_tests(context)
    except Exception:
        traceback.print_exc()
        add_check("前后端集成", "测试驱动未异常退出", False, "无异常", traceback.format_exc()[:800], "全局")
    finally:
        snapshot = {
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "started_at": STARTED,
            "checks": CHECKS,
            "matter_ids": {
                name: ev.get("matter_id") for name, ev in context.items() if ev.get("matter_id")
            },
            "task_ids": {
                name: ev.get("task_ids") for name, ev in context.items() if ev.get("task_ids")
            },
            "material_ids": {
                name: ev.get("material_ids") for name, ev in context.items() if ev.get("material_ids")
            },
        }
        (EVIDENCE / "results_api.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n结果已写入 {EVIDENCE / 'results_api.json'}")


if __name__ == "__main__":
    main()
