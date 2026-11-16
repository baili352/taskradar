"""生成第五阶段第二步 E2E 测试用的模拟文档与材料。

所有文档均为测试用途模拟数据，不是任何真实官方文件。
"""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document

BASE = Path(__file__).resolve().parent.parent
DOCS = BASE / "docs"
MATERIALS = BASE / "materials"
EVIDENCE = BASE / "evidence"

PREFIX = "【测试用途模拟文档·非真实官方文件】"

DOC_CONTENTS = {
    "d01_校园活动通知.txt": {
        "title": "关于开展2026年校园文化节活动的通知",
        "body": [
            "全体在校学生：",
            "为丰富校园文化生活，学校决定开展2026年校园文化节活动，现将有关事项通知如下。",
            "一、活动主题",
            "青春校园，文化同行。",
            "二、活动时间",
            "2026年4月10日至2026年4月20日",
            "三、参与对象",
            "全体在校学生均可报名参加。",
            "四、报名方式",
            "1. 登录学校活动平台填写报名表。",
            "2. 将报名表和学生证复印件交至校团委办公室。",
            "3. 扫码加入活动通知群，确认报名成功。",
            "五、所需材料",
            "报名表、学生证复印件。",
            "六、注意事项",
            "请按时参加活动，服从现场安排。",
            "联系人：文化中心 联系电话：010-12345678",
            "校团委",
            "2026年3月20日",
        ],
        "kind": "普通校园活动通知",
        "focus": "活动时间区间、参与对象、流程步骤、材料与注意事项",
    },
    "d02_竞赛通知.docx": {
        "title": "关于举办2026年大学生创新创业竞赛的通知",
        "body": [
            "参赛对象：全日制在校本科生、研究生均可报名参加。",
            "一、报名时间",
            "2026年3月1日至2026年3月31日",
            "二、报名方式",
            "1. 登录竞赛平台填写报名表。",
            "2. 提交项目申报书和推荐表。",
            "3. 将纸质材料交至教务处创新创业办公室。",
            "三、材料要求",
            "《项目申报书》《推荐意见表》、承诺书。",
            "四、注意事项",
            "逾期不予受理，请提前准备材料。",
            "联系人：教务处 联系电话：010-87654321",
            "教务处",
            "2026年2月20日",
        ],
        "kind": "有明确报名起止日期的竞赛通知",
        "focus": "报名起止日期、多材料、流程步骤、逾期提示",
    },
    "d03_跨年度申报通知.txt": {
        "title": "关于2027年寒假社会实践项目申报的通知",
        "body": [
            "全体本科生、研究生：",
            "一、申报时间",
            "2026年12月1日至2027年1月15日",
            "二、申报对象",
            "全体在校学生均可申请参与。",
            "三、申报材料",
            "《社会实践项目申请书》、实践方案、安全承诺书。",
            "四、申报方式",
            "1. 填写社会实践项目申请书。",
            "2. 将申请书和实践方案发送至校团委邮箱。",
            "3. 登录实践管理系统确认提交。",
            "五、注意事项",
            "跨年度项目请合理安排时间，逾期不再受理。",
            "联系人：校团委 联系电话：010-65432100",
            "校团委",
            "2026年11月20日",
        ],
        "kind": "跨年度日期通知",
        "focus": "2026-12-01 至 2027-01-15 的跨年度区间解析",
    },
    "d04_多材料申报通知.docx": {
        "title": "关于2026年度学生科研项目申报的通知",
        "body": [
            "申请对象：全日制在校本科生、研究生。",
            "一、申报时间",
            "2026年5月6日至2026年5月26日",
            "二、申报材料",
            "《学生科研项目申请书》《项目汇总表》、承诺书、成绩单复印件。",
            "三、申报流程",
            "1. 下载并填写项目申请书。",
            "2. 准备项目汇总表和成绩单复印件。",
            "3. 将材料提交至学院科研办公室。",
            "4. 登录科研系统上传电子版。",
            "四、注意事项",
            "材料不齐全的不予受理。",
            "联系人：科研办公室 联系电话：010-11112222",
            "科研处",
            "2026年4月28日",
        ],
        "kind": "有多个材料要求的申报通知",
        "focus": "四项材料名称提取、四步流程、材料清单生成",
    },
    "d05_招聘公告.txt": {
        "title": "某大学2026年公开招聘工作人员公告",
        "body": [
            "一、招聘岗位",
            "行政管理岗、实验技术岗。",
            "二、应聘条件",
            "具有硕士研究生及以上学历，符合岗位要求。",
            "三、报名时间",
            "2026年5月6日至2026年5月20日",
            "四、报名方式",
            "1. 填写应聘报名表。",
            "2. 将个人简历、学历学位证书复印件、身份证复印件发送至人事处邮箱。",
            "3. 登录招聘系统确认报名信息。",
            "五、注意事项",
            "应聘材料恕不退还，请自留备份。",
            "联系人：人事处 联系电话：010-33334444",
            "人事处",
            "2026年4月30日",
        ],
        "kind": "招聘公告",
        "focus": "招聘招录类型、报名区间、简历与证书材料",
    },
    "d06_日期模糊通知.txt": {
        "title": "关于2026年春季学期资助申请的通知",
        "body": [
            "全体在校学生：",
            "一、申请对象",
            "家庭经济困难的在校学生均可申请。",
            "二、报名时间",
            "报名时间另行通知，请关注学院通知。",
            "三、截止时间",
            "截止时间为5月20日。",
            "四、申请材料",
            "《资助申请表》、家庭情况说明。",
            "五、申请方式",
            "1. 填写资助申请表。",
            "2. 将申请表发送至学院邮箱。",
            "3. 联系辅导员确认提交结果。",
            "六、注意事项",
            "请如实填写家庭情况，不得弄虚作假。",
            "联系人：学生处 联系电话：010-55556666",
            "学生处",
            "2026年4月15日",
        ],
        "kind": "日期缺失或表达模糊的通知",
        "focus": "缺失报名区间、仅“5月20日”缺年份，应提示待核实",
    },
    "d07_多流程办事通知.docx": {
        "title": "关于办理2026年校园一卡通补办的通知",
        "body": [
            "全体师生：",
            "一、办理时间",
            "2026年9月1日至2026年9月30日",
            "二、办理条件",
            "校园一卡通遗失或损坏的师生均可申请补办。",
            "三、办理材料",
            "《一卡通补办申请表》、身份证复印件。",
            "四、办理流程",
            "1. 登录校园卡系统填写补办申请表。",
            "2. 打印申请表并签字。",
            "3. 携带申请表和身份证复印件前往校园卡服务中心。",
            "4. 缴纳补办费用并领取新卡。",
            "五、注意事项",
            "补办期间原卡停止使用，请提前安排。",
            "联系人：校园卡服务中心 联系电话：010-77778888",
            "后勤服务中心",
            "2026年8月25日",
        ],
        "kind": "含多个流程步骤的办事通知",
        "focus": "四步流程完整性、任务生成来源",
    },
    "d08_无材料要求通知.txt": {
        "title": "关于举办2026年秋季运动会的通知",
        "body": [
            "全体在校学生：",
            "一、活动时间",
            "2026年10月15日至2026年10月17日",
            "二、参与对象",
            "全体在校学生均可报名参加。",
            "三、报名方式",
            "1. 登录体育系统填写报名信息。",
            "2. 前往体育部办公室确认参赛项目。",
            "四、注意事项",
            "请根据身体状况选择参赛项目。",
            "联系人：体育部 联系电话：010-99990000",
            "体育运动委员会",
            "2026年9月20日",
        ],
        "kind": "没有明确材料要求的通知",
        "focus": "材料清单为空时系统应给出明确提示，不臆造材料",
    },
    "d09_标题含材料关键词通知.txt": {
        "title": "关于提交2026年国家奖学金材料的通知",
        "body": [
            "全体本科生：",
            "一、申请对象",
            "符合条件的全日制在校本科生均可申请。",
            "二、提交时间",
            "2026年9月10日至2026年9月25日",
            "三、提交材料",
            "《国家奖学金申请表》、成绩单、获奖证书复印件。",
            "四、提交方式",
            "1. 填写国家奖学金申请表。",
            "2. 将申请表和成绩单交至学院学生工作办公室。",
            "3. 登录学生资助系统上传电子版。",
            "五、注意事项",
            "标题中的“材料”不是材料名称，请按材料清单逐项准备。",
            "联系人：学生资助中心 联系电话：010-12121212",
            "学生工作处",
            "2026年9月1日",
        ],
        "kind": "标题包含“关于提交材料的通知”的文档",
        "focus": "标题中的“材料”不得被误提取为材料名称",
    },
    "d10_信息冲突通知.docx": {
        "title": "关于2026年优秀学生评选工作的通知",
        "body": [
            "全体在校学生：",
            "一、评选对象",
            "全日制在校本科生、研究生均可申请参与。",
            "二、报名时间",
            "2026年5月1日至2026年5月10日",
            "三、材料要求",
            "《优秀学生申请表》、成绩单复印件、获奖证明。",
            "四、报名方式",
            "1. 填写优秀学生申请表。",
            "2. 将申请表和成绩单交至学院办公室。",
            "五、注意事项",
            "截止时间：2026年6月20日，逾期不予受理。",
            "联系人：学院办公室 联系电话：010-13131313",
            "学生工作处",
            "2026年4月20日",
        ],
        "kind": "内容存在冲突或信息不完整的文档",
        "focus": "同一文档出现两个截止日期，系统需提示冲突/取最晚并待核实",
    },
    "d11_空流程通知.txt": {
        "title": "关于举办2026年学术讲座的通知",
        "body": [
            "全体师生：",
            "一、活动时间",
            "2026年11月20日",
            "二、活动地点",
            "图书馆报告厅。",
            "三、参与对象",
            "全体师生均可参加。",
            "四、注意事项",
            "请提前十分钟入场。",
            "联系人：图书馆 联系电话：010-14141414",
            "图书馆",
            "2026年11月10日",
        ],
        "kind": "空流程边界文档",
        "focus": "无办理流程时任务生成应为 0，并给出明确提示",
    },
    "d12_非法日期通知.txt": {
        "title": "关于2026年2月30日事项申报的通知",
        "body": [
            "全体在校学生：",
            "一、申报时间",
            "2026年2月30日",
            "二、申报材料",
            "《事项申请表》。",
            "三、申报方式",
            "1. 填写事项申请表。",
            "2. 将申请表交至行政办公室。",
            "四、注意事项",
            "请核实日期后按时提交。",
            "联系人：行政办公室 联系电话：010-15151515",
            "行政办公室",
            "2026年2月1日",
        ],
        "kind": "非法日期边界文档",
        "focus": "2026-02-30 不是真实日历日期，风险层应提示日期待核实",
    },
}


