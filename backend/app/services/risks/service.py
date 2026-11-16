"""风险刷新与统计的业务编排。

读取与刷新严格分离：
- 查询接口只做内存分析与数据库读取，不写入任何风险记录；
- 只有显式调用 refresh_risks()（POST /api/risks/refresh）才会同步数据库。
"""

from app.db.risks import count_risks, sync_risks
from app.schemas.risk import RiskSummary
from app.services.risks.analyzer import AnalysisOutcome, analyze_risks
from app.services.risks.dates import get_timezone_name, now_in_timezone, today_in_timezone


def _build_summary(counts: dict, outcome: AnalysisOutcome) -> RiskSummary:
    payload = {**counts, **outcome.stats}
    # 以数据库实际未解决风险为准，避免统计口径与风险列表不一致。
    payload["matters_with_risks"] = counts["matters_with_risks"]
    return RiskSummary(
        generated_at=now_in_timezone().isoformat(timespec="milliseconds"),
        timezone=get_timezone_name(),
        today=today_in_timezone().isoformat(),
        **payload,
    )


def read_risk_summary() -> tuple[RiskSummary, AnalysisOutcome]:
    """只读统计：动态分析只发生在内存中，不会写入数据库。"""
    outcome = analyze_risks()
    return _build_summary(count_risks(), outcome), outcome


def refresh_risks() -> tuple[dict, RiskSummary, AnalysisOutcome]:
    """显式刷新：重新分析全部事项，并同步数据库中的风险状态。"""
    outcome = analyze_risks()
    sync_result = sync_risks(outcome.candidates)
    return sync_result, _build_summary(count_risks(), outcome), outcome
