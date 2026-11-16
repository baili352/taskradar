"""对比重启前后快照，输出数据持久化统计。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"

before = json.loads((EVIDENCE / "persistence_before.json").read_text(encoding="utf-8"))
after = json.loads((EVIDENCE / "persistence_after.json").read_text(encoding="utf-8"))

checks = []


def add(name: str, ok: bool, expected: str, actual: str) -> None:
    checks.append(
        {
            "category": "数据持久化",
            "case": "重启前后",
            "name": name,
            "result": "PASS" if ok else "FAIL",
            "expected": expected,
            "actual": actual,
            "repro": "重启后端进程后重新查询",
            "evidence": "evidence/persistence_before.json / persistence_after.json",
        }
    )


for name, before_item in before.items():
    after_item = after.get(name)
    add(
        f"{name}：事项仍存在且关键字段一致",
        after_item is not None and before_item["matter"]["id"] == after_item["matter"]["id"]
        and before_item["matter"]["name"] == after_item["matter"]["name"]
        and before_item["matter"]["deadline"] == after_item["matter"]["deadline"]
        and before_item["matter"]["status"] == after_item["matter"]["status"],
        "事项 ID/名称/截止日期/状态一致",
        "一致" if after_item and before_item["matter"] == after_item["matter"] else "不一致或丢失",
    )
    if after_item is None:
        continue
    add(
        f"{name}：任务状态持久化",
        before_item["tasks"] == after_item["tasks"],
        f"{len(before_item['tasks'])} 个任务及状态一致",
        f"{len(after_item['tasks'])} 个任务；一致={before_item['tasks'] == after_item['tasks']}",
    )
    add(
        f"{name}：材料状态与文件持久化",
        before_item["materials"] == after_item["materials"],
        f"{len(before_item['materials'])} 项材料及文件信息一致",
        f"{len(after_item['materials'])} 项；一致={before_item['materials'] == after_item['materials']}",
    )
    add(
        f"{name}：风险状态持久化",
        before_item["risk_types"] == after_item["risk_types"],
        "重启前后未解决风险类型一致",
        f"一致={before_item['risk_types'] == after_item['risk_types']}",
    )

summary = {
    "category": "数据持久化",
    "total": len(checks),
    "passed": sum(1 for item in checks if item["result"] == "PASS"),
    "failed": sum(1 for item in checks if item["result"] == "FAIL"),
    "checks": checks,
}
(EVIDENCE / "results_persistence.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({k: summary[k] for k in ("total", "passed", "failed")}, ensure_ascii=False))
for item in checks:
    if item["result"] == "FAIL":
        print("FAIL:", item["name"], "|", item["actual"])