def write_txt(path: Path, title: str, body: list[str]) -> None:
    content = "\n".join([title, "", *body, "", PREFIX + "本文档仅用于 TaskRadar 端到端测试。"])
    path.write_text(content, encoding="utf-8")


def write_docx(path: Path, title: str, body: list[str]) -> None:
    document = Document()
    document.add_heading(title, level=1)
    for line in body:
        document.add_paragraph(line)
    document.add_paragraph(PREFIX + "本文档仅用于 TaskRadar 端到端测试。")
    document.save(path)


def write_pdf(path: Path, title: str, body: list[str]) -> bool:
    try:
        import fitz
    except Exception:
        return False
    try:
        pdf = fitz.open()
        page = pdf.new_page()
        y = 60
        lines = [title, "", *body, "", PREFIX + "本文档仅用于 TaskRadar 端到端测试。"]
        for line in lines:
            if y > 780:
                page = pdf.new_page()
                y = 60
            page.insert_text((50, y), line, fontname="china-s", fontsize=10.5)
            y += 16
        pdf.save(path)
        pdf.close()
        return True
    except Exception:
        return False


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    MATERIALS.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    manifest = []
    for filename, spec in DOC_CONTENTS.items():
        path = DOCS / filename
        suffix = path.suffix.lower()
        if suffix == ".docx":
            write_docx(path, spec["title"], spec["body"])
            created = True
        elif suffix == ".pdf":
            created = write_pdf(path, spec["title"], spec["body"])
        else:
            write_txt(path, spec["title"], spec["body"])
            created = True
        manifest.append(
            {
                "file": filename,
                "format": suffix.lstrip("."),
                "kind": spec["kind"],
                "focus": spec["focus"],
                "title_in_document": spec["title"],
                "created": created,
                "source": "人工编写的测试用途模拟文档，非真实官方文件",
            }
        )

    # 单独生成一个真实 PDF 版本（用于格式覆盖），若 CJK 字体不可用则记录失败
    pdf_source = DOCS / "d03_跨年度申报通知.txt"
    pdf_target = DOCS / "d03_跨年度申报通知.pdf"
    pdf_created = write_pdf(
        pdf_target,
        DOC_CONTENTS["d03_跨年度申报通知.txt"]["title"],
        DOC_CONTENTS["d03_跨年度申报通知.txt"]["body"],
    )
    manifest.append(
        {
            "file": pdf_target.name,
            "format": "pdf",
            "kind": "跨年度日期通知（PDF 格式副本）",
            "focus": "PDF 文本提取与跨年度区间解析",
            "title_in_document": DOC_CONTENTS["d03_跨年度申报通知.txt"]["title"],
            "created": pdf_created,
            "source": "由测试脚本生成的模拟 PDF，非真实官方文件",
        }
    )

    # 材料上传样本
    (MATERIALS / "material_ok.txt").write_text(
        "测试用途材料样本\n姓名：测试学生\n学号：TEST0001\n身份证号：TEST-ID-0001\n"
        "联系电话：13800000000\n签字：测试用途\n盖章：测试用途\n日期：2026年5月1日\n",
        encoding="utf-8",
    )
    (MATERIALS / "material_keyword_mismatch.txt").write_text(
        "测试用途材料样本\n本文件仅包含无关的课程安排说明，用于验证关键词不匹配场景。\n",
        encoding="utf-8",
    )
    (MATERIALS / "material_suspicious.txt").write_text(
        "测试用途材料样本\n姓名：测试学生\n该证明材料已过期，原证件已失效。\n",
        encoding="utf-8",
    )
    (MATERIALS / "corrupt.docx").write_bytes(b"this is not a real docx file, test only")
    (MATERIALS / "wrong_format.xlsx").write_bytes(b"PK\x03\x04 fake xlsx test only")
    (MATERIALS / "empty.txt").write_bytes(b"")
    (MATERIALS / "oversized.txt").write_bytes(b"A" * (10 * 1024 * 1024 + 128))

    (EVIDENCE / "document_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
