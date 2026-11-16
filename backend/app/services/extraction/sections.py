"""按常见通知、赛事、招聘与办事指南标题，把文本片段归类到不同章节。

设计要点：
- 章节词表覆盖「参赛对象 / 报名方式 / 报名时间 / 联系方式 / 主办单位 / 附件」等
  通知类文档常见标题，避免正文被一路归入最后一个章节。
- 标题匹配采用「最长关键词优先」，并允许标题与正文同行（如表格中的
  「参赛对象 | 全体在校学生」）。
- 联系人、组织单位、附件、落款等属于元信息，识别后立即切换当前章节，
  不再继续计入「注意事项」。
"""

import re
from dataclasses import dataclass

from app.services.documents.types import Segment

SECTION_LABELS = {
    "qualification": "参与对象与申请条件",
    "materials": "所需材料",
    "process": "报名/办理流程",
    "schedule": "时间安排",
    "notes": "注意事项",
    "activity": "活动内容",
    "awards": "奖项与结果",
    "contact": "联系方式",
    "organization": "组织单位",
    "attachment": "附件",
    "signature": "落款",
}

# 顺序不代表优先级：匹配时统一按关键词长度倒序，优先命中更具体的标题。
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "qualification": (
        "申请条件",
        "申请资格",
        "办理条件",
        "受理条件",
        "申报条件",
        "资格条件",
        "适用对象",
        "适用条件",
        "申请对象",
        "申请范围",
        "参赛对象",
        "参赛资格",
        "参赛条件",
        "参赛范围",
        "参赛要求",
        "参与对象",
        "参与资格",
        "参与条件",
        "参与范围",
        "参与要求",
        "报名对象",
        "报名条件",
        "参加对象",
        "参加条件",
        "活动对象",
        "面向对象",
        "招募对象",
        "招聘对象",
        "招生对象",
        "应聘对象",
        "应聘条件",
        "应聘资格",
        "招聘条件",
        "任职要求",
        "岗位要求",
        "学历要求",
        "遴选对象",
        "遴选范围",
        "选拔对象",
        "选拔范围",
        "适用范围",
        "申报范围",
        "支持对象",
        "扶持对象",
        "补贴对象",
        "补助对象",
        "保障对象",
    ),
    "materials": (
        "申请材料",
        "所需材料",
        "所需文件",
        "材料清单",
        "申报材料",
        "提交材料",
        "需提交材料",
        "应提交材料",
        "需提供材料",
        "应提供材料",
        "办理材料",
        "材料要求",
        "报送材料",
        "报名材料",
        "材料提交",
        "提交要求",
    ),
    "process": (
        "办理流程",
        "办理程序",
        "办理步骤",
        "办理方式",
        "申请流程",
        "申请步骤",
        "申请方式",
        "申报流程",
        "申报方式",
        "操作流程",
        "受理流程",
        "办事流程",
        "报名流程",
        "报名步骤",
        "报名方式",
        "报名办法",
        "参与流程",
        "参与步骤",
        "参与方式",
        "参加方式",
        "参赛流程",
        "参赛方式",
        "投稿方式",
        "提交方式",
        "活动流程",
        "实施步骤",
        "工作步骤",
    ),
    "schedule": (
        "报名时间",
        "报名日期",
        "活动时间",
        "活动日期",
        "比赛时间",
        "比赛日期",
        "参赛时间",
        "投稿时间",
        "申报时间",
        "办理时间",
        "截止时间",
        "时间安排",
        "日程安排",
        "时间节点",
        "实施时间",
        "开展时间",
        "活动周期",
    ),
    "notes": (
        "注意事项",
        "温馨提示",
        "特别提示",
        "重要提示",
        "其他事项",
        "其他要求",
        "补充说明",
        "特别说明",
        "其他说明",
        "备注",
        "工作要求",
        "有关要求",
        "相关要求",
        "报名须知",
        "参赛须知",
        "活动须知",
        "须知",
    ),
    "activity": (
        "活动主题",
        "活动内容",
        "活动背景",
        "活动目的",
        "活动意义",
        "活动形式",
        "活动安排",
        "活动地点",
        "比赛内容",
        "竞赛内容",
        "参赛内容",
        "征集内容",
        "作品要求",
        "比赛要求",
        "竞赛要求",
        "招聘岗位",
        "招聘职位",
        "岗位职责",
        "岗位描述",
        "岗位需求",
        "薪资待遇",
        "福利待遇",
        "薪酬待遇",
    ),
    "awards": (
        "奖项设置",
        "奖项",
        "奖励办法",
        "奖励标准",
        "表彰",
        "评选结果",
        "结果公布",
    ),
    "contact": (
        "联系人及电话",
        "联系人",
        "联系方式",
        "联系电话",
        "咨询电话",
        "咨询方式",
        "联系部门",
        "联系地址",
        "通讯地址",
        "电子邮箱",
        "投稿邮箱",
        "报名邮箱",
        "咨询邮箱",
        "邮箱",
        "电话咨询",
    ),
    "organization": (
        "主办单位",
        "承办单位",
        "协办单位",
        "指导单位",
        "组织单位",
        "组织机构",
        "主办方",
        "承办方",
        "协办方",
        "组织委员会",
        "组委会",
    ),
    "attachment": (
        "附件下载",
        "附件",
        "附录",
        "相关附件",
    ),
}

