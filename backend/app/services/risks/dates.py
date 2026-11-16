"""统一日期解析与时区处理（第四阶段第四步）。

规则：
1. 只识别明确的 ISO 日期与中文日期，不猜测缺失的年 / 月 / 日。
2. 原文只有日期没有时刻时，按“当天结束”作为统一规则参与到期判断，
   不会假设具体的时分。
3. 无法解析的日期返回 unverified，由风险服务标记为「日期待核实」，
   不参与逾期判断。
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

logger = logging.getLogger(__name__)

DeadlineStatus = Literal["missing", "ok", "unverified"]

# 前后都加数字边界，避免从「12026-1-1」「2026-01-011」这类长数字中截取日期。
_ISO_PATTERN = re.compile(
    r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"
    r"(?:[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?(?!\d)"
)
_CN_PATTERN = re.compile(
    r"(?<!\d)(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    r"(?:\s*(\d{1,2})\s*[:：时]\s*(\d{1,2})\s*分?)?(?!\d)"
)
_CN_SHORT_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# Windows 默认不带 IANA 时区库，缺少 tzdata 时使用固定偏移兜底。
_FIXED_OFFSET_HOURS = {
    "Asia/Shanghai": 8,
    "Asia/Chongqing": 8,
    "Asia/Hong_Kong": 8,
    "Asia/Macau": 8,
    "Asia/Taipei": 8,
    "UTC": 0,
}


@dataclass(frozen=True)
class DeadlineInfo:
    """一次截止日期解析结果；moment 为带时区的截止瞬间。"""

    status: DeadlineStatus
    raw: str | None
    normalized: str | None = None
    day: date | None = None
    moment: datetime | None = None
    has_time: bool = False
    reason: str | None = None


def get_timezone() -> tzinfo:
    name = (settings.app_timezone or "Asia/Shanghai").strip() or "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        offset = _FIXED_OFFSET_HOURS.get(name)
        if offset is None:
            logger.warning("未知时区 %s，回退为 UTC+8（Asia/Shanghai）", name)
            offset = 8
        return timezone(timedelta(hours=offset), name)


def get_timezone_name() -> str:
    return (settings.app_timezone or "Asia/Shanghai").strip() or "Asia/Shanghai"


def now_in_timezone() -> datetime:
    return datetime.now(get_timezone())


def today_in_timezone() -> date:
    return now_in_timezone().date()


def _build_deadline(
    raw: str,
    year: int,
    month: int,
    day_value: int,
    hour: int | None,
    minute: int | None,
    *,
    has_time: bool,
    is_iso: bool,
) -> DeadlineInfo:
    try:
        day = date(year, month, day_value)
    except ValueError:
        return DeadlineInfo(
            status="unverified",
            raw=raw,
            reason=f"日期 {year}-{month}-{day_value} 不存在，需要人工核实。",
        )

    moment = datetime.combine(day, time(23, 59, 59, 999999), tzinfo=get_timezone())
    if has_time:
        if hour is None or minute is None or not (0 <= hour <= 23 and 0 <= minute <= 59):
            return DeadlineInfo(
                status="unverified",
                raw=raw,
                day=day,
                has_time=False,
                reason="原文中的具体时刻不合法，需要人工核实。",
            )
        moment = datetime.combine(
            day, time(hour, minute, 59, 999999), tzinfo=get_timezone()
        )

    normalized = day.isoformat()
    if is_iso:
        normalized = f"{year:04d}-{month:02d}-{day_value:02d}"
    if has_time and hour is not None and minute is not None:
        normalized = f"{normalized} {hour:02d}:{minute:02d}"

    return DeadlineInfo(
        status="ok",
        raw=raw,
        normalized=normalized,
        day=day,
        moment=moment,
        has_time=has_time,
    )


def parse_deadline(raw: str | None) -> DeadlineInfo:
    """解析 ISO / 中文截止日期；无法确定时返回 unverified 并说明原因。"""
    text = (raw or "").strip()
    if not text:
        return DeadlineInfo(status="missing", raw=None, reason="没有提供截止日期。")

    match = _ISO_PATTERN.search(text)
    if match:
        year, month, day_value, hour, minute, _second = match.groups()
        return _build_deadline(
            text,
            int(year),
            int(month),
            int(day_value),
            int(hour) if hour else None,
            int(minute) if minute else None,
            has_time=hour is not None,
            is_iso=True,
        )

    match = _CN_PATTERN.search(text)
    if match:
        year, month, day_value, hour, minute = match.groups()
        return _build_deadline(
            text,
            int(year),
            int(month),
            int(day_value),
            int(hour) if hour else None,
            int(minute) if minute else None,
            has_time=hour is not None,
            is_iso=False,
        )

    match = _CN_SHORT_PATTERN.search(text)
    if match:
        month, day_value = match.groups()
        # 明确禁止补全原文没有的年份。
        return DeadlineInfo(
            status="unverified",
            raw=text,
            reason=f"原文只有「{month}月{day_value}日」，缺少年份，需要人工核实。",
        )

    return DeadlineInfo(
        status="unverified",
        raw=text,
        reason="无法识别为明确的日期格式，需要人工核实。",
    )


def days_left(day: date, today: date) -> int:
    """截止日期距今天的天数：今天为 0，已过期为负数。"""
    return (day - today).days


def ensure_aware(value: datetime) -> datetime:
    """把时间统一为带时区的本地时间。

    数据库与调用方可能传入 naive 时间（历史数据、脚本、测试），
    这里统一按配置时区补全，避免 naive / aware 直接比较抛出 TypeError。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=get_timezone())
    return value.astimezone(get_timezone())


def is_overdue(info: DeadlineInfo, now: datetime) -> bool:
    if info.status != "ok" or info.moment is None:
        return False
    return ensure_aware(info.moment) < ensure_aware(now)


def participates(source: str | None, raw: str | None) -> bool:
    """只有明确日期来源才参与到期判断。

    document / manual 直接参与；suggested 只有经用户应用（随后会被标记为
    manual）后才参与；none 或空日期不参与。
    """
    if not (raw or "").strip():
        return False
    return (source or "none") in {"document", "manual"}
