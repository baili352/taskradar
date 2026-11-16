"""规则提取服务：从真实文档文本中抽取事项要素，并提供原文证据。

第三阶段不调用大模型。所有结果均来自原文的正则/关键词/章节识别，
找不到依据的信息统一标记为 pending（待核实），不做推测性补全。

本版重点修复通知类文档的常见问题：
- 参赛对象、报名方式、报名时间等章节的识别；
- 从普通正文段落中提取材料与流程；
- 日期区间的起止识别与跨段落年份补全；
- 事项类型覆盖活动赛事、招聘招录等；
- 注意事项中过滤联系人、组织单位、落款、附件等元信息。
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.services.documents.types import ExtractedDocument, Segment
from app.services.extraction.sections import (
    SectionContent,
    collect_sections,
    detect_metadata_line,
    match_heading,
    strip_numbering,
)

SNIPPET_LIMIT = 180
MAX_EVIDENCE = 5
MAX_MATERIALS = 40
MAX_STEPS = 30
MAX_NOTES = 20

DATE_CORE = (
    r"(?<!\d)\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日(?!\d)"
    r"|(?<!\d)\d{4}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,2}(?!\d)"
    r"|(?<!\d)\d{1,2}\s*月\s*\d{1,2}\s*日(?!\d)"
)
DATE_PATTERN = re.compile(DATE_CORE)
DATE_RANGE_PATTERN = re.compile(
    rf"({DATE_CORE})\s*(?:至|到|—|–|－|~|～|-)\s*({DATE_CORE})"
)
YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})\s*年|(?<!\d)(20\d{2})\s*[-/.]\s*\d{1,2}")

DEADLINE_HINTS = (
    "截止",
    "截至",
    "之前",
    "前提交",
    "前完成",
    "前办理",
    "前报送",
    "前发送",
    "前上传",
    "受理时间",
    "申报时间",
    "报名时间",
    "办理时间",
    "办理期限",
    "有效期",
)

SIGNUP_HINTS = ("报名", "申请", "参与", "参赛", "提交", "投稿", "报送", "投递", "登记")
ACTIVITY_TIME_HINTS = (
    "比赛时间",
    "活动时间",
    "考试时间",
    "面试时间",
    "笔试时间",
    "培训时间",
    "演出时间",
    "会议时间",
    "活动日期",
    "比赛日期",
)

MATTER_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "活动赛事",
        (
            "大赛",
            "比赛",
            "竞赛",
            "选拔赛",
            "联赛",
            "锦标赛",
            "演出",
            "展演",
            "汇演",
            "征文",
            "征集",
            "评选",
            "运动会",
            "演讲",
            "朗诵",
            "诵读",
            "讲述",
            "话剧",
            "文艺",
            "晚会",
            "音乐会",
            "摄影",
            "书画",
            "挑战杯",
            "创新创业",
        ),
    ),
    (
        "招聘招录",
        (
            "招聘",
            "招录",
            "招募",
            "选聘",
            "选调",
            "人才引进",
            "校园招聘",
            "公开招聘",
            "应聘",
            "面试",
            "笔试",
            "录用",
        ),
    ),
    (
        "会议培训",
        ("会议", "论坛", "讲座", "培训", "研修", "研讨", "沙龙", "开班"),
    ),
    (
        "证件办理",
        ("身份证", "护照", "居住证", "驾驶证", "户口", "签证", "社保卡", "证件办理", "补办证件"),
    ),
    (
        "行政审批",
        ("行政许可", "审批", "备案", "核准", "登记", "资质", "许可证"),
    ),
    (
        "材料申报",
        ("申报", "补贴", "补助", "奖励", "资助", "认定", "扶持", "专项资金"),
    ),
)

_SPLIT_BY_NUMBER = re.compile(r"\s*(?:\d{1,2}\s*[、.．)）]|[（(]\s*\d{1,2}\s*[)）])\s*")
_SPLIT_BY_PUNCTUATION = re.compile(r"\s*[；;]\s*")
_LIST_FILLER = {"如下", "以下", "包括", "包含", "具体如下", "材料如下"}

_PURE_DATE = re.compile(r"^[二〇零一二三四五六七八九十百\d\s年月日\.\-/、（）()]+$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"1[3-9]\d{9}|0\d{2,3}-?\d{7,8}")

_META_TEXT = re.compile(
    r"^(?:联系人|联系方式|联系电话|咨询电话|咨询方式|报名咨询|联系部门|联系地址"
    r"|通讯地址|邮箱|电子邮箱|投稿邮箱|报名邮箱|咨询邮箱"
    r"|主办单位|承办单位|协办单位|指导单位|组织单位|组织机构|主办方|承办方|协办方"
    r"|附件|附录|相关附件)"
)

_GENERIC_MATERIALS = {
    "材料",
    "表格",
    "文档",
    "附件",
    "证明",
    "复印件",
    "扫描件",
    "原件",
    "报告",
    "视频",
    "照片",
    "作品",
    "截图",
    "报名",
    "申请",
}

# 标题式短语（如“关于提交材料的通知”）不是材料名称。
_MATERIAL_TITLE_PREFIXES = ("关于", "通知", "公告", "通告", "印发", "开展", "举办")
# 只有范围修饰的泛称（如“学生材料”“相关材料”）不足以构成具体材料名称。
_GENERIC_MATERIAL_MODIFIERS = {
    "相关",
    "所需",
    "以下",
    "上述",
    "各类",
    "有关",
    "全部",
    "其他",
    "学生",
    "教师",
    "教职工",
    "个人",
    "申请",
    "提交",
    "报送",
    "按",
}

MATERIAL_ACTIONS = (
    "填写",
    "提交",
    "上传",
    "发送",
    "准备",
    "携带",
    "下载",
    "打印",
    "附上",
    "提供",
    "报送",
    "递交",
    "投递",
    "交至",
    "提交至",
    "发送至",
    "录制",
    "拍摄",
    "扫描",
)

MATERIAL_NOUN_PATTERN = re.compile(
    r"(?:^|[，,。；;：:、\s]|填写|提交|上传|发送|准备|携带|下载|打印|附上|提供|报送"
    r"|递交|投递|交至|将|对|含|包括)"
    r"([\u4e00-\u9fa5A-Za-z0-9（）()《》〈〉·\-]{0,10}"
    r"(?:报名表|申请表|推荐表|登记表|汇总表|审批表|申报表|承诺书|申请书|委托书"
    r"|心得体会|心得|记录|简历|作品|视频|音频|照片|截图|方案|计划书|申报书|报告"
    r"|成绩单|户口簿|证书|证件"
    r"|PPT|ppt|Word|word|PDF|pdf"
    r"|证明|复印件|扫描件|原件|材料|表格|文档|附件))"
)

# 书名号内通常是正式材料名称，应优先保留完整名称，而非只取「报名表」等后缀。
QUOTED_MATERIAL_PATTERN = re.compile(
    r"《([^《》\r\n]{1,80}?(?:报名表|申请表|推荐表|登记表|汇总表|审批表|申报表"
    r"|承诺书|申请书|委托书|心得体会|简历|方案|计划书|报告|证书|证件|证明"
    r"|材料|表格|文档))》"
)

_MATERIAL_LEAD = re.compile(
    r"^(?:请|将|并|于|及时|按时|提前|自行|认真|如实|亲自|对"
    r"|应提交|应提供|需提交|需提供|须提交|须提供|应当提交|应当提供"
    r"|填写|提交|上传|发送|准备|携带|下载|打印|附上|提供|报送|递交|投递"
    r"|提交至|发送至|送至|交至|相关|电子版|纸质版|本人|一份|1份)"
)
_MATERIAL_SPLIT = re.compile(r"(?:并|且|以及|及|和|对|组织|评选)")
_MATERIAL_TAIL = re.compile(r"(?:予以|进行|参加|参与|提交|发送|报送|上传|用于|作为|等).*$")
_MATERIAL_QUANTITY = re.compile(r"^(?:\d+|[一二三四五六七八九十]+)(?:篇|份|个|张|页|项|套|人)")

STEP_ACTIONS = (
    "填写",
    "提交",
    "上传",
    "发送",
    "加入",
    "扫码",
    "扫描",
    "登录",
    "注册",
    "下载",
    "打印",
    "缴费",
    "支付",
    "报名",
    "参加",
    "参与",
    "联系",
    "递交",
    "报送",
    "投递",
    "交至",
    "送至",
    "送交",
    "领取",
    "确认",
    "关注",
    "前往",
    "携带",
    "准备",
    "录制",
    "拍摄",
    "完成",
)

STEP_CONNECTOR = re.compile(r"[，,；;]\s*(?:然后|接着|随后|之后|最后|同时|并且|并|再|另)")
STEP_NUMBER = re.compile(
    r"(?:^|\s|。|；|;)\s*(?:\d{1,2}[、.．)）]|[（(]\d{1,2}[)）]|[一二三四五六七八九十]+[、.．])"
)
STEP_SENTENCE = re.compile(r"[。；;]\s*")

QUALIFICATION_PATTERNS = (
    re.compile(r"(?:全体|全校|全院|全系)[^。；;]{0,20}(?:学生|师生|教师|教职工|研究生|本科生|同学)"),
    re.compile(r"[^。；;]{0,20}(?:在校学生|在校生|全日制学生)[^。；;]{0,20}"),
    re.compile(r"(?:凡|符合)[^。；;]{0,60}(?:均可|皆可|可)[^。；;]{0,20}(?:报名|参加|参与|申请|投稿)"),
    re.compile(r"[^。；;]{0,20}(?:均可|皆可)(?:报名|参加|参与|申请|投稿)"),
    re.compile(r"(?:报名|参赛|参与|申请)(?:对象|条件|资格)[：:][^。；;]{2,80}"),
)

TEAM_PATTERN = re.compile(
    r"(?:(?:每队|每组|每支队伍|每个团队|每个参赛队|每支参赛队)[^。；;，,]{0,12}?"
    r"|(?:队伍|团队|参赛队伍)?人数(?:限|限制|为|：|:)?\s*)"
    r"\d{1,2}\s*[-~—至到]\s*\d{1,2}\s*人"
    r"|(?:每队|每组|每支队伍|每个团队)\s*\d{1,2}\s*人"
    r"|\d{1,2}\s*[-~—至到]\s*\d{1,2}\s*人(?:组成|组队|为队)"
    r"|人数(?:不超过|不得超过|上限为?)\s*\d{1,2}\s*人"
)
TEAM_RANGE_PATTERN = re.compile(r"\d{1,2}\s*[-~—至到]\s*\d{1,2}\s*人")


def _team_value(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    match = TEAM_RANGE_PATTERN.search(compact)
    if match:
        return match.group(0)
    return re.sub(r"^(?:队伍|团队|参赛队伍)?人数", "", compact)


@dataclass
class DateHit:
    segment: Segment
    index: int
    pos: int
    year: int | None
    month: int
    day: int
    year_source: str | None = None
    year_evidence: Segment | None = None


@dataclass
class DateRange:
    segment: Segment
    index: int
    pos: int
    end_pos: int
    start_year: int | None
    start_month: int
    start_day: int
    end_year: int | None
    end_month: int
    end_day: int
    year_source: str | None = None
    year_evidence: Segment | None = None


def snippet(text: str, limit: int = SNIPPET_LIMIT) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= limit else f"{cleaned[:limit]}…"


def build_evidence(
    segment: Segment,
    limit: int = SNIPPET_LIMIT,
    excerpt: str | None = None,
) -> dict:
    return {
        "text": snippet(excerpt or segment.text, limit),
        "location": segment.location or "原文",
        "page": segment.page,
        "paragraph": segment.paragraph,
    }


def make_field(
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


def split_list_items(text: str) -> list[str]:
    """把一段正文拆成条目，兼容「1. xx 2. yy」「甲、乙、丙」「甲；乙」。"""
    text = text.strip()
    if not text:
        return []

    number_matches = list(_SPLIT_BY_NUMBER.finditer(text))
    if len(number_matches) >= 2 or (number_matches and number_matches[0].start() == 0):
        pieces = _SPLIT_BY_NUMBER.split(text)
    elif "；" in text or ";" in text:
        pieces = _SPLIT_BY_PUNCTUATION.split(text)
    elif "、" in text and len(text) <= 200 and text.count("、") >= 1:
        pieces = text.split("、")
    else:
        pieces = [text]

    items: list[str] = []
    for piece in pieces:
        cleaned = piece.strip(" 　\t。；;，,、：:")
        cleaned = re.sub(r"^(?:包括|包含|材料如下|具体如下)[：:]?", "", cleaned).strip()
        if len(cleaned) < 2 or cleaned in _LIST_FILLER:
            continue
        items.append(cleaned)
    return items


def _segment_section_map(sections: dict[str, list[SectionContent]]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for name, contents in sections.items():
        for content in contents:
            mapping[id(content.segment)] = name
    return mapping


def _parse_date(raw: str) -> tuple[int | None, int, int] | None:
    text = re.sub(r"\s+", "", raw)
    match = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日(?!\d)", text)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    match = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    match = re.match(r"(\d{1,2})月(\d{1,2})日", text)
    if match:
        return None, int(match.group(1)), int(match.group(2))
    return None


def _format_date(year: int | None, month: int, day: int) -> str:
    if year:
        return f"{year}年{month}月{day}日"
    return f"{month}月{day}日"


_CROSS_YEAR_MAX_DAYS = 180


def _context_year(
    segments: list[Segment],
    index: int,
    before_pos: int,
    month: int,
    day: int,
    lookback: int = 5,
) -> tuple[int | None, Segment | None]:
    """寻找可用于补全缺少年份日期的上下文年份。

    仅当上下文年份唯一、且能按时间顺序唯一确定目标年份时才补全：
    - 目标日期不早于上下文日期时沿用该年份；
    - 目标日期早于上下文日期、顺延一年后间隔不超过半年时补为次年；
    - 上下文存在多个不同年份，或顺延后间隔过大时返回 None，
      由下游标记为日期待核实，不做推测性补全。
    """
    window: list[tuple[Segment, str]] = [
        (segments[index], segments[index].text[:before_pos])
    ]
    for back in range(1, lookback + 1):
        if index - back < 0:
            break
        segment = segments[index - back]
        window.append((segment, segment.text))

    years: set[int] = set()
    for _segment, text in window:
        for first, second in YEAR_PATTERN.findall(text):
            years.add(int(first or second))
    # 没有年份，或存在多个冲突年份，都无法可靠判断所属年份。
    if len(years) != 1:
        return None, None

    year = next(iter(years))
    reference: tuple[date, Segment] | None = None
    for segment, text in window:
        for match in reversed(list(DATE_PATTERN.finditer(text))):
            parsed = _parse_date(match.group(0))
            if parsed is None or parsed[0] is None:
                continue
            try:
                reference = (date(parsed[0], parsed[1], parsed[2]), segment)
            except ValueError:
                continue
            break
        if reference is not None:
            break

    if reference is None:
        # 上下文只有年份、没有可比较的完整日期时，沿用该年份。
        return year, window[0][0]

    reference_day, evidence = reference
    try:
        same_year = date(year, month, day)
    except ValueError:
        return None, None
    if same_year >= reference_day:
        return year, evidence

    try:
        next_year = date(year + 1, month, day)
    except ValueError:
        return None, None
    if (next_year - reference_day).days <= _CROSS_YEAR_MAX_DAYS:
        return year + 1, evidence
    return None, None


def _collect_date_ranges(document: ExtractedDocument) -> list[DateRange]:
    ranges: list[DateRange] = []
    segments = document.segments

    for index, segment in enumerate(segments):
        for match in DATE_RANGE_PATTERN.finditer(segment.text):
            start = _parse_date(match.group(1))
            end = _parse_date(match.group(2))
            if not start or not end:
                continue

            start_year, start_month, start_day = start
            end_year, end_month, end_day = end
            year_source: str | None = None
            year_evidence: Segment | None = None

            if start_year is not None and end_year is None:
                end_year = start_year
                year_source = "range"
                year_evidence = segment
            elif start_year is None and end_year is not None:
                start_year = end_year
                year_source = "range"
                year_evidence = segment
            elif start_year is None and end_year is None:
                start_resolved, evidence = _context_year(
                    segments, index, match.start(), start_month, start_day
                )
                end_resolved, end_evidence = _context_year(
                    segments, index, match.start(), end_month, end_day
                )
                if start_resolved is not None or end_resolved is not None:
                    start_year = start_resolved
                    end_year = end_resolved
                    year_source = "context"
                    year_evidence = evidence or end_evidence

            ranges.append(
                DateRange(
                    segment=segment,
                    index=index,
                    pos=match.start(),
                    end_pos=match.end(),
                    start_year=start_year,
                    start_month=start_month,
                    start_day=start_day,
                    end_year=end_year,
                    end_month=end_month,
                    end_day=end_day,
                    year_source=year_source,
                    year_evidence=year_evidence,
                )
            )

    return ranges


def _collect_single_dates(
    document: ExtractedDocument,
    ranges: list[DateRange],
) -> list[DateHit]:
    covered: dict[int, list[tuple[int, int]]] = {}
    for item in ranges:
        covered.setdefault(item.index, []).append((item.pos, item.end_pos))

    hits: list[DateHit] = []
    for index, segment in enumerate(document.segments):
        for match in DATE_PATTERN.finditer(segment.text):
            spans = covered.get(index, [])
            if any(start <= match.start() < end for start, end in spans):
                continue
            parsed = _parse_date(match.group(0))
            if not parsed:
                continue
            year, month, day = parsed
            year_source: str | None = None
            year_evidence: Segment | None = None
            if year is None:
                year, year_evidence = _context_year(
                    document.segments, index, match.start(), month, day
                )
                if year is not None:
                    year_source = "context"
            hits.append(
                DateHit(
                    segment=segment,
                    index=index,
                    pos=match.start(),
                    year=year,
                    month=month,
                    day=day,
                    year_source=year_source,
                    year_evidence=year_evidence,
                )
            )

    return hits


def _range_score(item: DateRange, document: ExtractedDocument, section_map: dict[int, str]) -> int:
    context = item.segment.text
    if item.index > 0:
        context = f"{document.segments[item.index - 1].text} {context}"

    score = 0
    if any(hint in context for hint in SIGNUP_HINTS):
        score += 4
    if any(hint in context for hint in ACTIVITY_TIME_HINTS):
        score -= 4
    section = section_map.get(id(item.segment))
    if section == "schedule":
        score += 2
    elif section == "process":
        score += 1
    if any(hint in item.segment.text for hint in DEADLINE_HINTS):
        score += 1
    return score


def _pick_signup_range(
    ranges: list[DateRange],
    document: ExtractedDocument,
    section_map: dict[int, str],
) -> tuple[DateRange | None, int]:
    if not ranges:
        return None, 0
    scored = [(_range_score(item, document, section_map), item) for item in ranges]
    score, best = max(scored, key=lambda pair: pair[0])
    if score >= 2:
        return best, score
    return None, score


def _date_note(item: DateRange | DateHit, label: str) -> str | None:
    if isinstance(item, DateRange):
        year_missing = item.start_year is None or item.end_year is None
        year_source = item.year_source
        year_evidence = item.year_evidence
    else:
        year_missing = item.year is None
        year_source = item.year_source
        year_evidence = item.year_evidence

    if year_missing:
        return f"原文未标注{label}的年份，请核实具体年份。"
    if year_source == "context" and year_evidence is not None:
        return (
            f"年份依据原文 {year_evidence.location or '前文'}「{snippet(year_evidence.text, 60)}」补全。"
        )
    if year_source == "range":
        return f"{label}年份沿用同一日期区间内的明确年份。"
    return None


_TITLE_PATTERN = re.compile(
    r"关于.+的(?:通知|公告|通告|办法|规定|意见|指南|方案|细则|须知|安排)"
)
_TITLE_END_PATTERN = re.compile(r"(?:通知|公告|通告|办法|规定|意见|指南|方案|细则|须知)$")


def _locate_title_segments(document: ExtractedDocument) -> list[Segment]:
    """按标题特征定位标题片段；标题中的“材料”等字样不是材料名称。"""
    head = document.segments[:5]
    for count in range(1, 4):
        if len(head) < count:
            break
        parts = head[:count]
        text = "".join(part.text.strip() for part in parts)
        if not 4 <= len(text) <= 100:
            continue
        if _TITLE_PATTERN.search(text) or (count > 1 and _TITLE_END_PATTERN.search(text)):
            return parts
    return []


def _extract_title(document: ExtractedDocument) -> dict:
    """标题可能被 WORD 拆成多个段落，按顺序拼接后再判断。"""
    parts = _locate_title_segments(document)
    if parts:
        return make_field(
            "title",
            "事项名称",
            "".join(part.text.strip() for part in parts),
            "found",
            [build_evidence(part) for part in parts],
        )

    for segment in document.segments:
        text = segment.text.strip()
        if 3 <= len(text) <= 80 and not match_heading(text):
            return make_field("title", "事项名称", text, "found", [build_evidence(segment)])

    stem = Path(document.filename).stem
    return make_field(
        "title",
        "事项名称",
        stem,
        "pending",
        note="原文中未找到明确标题，当前名称取自文件名，请核实。",
    )


def _extract_matter_type(document: ExtractedDocument, title: str | None = None) -> dict:
    if title:
        for type_name, keywords in MATTER_TYPE_RULES:
            for keyword in keywords:
                if keyword in title:
                    return make_field(
                        "matter_type",
                        "事项类型",
                        type_name,
                        "found",
                        [build_evidence(document.segments[0])],
                        note=f"依据标题关键词「{keyword}」判断，仅供参考。",
                    )

    for segment in document.segments:
        text = segment.text
        for type_name, keywords in MATTER_TYPE_RULES:
            for keyword in keywords:
                if keyword in text:
                    return make_field(
                        "matter_type",
                        "事项类型",
                        type_name,
                        "found",
                        [build_evidence(segment)],
                        note=f"依据原文关键词「{keyword}」判断，仅供参考。",
                    )

    return make_field(
        "matter_type",
        "事项类型",
        None,
        "pending",
        note="原文未出现明确的事项类型关键词，无法判断，请核实。",
    )


def _is_metadata_text(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return True
    if _META_TEXT.match(compact):
        return True
    if detect_metadata_line(compact):
        return True
    if _PURE_DATE.fullmatch(re.sub(r"\s+", "", compact)):
        return True
    if _EMAIL.search(compact) or _PHONE.search(compact):
        # 仅当去掉邮箱/电话后只剩联系类词时，才视为纯联系方式
        stripped = _PHONE.sub("", _EMAIL.sub("", compact))
        stripped = re.sub(r"[\s:：,，。；;、\-—（）()]", "", stripped)
        if len(stripped) <= 8 and any(
            word in stripped for word in ("联系", "咨询", "电话", "邮箱", "报名", "投稿")
        ):
            return True
    return False


def _qualification_line(text: str) -> str:
    compact = re.sub(r"\s+", "", text).strip(" 　，,。；;：:")
    team = TEAM_PATTERN.search(compact)
    if team:
        return f"队伍人数：{_team_value(team.group(0))}"
    if re.search(
        r"(全体|全校|全院|在校|师生|学生|教师|教职工|年级|专业|本科生|研究生|同学)",
        compact,
    ):
        return f"参与对象：{compact}"
    if re.search(r"(条件|资格|具备|符合|须|应当|要求|具有|年龄|学历)", compact):
        return f"申请条件：{compact}"
    return compact


def _extract_qualification(
    sections: dict[str, list[SectionContent]],
    document: ExtractedDocument,
) -> dict:
    lines: list[str] = []
    evidence: list[dict] = []
    evidence_keys: set[int] = set()

    def add_evidence(segment: Segment, excerpt: str | None = None) -> None:
        if id(segment) in evidence_keys or len(evidence) >= MAX_EVIDENCE:
            return
        evidence_keys.add(id(segment))
        evidence.append(build_evidence(segment, excerpt=excerpt))

    for content in sections.get("qualification") or []:
        for piece in re.split(r"[。；;\n]", content.text):
            piece = strip_numbering(piece).strip(" 　，,、：:")
            if len(piece) < 2 or _is_metadata_text(piece):
                continue
            lines.append(_qualification_line(piece))
        add_evidence(content.segment)

    if not lines:
        for segment in document.segments:
            for sentence in re.split(r"[。；;\n]", segment.text):
                sentence = sentence.strip(" 　，,、：:")
                if len(sentence) < 6:
                    continue
                if any(pattern.search(sentence) for pattern in QUALIFICATION_PATTERNS):
                    lines.append(_qualification_line(sentence))
                    add_evidence(segment, excerpt=sentence)
                    break

    for segment in document.segments:
        if any(line.startswith("队伍人数：") for line in lines):
            break
        match = TEAM_PATTERN.search(re.sub(r"\s+", "", segment.text))
        if not match:
            continue
        team = f"队伍人数：{_team_value(match.group(0))}"
        if team not in lines:
            lines.append(team)
            add_evidence(segment)
        break

    lines = [line for line in dict.fromkeys(lines) if line]
    if not lines:
        return make_field(
            "qualification",
            "申请资格",
            None,
            "pending",
            note="未在原文中找到「参赛对象 / 参与对象 / 申请条件」等明确表述，请核实。",
        )

    return make_field(
        "qualification",
        "申请资格",
        snippet("；".join(lines), 400),
        "found",
        evidence,
        note="以上内容直接摘自原文对应章节或正文句子。",
    )


def _extract_registration_start(signup_range: DateRange | None) -> dict:
    if signup_range is None:
        return make_field(
            "registration_start",
            "报名开始日期",
            None,
            "pending",
            note="原文未找到明确的报名日期区间，无法确认报名开始日期，请核实。",
        )

    value = _format_date(
        signup_range.start_year,
        signup_range.start_month,
        signup_range.start_day,
    )
    evidence = [build_evidence(signup_range.segment)]
    if (
        signup_range.year_evidence is not None
        and signup_range.year_evidence is not signup_range.segment
    ):
        evidence.append(build_evidence(signup_range.year_evidence))

    return make_field(
        "registration_start",
        "报名开始日期",
        value,
        "found",
        evidence,
        note=_date_note(signup_range, "报名开始日期"),
    )


def _is_deadline_context(text: str) -> bool:
    if any(hint in text for hint in DEADLINE_HINTS):
        return True
    return bool(re.search(r"\d{1,2}\s*月\s*\d{1,2}\s*日\s*(?:前|之前|以前)", text))


def _extract_deadline(
    singles: list[DateHit],
    signup_range: DateRange | None,
    section_map: dict[int, str] | None = None,
) -> dict:
    if signup_range is not None:
        evidence = [build_evidence(signup_range.segment)]
        if (
            signup_range.year_evidence is not None
            and signup_range.year_evidence is not signup_range.segment
        ):
            evidence.append(build_evidence(signup_range.year_evidence))
        value = _format_date(signup_range.end_year, signup_range.end_month, signup_range.end_day)
        note = _date_note(signup_range, "截止日期")

        # 报名区间之外若还有明确的截止日期，提示冲突；默认值仍取区间结束日。
        section_map = section_map or {}
        distinct: list[str] = []
        conflict_hits: list[DateHit] = []
        for hit in singles:
            if section_map.get(id(hit.segment)) == "signature":
                continue
            if not _is_deadline_context(hit.segment.text):
                continue
            hit_value = _format_date(hit.year, hit.month, hit.day)
            if hit_value == value or hit_value in distinct:
                continue
            distinct.append(hit_value)
            conflict_hits.append(hit)
        if distinct:
            note = (
                f"原文出现多个截止日期（{'、'.join([value, *distinct])}），"
                f"已取报名区间结束日 {value}，请核实。"
            )
            for hit in conflict_hits:
                item = build_evidence(hit.segment)
                if item not in evidence and len(evidence) < MAX_EVIDENCE:
                    evidence.append(item)

        return make_field(
            "deadline",
            "截止日期",
            value,
            "found",
            evidence,
            note=note,
        )

    section_map = section_map or {}
    candidates = [
        hit for hit in singles if section_map.get(id(hit.segment)) != "signature"
    ]

    if not candidates:
        return make_field(
            "deadline",
            "截止日期",
            None,
            "pending",
            note="原文中未找到日期信息，无法确定截止日期，请向办理机构核实。",
        )

    hinted = [hit for hit in candidates if _is_deadline_context(hit.segment.text)]
    pool = hinted or candidates
    chosen = max(pool, key=lambda hit: (hit.year or 0, hit.month, hit.day))

    note = _date_note(chosen, "截止日期")
    if not hinted:
        note = "原文出现日期，但未明确标注为截止日期，请核实。"

    evidence = [build_evidence(chosen.segment)]
    if hinted:
        distinct: list[str] = []
        for hit in hinted:
            value = _format_date(hit.year, hit.month, hit.day)
            if value not in distinct:
                distinct.append(value)
        if len(distinct) > 1:
            note = f"原文出现多个截止日期（{'、'.join(distinct)}），已取最晚日期，请核实。"
            for hit in hinted:
                item = build_evidence(hit.segment)
                if item not in evidence and len(evidence) < MAX_EVIDENCE:
                    evidence.append(item)

    return make_field(
        "deadline",
        "截止日期",
        _format_date(chosen.year, chosen.month, chosen.day),
        "found",
        evidence,
        note=note,
    )


def _clean_material_name(name: str) -> str:
    cleaned = name.strip()
    for _ in range(4):
        before = cleaned
        cleaned = cleaned.strip(" 　\t。，,；;：:、（）()《》【】\"'“”")
        cleaned = _MATERIAL_LEAD.sub("", cleaned)
        if cleaned == before:
            break
    # 「学院将组织评选并对优秀作品予以表彰」这类长前缀，取最后一个连接词后的名词
    cleaned = _MATERIAL_SPLIT.split(cleaned)[-1]
    cleaned = _MATERIAL_TAIL.sub("", cleaned)
    cleaned = _MATERIAL_QUANTITY.sub("", cleaned)
    return _MATERIAL_LEAD.sub("", cleaned).strip()


def _valid_material_name(name: str, max_length: int = 26) -> bool:
    if len(name) < 2 or len(name) > max_length:
        return False
    if name.startswith(_MATERIAL_TITLE_PREFIXES):
        # “关于提交材料的通知”等标题片段不是材料名称。
        return False
    for noun in ("材料", "表格", "文档", "附件"):
        if name.endswith(noun) and name[: -len(noun)] in _GENERIC_MATERIAL_MODIFIERS:
            # “学生材料”“相关材料”等泛称无法对应具体材料，交由人工核实。
            return False
    if name in _GENERIC_MATERIALS:
        return False
    if extract_pure_digits(name):
        return False
    if re.search(r"(时间|日期|截止|方式|地点|清单|要求)", name):
        return False
    if match_heading(name):
        return False
    if _is_metadata_text(name):
        return False
    return True


def extract_pure_digits(text: str) -> bool:
    return bool(re.fullmatch(r"[\d一二三四五六七八九十]+(?:份|个|张|页|项|人|次)?", text.strip()))


def _materials_from_text(
    text: str,
    require_action: bool,
) -> list[str]:
    results: list[str] = []
    for sentence in re.split(r"[。；;\n]", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        has_action = any(verb in sentence for verb in MATERIAL_ACTIONS)
        if require_action and not has_action:
            continue
        for match in QUOTED_MATERIAL_PATTERN.finditer(sentence):
            name = match.group(1).strip()
            if _valid_material_name(name, max_length=80):
                results.append(name)
        for match in MATERIAL_NOUN_PATTERN.finditer(sentence):
            name = _clean_material_name(match.group(1))
            if _valid_material_name(name):
                results.append(name)
    return results


def _table_material_name(row_text: str) -> str:
    for cell in row_text.split("|"):
        cell = cell.strip()
        if not cell or extract_pure_digits(cell):
            continue
        if cell in ("电子版", "纸质版", "原件", "复印件", "备注"):
            continue
        cleaned = _clean_material_name(cell)
        if _valid_material_name(cleaned):
            return cleaned
    return ""


def _extract_materials(
    sections: dict[str, list[SectionContent]],
    document: ExtractedDocument,
    section_map: dict[int, str],
    title_segments: list[Segment] | None = None,
) -> list[dict]:
    materials: list[dict] = []
    seen: set[str] = set()

    def add(name: str, segment: Segment) -> bool:
        key = re.sub(r"\s+", "", name)
        if not key or key in seen:
            return False
        item = {
            "name": name,
            "status": "found",
            "evidence": build_evidence(segment),
        }
        # 同一名称的简称与全称同时出现时，保留更具体的全称及其原文证据。
        for index, existing in enumerate(materials):
            existing_key = re.sub(r"\s+", "", existing["name"])
            if key in existing_key:
                return False
            if existing_key in key:
                seen.discard(existing_key)
                seen.add(key)
                materials[index] = item
                return len(materials) >= MAX_MATERIALS
        seen.add(key)
        materials.append(item)
        return len(materials) >= MAX_MATERIALS

    for content in sections.get("materials") or []:
        if content.segment.location.startswith("表格") and "|" in content.text:
            name = _table_material_name(content.text)
            if name and add(name, content.segment):
                return materials
            continue

        for item in split_list_items(content.text):
            names = _materials_from_text(item, require_action=False)
            if names:
                for name in names:
                    if add(name, content.segment):
                        return materials
                continue
            # 短条目（如「身份证原件」）直接作为材料名称
            name = _clean_material_name(item)
            if len(item) <= 20 and _valid_material_name(name):
                if add(name, content.segment):
                    return materials

    title_ids = {id(segment) for segment in title_segments or []}
    for segment in document.segments:
        if id(segment) in title_ids:
            continue
        section = section_map.get(id(segment))
        require_action = section not in ("materials",)
        for name in _materials_from_text(segment.text, require_action=require_action):
            if add(name, segment):
                return materials

    return materials


def split_steps(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    chunks: list[str] = []
    for numbered in STEP_NUMBER.split(f" {text}"):
        numbered = numbered.strip()
        if not numbered:
            continue
        chunks.extend(STEP_SENTENCE.split(numbered))

    steps: list[str] = []
    for chunk in chunks:
        for part in STEP_CONNECTOR.split(chunk):
            cleaned = part.strip(" 　，,。；;：:")
            if cleaned:
                steps.append(cleaned)
    return steps


def _valid_step(text: str) -> bool:
    compact = strip_numbering(text).strip(" 　，,。；;：:")
    if len(compact) < 3 or len(compact) > 200:
        return False
    if not re.search(r"[\u4e00-\u9fa5]", compact):
        return False
    if _is_metadata_text(compact):
        return False
    if _PURE_DATE.fullmatch(re.sub(r"\s+", "", compact)):
        return False
    if not any(verb in compact for verb in STEP_ACTIONS):
        return False
    return True


FALLBACK_STEP_ACTIONS = ("发送", "提交", "报送", "上传", "投递", "递交", "加入")
FALLBACK_STEP_CHANNELS = (
    "邮箱",
    "QQ",
    "qq",
    "群",
    "系统",
    "平台",
    "网站",
    "办公室",
    "学生处",
    "教务处",
)


def _extract_process(
    sections: dict[str, list[SectionContent]],
    document: ExtractedDocument | None = None,
    section_map: dict[int, str] | None = None,
) -> list[dict]:
    steps: list[dict] = []
    seen: set[str] = set()

    def add(text: str, segment: Segment) -> bool:
        key = re.sub(r"\s+", "", text)
        if key in seen:
            return False
        seen.add(key)
        steps.append(
            {
                "index": len(steps) + 1,
                "text": text,
                "evidence": build_evidence(segment, excerpt=text),
            }
        )
        return len(steps) >= MAX_STEPS

    for content in sections.get("process") or []:
        for item in split_steps(content.text):
            if not _valid_step(item):
                continue
            if add(item, content.segment):
                return steps

    if steps or document is None:
        return steps

    # 没有明确的报名/办理方式章节时，从正文中带提交渠道的句子补充步骤
    section_map = section_map or {}
    for segment in document.segments:
        if section_map.get(id(segment)) in ("signature", "contact"):
            continue
        for sentence in re.split(r"[。；;\n]", segment.text):
            sentence = strip_numbering(sentence).strip()
            if len(sentence) < 8:
                continue
            if not any(verb in sentence for verb in FALLBACK_STEP_ACTIONS):
                continue
            if not any(channel in sentence for channel in FALLBACK_STEP_CHANNELS):
                continue
            if not _valid_step(sentence):
                continue
            if add(sentence, segment):
                return steps
            if len(steps) >= 8:
                return steps

    return steps


def _extract_notes(sections: dict[str, list[SectionContent]]) -> list[dict]:
    notes: list[dict] = []
    seen: set[str] = set()

    for content in sections.get("notes") or []:
        text = strip_numbering(content.text).strip()
        if not text or _is_metadata_text(text):
            continue
        key = re.sub(r"\s+", "", text)
        if key in seen:
            continue
        seen.add(key)
        notes.append(
            {
                "text": snippet(text, 240),
                "evidence": build_evidence(content.segment, excerpt=text),
            }
        )
        if len(notes) >= MAX_NOTES:
            break

    return notes


def extract_document(document: ExtractedDocument) -> dict:
    """执行完整提取，返回可直接序列化的结构。"""
    sections = collect_sections(document.segments)
    section_map = _segment_section_map(sections)

    ranges = _collect_date_ranges(document)
    singles = _collect_single_dates(document, ranges)
    signup_range, _ = _pick_signup_range(ranges, document, section_map)

    qualification_field = _extract_qualification(sections, document)
    title_field = _extract_title(document)

    fields = [
        title_field,
        _extract_matter_type(document, title_field["value"]),
        qualification_field,
        _extract_registration_start(signup_range),
        _extract_deadline(singles, signup_range, section_map),
    ]

    materials = _extract_materials(
        sections, document, section_map, _locate_title_segments(document)
    )
    process = _extract_process(sections, document, section_map)
    notes = _extract_notes(sections)

    warnings: list[str] = []
    if qualification_field["status"] == "pending":
        warnings.append("未识别到「申请资格 / 参赛对象」的明确表述。")
    if not materials:
        warnings.append("未识别到材料要求，请核实原文是否包含材料清单或「填写/提交」类要求。")
    if not process:
        warnings.append("未识别到办理流程，请核实原文是否包含「报名方式 / 办理流程」等章节。")
    if not notes:
        warnings.append("未识别到注意事项，请核实原文是否包含「注意事项 / 温馨提示」章节。")

    return {
        "fields": fields,
        "materials": materials,
        "process": process,
        "notes": notes,
        "warnings": warnings,
    }
