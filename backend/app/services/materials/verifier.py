"""本地规则核验。

设计原则：
- 只依据真实上传文件的文本与材料要求原文，不编造内容；
- 文件可读取 + 文本有效 + 材料名称关键词匹配 + 要求要素齐全，才判定为 qualified；
- 规则无法判断时给出 uncertain 并写明原因；
- 规则发现可能的问题时给出 incomplete（信息不完整）或 uncertain，提示人工确认，
  不会直接判定材料无效；conflict 只能由人工确认产生。
"""

import re
from datetime import datetime

from app.schemas.material import MaterialVerification, MaterialVerificationCheck
from app.services.documents.types import ExtractedDocument

_PARENTHESES = re.compile(r"[（(][^）)]{0,40}[）)]")
_SEPARATORS = re.compile(r"[\s\u3000、,，;；:：/\\\-]+")
_SUFFIXES = ("复印件", "扫描件", "电子版", "原件", "照片", "材料", "文件", "证明")
_GENERIC_NAMES = {
    "材料",
    "文件",
    "相关材料",
    "证明材料",
    "纸质版",
    "电子版",
    "扫描件",
    "复印件",
    "附件",
}

_MARKERS = (
    ("签字", ("签字", "签名")),
    ("盖章", ("盖章", "公章", "印章")),
    ("日期", ("日期",)),
    ("身份证号", ("身份证号", "身份证", "证件号")),
    ("联系方式", ("联系方式", "电话", "手机", "邮箱")),
    ("学号", ("学号",)),
)

_SUSPICIOUS_PHRASES = (
    "过期",
    "失效",
    "不符合",
    "不满足",
    "无效",
    "作废",
    "不予受理",
    "未通过",
    "造假",
    "伪造",
)

# 否定前缀：「未过期」「没有失效」「不存在无效」等不应被当成问题表述。
_NEGATIONS = ("未", "不", "无", "非", "没")

_WHITESPACE = re.compile(r"[\s\u3000]+")


def _normalize(text: str) -> str:
    """去掉空白后比对，避免「成绩 单」这类空格差异造成误判。"""
    return _WHITESPACE.sub("", text or "")


def _contains(text: str, keyword: str) -> bool:
    normalized_keyword = _normalize(keyword)
    return bool(normalized_keyword) and normalized_keyword in text


def _find_suspicious(text: str) -> list[str]:
    """返回真正出现且未被否定的问题表述，减少「未过期」这类误判。"""
    found: list[str] = []
    for phrase in _SUSPICIOUS_PHRASES:
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            prefix = text[max(0, index - 2) : index]
            if not any(prefix.endswith(negation) for negation in _NEGATIONS):
                found.append(phrase)
                break
            start = index + len(phrase)
    return found


