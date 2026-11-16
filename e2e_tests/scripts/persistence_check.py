"""重启前后数据持久化核对：生成 before/after 快照并对比。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import request  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"


def snapshot() -> dict:
    base = json.loads((EVIDENCE / "results_api.json").read_text(encoding="utf-8"))
    matters = {}
    for name, matter_id in base["matter_ids"].items():
        matter = request("GET", f"/matters/{matter_id}").body
        tasks = request("GET", "/tasks", params={"matter_id": matter_id}).body or []
        materials = request("GET", f"/matters/{matter_id}/materials").body or []
        risks = request("GET", f"/matters/{matter_id}/risks").body or {}
        matters[name] = {
            "matter": {
                "id": matter.get("id"),
                "name": matter.get("name"),
                "status": matter.get("status"),
                "deadline": matter.get("deadline"),
                "registration_start": matter.get("registration_start"),
                "materials_count": len(matter.get("materials") or []),
                "process_count": len(matter.get("process") or []),
            },
            "tasks": [
                {"id": task["id"], "title": task["title"], "status": task["status"]}
                for task in tasks
            ],
            "materials": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "status": item["status"],
                    "file": item.get("original_filename"),
                }
                for item in materials
            ],
            "risk_types": [item["risk_type"] for item in (risks.get("risks") or [])],
        }
    return matters


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "before"
    data = snapshot()
    (EVIDENCE / f"persistence_{mode}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"mode": mode, "matters": len(data)}, ensure_ascii=False))


if __name__ == "__main__":
    main()


def compare() -> None:  # pragma: no cover - 由 compare_persistence.py 调用
    pass
