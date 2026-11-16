"""从事项的材料要求生成材料清单。

只读取事项的 materials 字段，不引入原文之外的内容；每个材料保留对应原文证据。
同一事项内按名称归一化去重，数据库唯一索引作为最终兜底。
"""

import hashlib
import re

from app.schemas.matter import MatterEvidence, MatterRecord

_NORMALIZE = re.compile(r"[\s\u3000，,。；;：:、（）()【】\[\]《》<>\"'“”‘’·—\-_/\\]+")


def material_step_key(name: str) -> str:
    normalized = _NORMALIZE.sub("", name).lower()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:20]
    return f"material:{digest}"


def build_materials_from_matter(
    matter: MatterRecord,
) -> list[dict[str, object]]:
    """返回待写入的材料列表，已按名称在事项内去重。"""
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()

    for item in matter.materials:
        name = item.name.strip()
        if not name:
            continue
        key = material_step_key(name)
        if key in seen:
            continue
        seen.add(key)

        evidence: MatterEvidence | None = item.evidence
        candidates.append(
            {
                "name": name,
                "description": evidence.text if evidence else "",
                "evidence": evidence,
                "step_key": key,
            }
        )

    return candidates
