"""大模型事项分析：严格校验 JSON，并仅从本地 Segment 重建证据。"""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from app.core.config import settings
from app.services.ai.client import AIError, request_analysis_json
from app.services.documents.types import ExtractedDocument
from app.services.extraction.extractor import build_evidence

FIELD_DEFINITIONS = (
    ("title", "事项名称"),
    ("matter_type", "事项类型"),
    ("qualification", "申请资格"),
    ("registration_start", "报名开始日期"),
    ("deadline", "截止日期"),
)
FIELD_KEYS = tuple(key for key, _label in FIELD_DEFINITIONS)
FIELD_LABELS = dict(FIELD_DEFINITIONS)

SYSTEM_PROMPT = """你是办事通知信息提取助手。只能依据用户提供的原文片段，不得使用外部知识或猜测。
只返回一个 JSON 对象，不要 Markdown，不要额外解释，结构严格如下：
{
  "fields": [
    {"key":"title","value":"...或null","status":"found或pending","segment_ids":[0],"note":"...或null"},
    {"key":"matter_type","value":"...或null","status":"found或pending","segment_ids":[0],"note":"...或null"},
    {"key":"qualification","value":"...或null","status":"found或pending","segment_ids":[0],"note":"...或null"},
    {"key":"registration_start","value":"...或null","status":"found或pending","segment_ids":[0],"note":"...或null"},
    {"key":"deadline","value":"...或null","status":"found或pending","segment_ids":[0],"note":"...或null"}
  ],
  "materials": [{"name":"材料名","segment_id":0}],
  "process": [{"text":"办理步骤","segment_id":0}],
  "notes": [{"text":"注意事项","segment_id":0}]
}
fields 必须且只能按给定顺序包含这五项。found 必须有非空 value 和有效原文片段编号；找不到时 value 为 null、status 为 pending、segment_ids 为空。
materials/process/notes 每项都必须引用一个有效 segment_id，没有依据就返回空数组。不得虚构截止日期、补全原文没有的年份或编造依据。
不要返回证据正文、页码、段落或位置，后端会根据 segment_id 从本地原文重建。"""

_FENCE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AIField(_Model):
    key: str
    value: str | None = Field(default=None, max_length=2000)
    status: Literal["found", "pending"]
    segment_ids: list[StrictInt] = Field(default_factory=list, max_length=5)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_status(self) -> "AIField":
        if self.status == "found" and (not self.value or not self.segment_ids):
            raise ValueError("found 字段必须包含值和证据编号")
        if self.status == "pending" and (self.value is not None or self.segment_ids):
            raise ValueError("pending 字段不能包含值或证据编号")
        return self


class AIMaterial(_Model):
    name: str = Field(min_length=1, max_length=200)
    segment_id: StrictInt = Field(ge=0)


class AIProcess(_Model):
    text: str = Field(min_length=1, max_length=1000)
    segment_id: StrictInt = Field(ge=0)


class AINote(_Model):
    text: str = Field(min_length=1, max_length=2000)
    segment_id: StrictInt = Field(ge=0)


class AIPayload(_Model):
    fields: list[AIField] = Field(min_length=5, max_length=5)
    materials: list[AIMaterial] = Field(default_factory=list, max_length=40)
    process: list[AIProcess] = Field(default_factory=list, max_length=30)
    notes: list[AINote] = Field(default_factory=list, max_length=20)


def _parse_payload(content: str) -> AIPayload:
    candidate = content.strip()
    fence = _FENCE.fullmatch(candidate)
    if fence:
        candidate = fence.group(1).strip()
    try:
        raw = json.loads(candidate)
        if not isinstance(raw, dict):
            raise ValueError("根节点不是对象")
        return AIPayload.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, ValueError):
        raise AIError("大模型返回的 JSON 结构或字段约束不合法。") from None


def _segment(payload_id: int, document: ExtractedDocument):
    if payload_id < 0 or payload_id >= len(document.segments):
        raise AIError("大模型结果引用了不存在的原文片段编号。")
    return document.segments[payload_id]


def _warnings(result: dict) -> list[str]:
    fields = result["fields"]
    warnings = []
    qualification = next(item for item in fields if item["key"] == "qualification")
    if qualification["status"] == "pending":
        warnings.append("未识别到「申请资格 / 参赛对象」的明确表述。")
    if not result["materials"]:
        warnings.append("未识别到材料要求，请核实原文是否包含材料清单或「填写/提交」类要求。")
    if not result["process"]:
        warnings.append("未识别到办理流程，请核实原文是否包含「报名方式 / 办理流程」等章节。")
    if not result["notes"]:
        warnings.append("未识别到注意事项，请核实原文是否包含「注意事项 / 温馨提示」章节。")
    return warnings


def _build_result(payload: AIPayload, document: ExtractedDocument) -> dict:
    if tuple(item.key for item in payload.fields) != FIELD_KEYS:
        raise AIError("大模型返回的字段键或字段顺序不符合约定。")

    fields = []
    for item in payload.fields:
        evidence = [
            build_evidence(_segment(segment_id, document))
            for segment_id in item.segment_ids
        ]
        fields.append(
            {
                "key": item.key,
                "label": FIELD_LABELS[item.key],
                "value": item.value,
                "status": item.status,
                "evidence": evidence,
                "note": item.note,
            }
        )

    materials = [
        {
            "name": item.name,
            "status": "found",
            "evidence": build_evidence(_segment(item.segment_id, document)),
        }
        for item in payload.materials
    ]
    process = [
        {
            "index": index,
            "text": item.text,
            "evidence": build_evidence(_segment(item.segment_id, document)),
        }
        for index, item in enumerate(payload.process, start=1)
    ]
    notes = [
        {
            "text": item.text,
            "evidence": build_evidence(_segment(item.segment_id, document)),
        }
        for item in payload.notes
    ]
    result = {"fields": fields, "materials": materials, "process": process, "notes": notes}
    result["warnings"] = _warnings(result)
    return result


async def analyze_with_ai(document: ExtractedDocument) -> dict:
    """发送带编号的原文片段，任一校验失败则整份结果不可用。"""
    input_chars = sum(len(segment.text) for segment in document.segments)
    if input_chars > settings.ai_max_input_chars:
        raise AIError(
            f"文档文本约 {input_chars} 字，超过 AI 单次分析上限 {settings.ai_max_input_chars} 字；未截断发送。"
        )
    if not document.segments:
        raise AIError("文档没有可发送给大模型的文本片段。")

    segments = [
        {
            "segment_id": index,
            "text": segment.text,
            "page": segment.page,
            "paragraph": segment.paragraph,
            "location": segment.location,
        }
        for index, segment in enumerate(document.segments)
    ]
    user_prompt = json.dumps({"segments": segments}, ensure_ascii=False)
    content = await request_analysis_json(SYSTEM_PROMPT, user_prompt)
    return _build_result(_parse_payload(content), document)