def _strip_suffix(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            return word[: -len(suffix)]
    return word


def extract_keywords(name: str) -> list[str]:
    """从材料名称提取用于文本比对的关键词，去掉格式类后缀。"""
    text = _PARENTHESES.sub(" ", name or "")
    keywords: list[str] = []
    for part in _SEPARATORS.split(text):
        word = part.strip("。.·—－_")
        if not word:
            continue
        word = _strip_suffix(word)
        if len(word) < 2 or word in _GENERIC_NAMES:
            continue
        if word not in keywords:
            keywords.append(word)
    return keywords[:6]


def _requirement_text(material: dict) -> str:
    parts: list[str] = [material.get("name") or "", material.get("description") or ""]
    evidence = material.get("source_evidence")
    if evidence is not None:
        parts.append(getattr(evidence, "text", "") or "")
    return "\n".join(part for part in parts if part)


def _first_excerpt(
    document: ExtractedDocument, tokens: list[str]
) -> tuple[str | None, str | None]:
    for segment in document.segments:
        text = segment.text or ""
        if any(token and _contains(_normalize(text), token) for token in tokens):
            excerpt = text.strip()
            if len(excerpt) > 180:
                excerpt = excerpt[:180] + "…"
            return excerpt, segment.location or None
    return None, None


def _format_scope(document: ExtractedDocument) -> str:
    parts: list[str] = []
    if document.page_count:
        parts.append(f"共 {document.page_count} 页")
    if document.paragraph_count:
        parts.append(f"{document.paragraph_count} 段")
    parts.append(f"{document.char_count} 字")
    return "，".join(parts)


def verify_material(
    material: dict, document: ExtractedDocument
) -> MaterialVerification:
    """执行规则核验，返回可持久化的核验记录。"""
    checks: list[MaterialVerificationCheck] = []
    reasons: list[str] = []
    full_text = "\n".join(_normalize(segment.text) for segment in document.segments)
    requirement = _normalize(_requirement_text(material))

    checks.append(
        MaterialVerificationCheck(
            key="file_readable",
            label="文件可读取",
            status="pass",
            message=f"文件已通过格式与内容校验，可正常读取：{_format_scope(document)}。",
            location=document.filename,
        )
    )

    char_count = document.char_count
    if char_count > 0:
        checks.append(
            MaterialVerificationCheck(
                key="text_extracted",
                label="有效文本",
                status="pass",
                message=f"成功提取到 {char_count} 个字符，可用于内容比对。",
            )
        )
    else:
        checks.append(
            MaterialVerificationCheck(
                key="text_extracted",
                label="有效文本",
                status="unknown",
                message="文件可打开，但没有提取到有效文本，可能是扫描件或空白文档。",
            )
        )
        reasons.append("文件未提取到有效文本，无法比对材料内容，需人工查看原件。")

    keywords = extract_keywords(material.get("name") or "")
    matched: list[str] = []
    missing: list[str] = []
    if not keywords:
        checks.append(
            MaterialVerificationCheck(
                key="keyword_coverage",
                label="关键内容",
                status="unknown",
                message="材料名称过于笼统，无法提取可用于比对的关键词。",
            )
        )
        reasons.append("材料名称过于笼统，规则无法自动比对关键内容。")
    else:
        for keyword in keywords:
            (matched if _contains(full_text, keyword) else missing).append(keyword)
        excerpt, location = _first_excerpt(document, matched)
        if not missing:
            checks.append(
                MaterialVerificationCheck(
                    key="keyword_coverage",
                    label="关键内容",
                    status="pass",
                    message=f"文件文本包含材料名称中的全部关键内容：{'、'.join(matched)}。",
                    excerpt=excerpt,
                    location=location,
                )
            )
        else:
            checks.append(
                MaterialVerificationCheck(
                    key="keyword_coverage",
                    label="关键内容",
                    status="warn",
                    message=(
                        f"已匹配：{'、'.join(matched) if matched else '无'}；"
                        f"未找到：{'、'.join(missing)}。可能是材料不匹配，或文件内容缺少相关表述。"
                    ),
                    excerpt=excerpt,
                    location=location,
                )
            )
            reasons.append(
                f"文件文本中未找到关键词：{'、'.join(missing)}，需人工确认材料是否匹配。"
            )

    required_markers = [
        (label, words) for label, words in _MARKERS if any(word in requirement for word in words)
    ]
    if not required_markers:
        checks.append(
            MaterialVerificationCheck(
                key="required_elements",
                label="要求要素",
                status="pass",
                message="材料要求中未提到签字、盖章、日期等必须要素，无需逐项比对。",
            )
        )
    else:
        missing_markers: list[str] = []
        present_markers: list[str] = []
        for label, words in required_markers:
            if any(_contains(full_text, word) for word in words):
                present_markers.append(label)
            else:
                missing_markers.append(label)
        if missing_markers:
            checks.append(
                MaterialVerificationCheck(
                    key="required_elements",
                    label="要求要素",
                    status="warn",
                    message=(
                        f"材料要求涉及：{'、'.join(label for label, _ in required_markers)}；"
                        f"文件中未找到：{'、'.join(missing_markers)}。"
                    ),
                )
            )
            reasons.append(
                f"材料要求涉及「{'、'.join(missing_markers)}」，但文件文本中未找到，需人工核对原件。"
            )
        else:
            checks.append(
                MaterialVerificationCheck(
                    key="required_elements",
                    label="要求要素",
                    status="pass",
                    message=f"材料要求涉及的要素均已出现：{'、'.join(present_markers)}。",
                )
            )

    suspicious = _find_suspicious(full_text)
    if suspicious:
        excerpt, location = _first_excerpt(document, suspicious)
        checks.append(
            MaterialVerificationCheck(
                key="suspicious_phrases",
                label="冲突风险",
                status="unknown",
                message=(
                    f"文件文本中出现「{'、'.join(suspicious)}」等表述，"
                    "可能表示材料存在问题，需人工确认，系统不直接判定材料无效。"
                ),
                excerpt=excerpt,
                location=location,
            )
        )
        reasons.append("文件文本存在可能表示材料不符合要求的表述，需人工确认。")
    else:
        checks.append(
            MaterialVerificationCheck(
                key="suspicious_phrases",
                label="冲突风险",
                status="pass",
                message="未发现「过期、失效、无效」等可能表示材料不符合要求的表述。",
            )
        )

    if char_count == 0:
        result = "uncertain"
        summary = "文件可打开但未提取到有效文本，系统无法判断材料是否符合要求，请人工查看原件。"
    elif suspicious:
        result = "uncertain"
        summary = "文件文本出现可能表示材料存在问题的表述，系统无法判断，请人工确认。"
    elif not keywords:
        result = "uncertain"
        summary = "材料名称过于笼统，系统缺少比对依据，无法判断材料是否符合要求。"
    elif missing or any(
        check.key == "required_elements" and check.status == "warn" for check in checks
    ):
        result = "incomplete"
        summary = "文件可读取，但部分关键内容或要求要素未在文本中找到，信息可能不完整，请人工确认。"
    else:
        result = "qualified"
        summary = (
            "规则核验通过：文件可读取、文本有效，材料名称关键词均已匹配。"
            "该结论仅为规则比对结果，不代表对材料真实性或法律效力的认定，请人工确认。"
        )

    return MaterialVerification(
        result=result,
        source="rule",
        verified_at=datetime.now().isoformat(timespec="milliseconds"),
        summary=summary,
        checks=checks,
        reasons=reasons,
        reviewer_note=None,
    )
