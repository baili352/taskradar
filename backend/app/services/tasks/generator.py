"""从事项办理流程生成任务。

规则要点：
1. 只读取事项的 process（办理流程），不会把注意事项、组织单位、联系人当作任务。
2. 每个任务保留该流程步骤的原文证据，描述保存完整原文。
3. 标题只做“缩短”，不新增原文没有的操作，例如不会凭空加上“下载”。
4. 只有步骤原文里出现明确日期时才写入 deadline，否则留空；
   事项总截止日期只作为“系统建议”返回，由用户确认后再保存。
"""

import hashlib
import re
from dataclasses import dataclass

from app.schemas.matter import MatterEvidence, MatterRecord

_DATE_FULL = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_DATE_SHORT = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日")

_LEADING_ENUM = re.compile(r"^\s*(?:第\s*\d+\s*步[、.．:：]?|\d+\s*[、.．)）]|[（(]\s*\d+\s*[)）]|[①-⑳])\s*")
_NON_ACTIONABLE = re.compile(
    r"^\s*(?:联系人|联系方式|电话|手机|邮箱|电子邮箱|QQ\s*群|群号|地址|地点|主办单位|承办单位|"
    r"协办单位|指导单位|附件|附件下载)\s*[：:]"
)
_HIGH_PRIORITY = re.compile(r"提交|发送|上传|报名|截止|缴费|缴纳|确认|面试|答辩|报送")
_MEDIUM_PRIORITY = re.compile(r"填写|下载|准备|组队|联系|打印|盖章|扫描|排练|提交材料")
_SPLIT_PUNCT = re.compile(r"[。；;，,]")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_DIGITS = re.compile(r"[：:，,、]?\s*\d{5,}")


def _shorten_quoted(name: str) -> str:
    """书名号内是完整文件名，标题只保留可用于识别活动的后段。"""
    if len(name) <= 14:
        return name
    index = name.rfind("第")
    if index > 0 and len(name) - index <= 18:
        return name[index:]
    return name[-12:]


@dataclass
class GeneratedTask:
    title: str
    description: str
    priority: str
    deadline: str | None
    step_key: str
    evidence: MatterEvidence


def _clean_step(text: str) -> str:
    return _LEADING_ENUM.sub("", text.strip())


def _step_key(text: str) -> str:
    normalized = re.sub(r"[\s，。；、,.;:：（）()《》【】\[\]“”\"']", "", text)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:20]
    return f"process:{digest}"


def _build_title(text: str) -> str:
    title = _clean_step(text)
    title = re.sub(r"[（(]\s*见附件\s*[)）]", "", title)
    # 书名号内的全称通常很长，只保留尾部关键信息，避免标题变成整段原文。
    title = re.sub(r"《([^》]{1,80})》", lambda match: _shorten_quoted(match.group(1)), title)
    # 标题里不保留邮箱与长串号码（完整原文仍在 description 中）。
    title = _EMAIL.sub("", title)
    title = _LONG_DIGITS.sub("", title)
    title = _SPLIT_PUNCT.split(title)[0].strip(" ：:、")
    if not title:
        # 极端情况下（步骤几乎全是联系方式）退回到原文前 30 字。
        title = _clean_step(text)[:30]
    if len(title) > 30:
        title = f"{title[:29]}…"
    return title


def _suggest_priority(text: str) -> str:
    if _HIGH_PRIORITY.search(text):
        return "high"
    if _MEDIUM_PRIORITY.search(text):
        return "medium"
    return "low"


def _extract_deadline(text: str) -> str | None:
    full = _DATE_FULL.search(text)
    if full:
        year, month, day = full.groups()
        return f"{year}年{int(month)}月{int(day)}日"
    short = _DATE_SHORT.search(text)
    if short:
        month, day = short.groups()
        return f"{int(month)}月{int(day)}日"
    return None


def _is_actionable(text: str) -> bool:
    cleaned = _clean_step(text)
    if len(cleaned) < 3:
        return False
    if _NON_ACTIONABLE.match(cleaned):
        return False
    return bool(re.search(r"[\u4e00-\u9fa5A-Za-z]", cleaned))


def build_tasks_from_matter(matter: MatterRecord) -> list[GeneratedTask]:
    """按办理流程生成任务候选；同一流程文本只保留一条。"""
    generated: list[GeneratedTask] = []
    seen_keys: set[str] = set()

    for step in matter.process:
        text = step.text.strip()
        if not text or not _is_actionable(text):
            continue
        key = _step_key(text)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        generated.append(
            GeneratedTask(
                title=_build_title(text),
                description=text,
                priority=_suggest_priority(text),
                deadline=_extract_deadline(text),
                step_key=key,
                evidence=step.evidence,
            )
        )

    return generated