_ALL_KEYS: tuple[str, ...] = tuple(SECTION_KEYWORDS) + ("signature",)

_KEYWORDS_BY_LENGTH: tuple[tuple[str, str], ...] = tuple(
    sorted(
        ((keyword, section) for section, keywords in SECTION_KEYWORDS.items() for keyword in keywords),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)

_NUMBERING_PREFIX = re.compile(
    r"^\s*(?:[一二三四五六七八九十]+[、.．]"
    r"|【[一二三四五六七八九十\d]+】"
    r"|[（(][一二三四五六七八九十\d]+[)）]"
    r"|\d+[、.．)）]"
    r"|第[一二三四五六七八九十\d]+[条章节部分篇])\s*"
)

_TRAIL_PUNCT = " ：:，,、。;；|｜　\t（）()【】[]"

# 标题后缀：如「参赛对象及要求」「报名方式及有关事项」，应视为纯标题。
_HEADING_SUFFIXES: tuple[str, ...] = (
    "及相关要求",
    "及有关要求",
    "及有关规定",
    "及注意事项",
    "等有关事项",
    "等事项",
    "等要求",
    "等材料",
    "等条件",
    "及要求",
    "及条件",
    "及标准",
    "及安排",
    "及范围",
    "和要求",
    "与要求",
    "及规定",
    "的要求",
    "有关要求",
    "相关要求",
    "具体要求",
    "工作要求",
    "要求",
    "条件",
    "标准",
    "安排",
    "范围",
    "情况",
    "说明",
    "事项",
)

_INLINE_LEAD = re.compile(r"^(?:为|是|如下|包括|包含)\s*")

# 标题前的限定词：如「活动联系人及联系方式」「本次大赛报名方式」。
_HEADING_PREFIXES = ("活动", "本次", "本届", "大赛", "赛事", "比赛", "竞赛", "招聘", "申报")

_SIGNATURE_EXCLUDE = (
    "全体",
    "面向",
    "学生",
    "同学",
    "师生",
    "对象",
    "条件",
    "报名",
    "参加",
    "参与",
    "申请",
    "要求",
    "资格",
    "每队",
    "每组",
)

# 含动作词的完整句子即使以单位名结尾，也不是落款。
# 例如「将纸质材料交至教务处创新创业办公室」属于流程步骤。
_SENTENCE_ACTION_WORDS = (
    "提交",
    "交至",
    "送至",
    "送交",
    "报送",
    "递交",
    "投递",
    "发送",
    "上传",
    "填写",
    "准备",
    "携带",
    "前往",
    "领取",
    "打印",
    "下载",
    "登录",
    "缴费",
    "缴纳",
    "支付",
    "办理",
    "联系",
    "咨询",
)

_SIGNATURE_ORG = re.compile(
    r"(大学|学院|学校|委员会|团委|团总支|团支部|学生会|研究生会"
    r"|协会|学会|公司|集团|研究院|研究所|办公室|中心|党委|党总支)$"
)
_ORG_INLINE = re.compile(
    r"(大学|学院|学校|委员会|团委|团总支|学生会|研究生会"
    r"|协会|学会|公司|集团|研究院|研究所|办公室|中心|党委|党总支)"
)
_DATE_INLINE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")
_SIGNATURE_BLOCK_EXCLUDE = (
    "请",
    "于",
    "前",
    "提交",
    "发送",
    "截止",
    "报名",
    "参加",
    "材料",
    "要求",
    "邮箱",
)
_DATE_ONLY = re.compile(r"^[二〇零一二三四五六七八九十百\d\s年月日\.\-/、（）()]+$")
_CLOSING_WORDS = ("特此通知", "特此公告", "特此函告", "此致")


@dataclass
class SectionContent:
    """归属某个章节的正文内容。"""

    section: str
    text: str
    segment: Segment


def strip_numbering(text: str) -> str:
    """去掉「一、」「1.」「（1）」「第一条」等编号前缀。"""
    return _NUMBERING_PREFIX.sub("", text.strip())


def normalize_heading(text: str) -> str:
    return strip_numbering(text).strip(f" {_TRAIL_PUNCT}")


def _clean_remainder(text: str) -> str:
    """清理标题后面的连接词与标点，取出同行正文。"""
    remainder = text.strip(_TRAIL_PUNCT)
    changed = True
    while changed and remainder:
        changed = False
        for suffix in _HEADING_SUFFIXES:
            if remainder == suffix:
                return ""
            if remainder.startswith(suffix):
                remainder = remainder[len(suffix):].strip(_TRAIL_PUNCT)
                changed = True
                break
    return _INLINE_LEAD.sub("", remainder).strip(_TRAIL_PUNCT)


def match_heading(text: str) -> tuple[str, str] | None:
    """判断片段是否是章节标题，返回（章节键，同行正文）。

    关键词按长度倒序匹配，确保「报名时间」不会被「报名」类短词抢先命中。
    标题与正文同行（含表格单元格拼接符「|」）时，后半部分作为 inline 正文返回。
    """
    normalized = normalize_heading(text)
    if not normalized:
        return None

    candidates = [normalized]
    for prefix in _HEADING_PREFIXES:
        if normalized.startswith(prefix) and len(normalized) > len(prefix) + 1:
            candidates.append(normalized[len(prefix):])
            break

    for candidate in candidates:
        for keyword, section in _KEYWORDS_BY_LENGTH:
            if not candidate.startswith(keyword):
                continue
            remainder = _clean_remainder(candidate[len(keyword):])
            return section, remainder
    return None


def detect_metadata_line(text: str) -> str | None:
    """识别落款、日期行等元信息，避免被计入正文或注意事项。"""
    compact = text.strip()
    if not compact:
        return None

    if len(compact) <= 40 and any(word in compact for word in _CLOSING_WORDS):
        return "signature"

    if len(compact) <= 30:
        if _DATE_ONLY.fullmatch(compact) and ("年" in compact or "月" in compact):
            return "signature"
        if _SIGNATURE_ORG.search(compact) and not any(
            word in compact for word in _SIGNATURE_EXCLUDE + _SENTENCE_ACTION_WORDS
        ):
            return "signature"
        # 「水利工程学院 2025年12月14日」这类落款：单位与日期同处一行
        if _DATE_INLINE.search(compact) and _ORG_INLINE.search(compact):
            if not any(word in compact for word in _SIGNATURE_BLOCK_EXCLUDE):
                return "signature"

    return None


def collect_sections(segments: list[Segment]) -> dict[str, list[SectionContent]]:
    """顺序扫描片段，把正文归入当前章节。

    遇到联系方式、组织单位、附件、落款等元信息时切换当前章节，
    从而终止「注意事项」对后续内容的吞并。
    """
    result: dict[str, list[SectionContent]] = {key: [] for key in _ALL_KEYS}
    current: str | None = None

    for segment in segments:
        # Word 中常用软换行把多个标题放在同一段落内，按行拆开识别，
        # 证据位置仍指向原段落。
        for line in segment.text.splitlines():
            text = line.strip()
            if not text:
                continue

            matched = match_heading(text)
            if matched:
                current, inline = matched
                if inline:
                    result[current].append(SectionContent(current, inline, segment))
                continue

            metadata = detect_metadata_line(text)
            if metadata:
                current = metadata
                result[metadata].append(SectionContent(metadata, text, segment))
                continue

            if current:
                result[current].append(SectionContent(current, text, segment))

    return result
