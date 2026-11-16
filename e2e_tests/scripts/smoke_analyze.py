"""上传全部测试文档，输出解析摘要，便于确认测试预期。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import upload_file  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs"
EVIDENCE = Path(__file__).resolve().parent.parent / "evidence"


def main() -> None:
    summary = []
    for path in sorted(DOCS.iterdir()):
        result = upload_file("/analysis/analyze", path)
        item = {"file": path.name, "status": result.status}
        if result.status == 200:
            body = result.body
            fields = {f["key"]: f for f in body["fields"]}
            item.update(
                {
                    "char_count": body["document"]["char_count"],
                    "title": fields["title"]["value"],
                    "title_status": fields["title"]["status"],
                    "matter_type": fields["matter_type"]["value"],
                    "qualification": (fields["qualification"]["value"] or "")[:60],
                    "registration_start": fields["registration_start"]["value"],
                    "deadline": fields["deadline"]["value"],
                    "deadline_note": fields["deadline"]["note"],
                    "materials": [m["name"] for m in body["materials"]],
                    "process": [p["text"] for p in body["process"]],
                    "notes_count": len(body["notes"]),
                    "warnings": body["warnings"],
                }
            )
        else:
            item["error"] = result.body
        summary.append(item)
        print(json.dumps(item, ensure_ascii=False, indent=2))
    (EVIDENCE / "smoke_analysis.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
