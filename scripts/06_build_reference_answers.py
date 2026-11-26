#!/usr/bin/env python3
"""Runs every reference query in `backend/reference_answers.py` and writes a snapshot to
`benchmarks/reference_answers.json`. The portal shows the snapshot next to the pre-run baseline
cards; live workbench runs execute the same queries again at run time.

Usage:  GOOGLE_CLOUD_PROJECT=<project> python scripts/06_build_reference_answers.py
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.reference_answers import REFERENCES, normalize_question, run_reference  # noqa: E402

OUT = REPO_ROOT / "benchmarks" / "reference_answers.json"


def main() -> None:
    entries = []
    for ref in REFERENCES:
        res = run_reference(ref)
        res["questions"] = [normalize_question(q) for q in ref["questions"]]
        entries.append(res)
        for q in res["queries"]:
            status = q.get("error") or f"{len(q['rows'])} row(s)"
            print(f"[{ref['id']}] {q['label']['en']}: {status}")
    OUT.write_text(
        json.dumps(
            {"generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "references": entries},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[OK] wrote {OUT}")


if __name__ == "__main__":
    main()
