#!/usr/bin/env python3
"""Runs the preset questions that have a reference query several times and counts how often every
reference figure appears in each pipeline's output.

For each run both pipelines answer the question on the deployed (or local) service, and the service
runs the hand-written reference query on BigQuery at the same time. This script then checks, for
each side, whether every numeric cell of the reference rows appears in that side's result table or
answer text (the As-Is table is the rows BQCA returned to the built-in tool).

This is a spot check, not an accuracy evaluation: a question can have more than one defensible
reading, and the same question can give different answers on different runs.

Output: `benchmarks/answer_check_results.json`. Standard library only.

Usage:
    python3 scripts/07_answer_check.py --base-url https://<service-url> [--runs 5]
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
import urllib.request

OUT_JSON = Path(__file__).resolve().parent.parent / "benchmarks" / "answer_check_results.json"

# (key, scenario code, prompt). A run sends them in this order in one visitor session, so the
# follow-up and the domain switch have the earlier turns they refer to.
QUESTIONS = [
    ("s1_vip_by_source", "S1", "Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days."),
    ("s2_follow_up_cart", "S2", "Keep those exact columns from the previous result and join our 14-day cart session count and cart abandonment rate (%) for each traffic_source."),
    ("s3_switch_supply_chain", "S3", "Now pivot to Supply Chain: compare average delivery lead time in days and unsold inventory holding cost ($) across all distribution centers."),
    ("s3_three_domains", "S3", "Why is Women's Outerwear & Coats realized profit dropping despite strong VIP sales? Run a parallel cross-domain analysis across: (1) last 30-day VIP orders & gross demand where order_id >= 9900000, (2) Women's 'Outerwear & Coats' unit margin %, return rate %, and realized profit by brand (order_id >= 9900000), and (3) recent Women's Outerwear average delivery lead time in days and unsold holding cost by distribution center (order_id >= 9900000)."),
    ("s3_cross_channel_fallback", "S3", "Compare net profit by year across the retail store, catalog and web channels side by side in one table."),
    ("s4_dc_outerwear", "S4", "Compare average delivery lead time in days and unsold inventory holding cost ($) by distribution center for Women's Outerwear (order_id >= 9900000)."),
    ("s1_store_by_year", "S1", "For the retail store channel, show net sales and net profit by year."),
]

SKIP_COLS = {"delivered_items", "order_items", "unsold_cost_seed_rows_only"}
ALT = {"unsold_cost_all_womens_outerwear": "unsold_cost_seed_rows_only"}


def numbers_in(text: str) -> list[float]:
    out = []
    for tok in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?", text):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            pass
    return out


def near(value: str, nums: list[float]) -> bool:
    f = float(value)
    return any(abs(f - n) <= max(0.011, abs(f) * 1e-5) for n in nums)


def score(reference: dict, text: str) -> tuple[int, int]:
    nums = numbers_in(text)
    hit = total = 0
    for q in reference.get("queries", []):
        cols = q.get("columns", [])
        for row in q.get("rows", []):
            cells = dict(zip(cols, row))
            for col, val in cells.items():
                if col in SKIP_COLS or val is None or not re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", str(val)):
                    continue
                total += 1
                ok = near(val, nums)
                if not ok and col in ALT and cells.get(ALT[col]) is not None:
                    ok = near(cells[ALT[col]], nums)
                hit += ok
    return hit, total


def stream(base: str, visitor: str, code: str, prompt: str) -> dict | None:
    req = urllib.request.Request(
        base.rstrip("/") + "/api/workbench/stream",
        data=json.dumps({"visitor_id": visitor, "scenario_code": code, "prompt": prompt, "s4_mode": "burst"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    payload = None
    with urllib.request.urlopen(req, timeout=900) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if line.startswith("data:"):
                ev = json.loads(line[5:])
                if ev.get("type") == "complete":
                    payload = ev["payload"]
    return payload


def one_run(base: str, run_no: int) -> list[dict]:
    visitor = f"answercheck_{int(time.time())}_{os.getpid()}_{run_no}"
    rows = []
    for key, code, prompt in QUESTIONS:
        try:
            p = stream(base, visitor, code, prompt)
        except Exception as exc:  # pylint: disable=broad-except
            rows.append({"key": key, "run": run_no, "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        if not p:
            rows.append({"key": key, "run": run_no, "error": "no result"})
            continue
        ref = p.get("reference") or {}
        row = {"key": key, "run": run_no, "reference_executed_at_utc": ref.get("executed_at_utc")}
        for side in ("tobe", "asis"):
            s = p[side]
            text = (s.get("markdown_table") or "") + "\n" + (s.get("answer") or "")
            hit, total = score(ref, text)
            row[side] = {
                "reference_cells_found": hit, "reference_cells": total, "all_found": bool(total) and hit == total,
                "bqca_agents": s.get("bqca_agents"), "errors": s.get("errors"), "status": s.get("status"),
                "table_chars": len(s.get("markdown_table") or ""), "answer_chars": len(s.get("answer") or ""),
                "numbers_in_output": len(numbers_in(text)),
                "_excerpt": {"table": (s.get("markdown_table") or "")[:400], "answer": (s.get("answer") or "")[:400],
                             "tools": s.get("tool_calls"), "questions": s.get("bqca_questions")},
            }
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--debug-out", default=None, help="Optional path for per-run output excerpts (not part of the result file).")
    args = ap.parse_args()
    with ThreadPoolExecutor(args.runs) as pool:
        all_rows = [r for rows in pool.map(lambda i: one_run(args.base_url, i), range(1, args.runs + 1)) for r in rows]
    if args.debug_out:
        Path(args.debug_out).write_text(json.dumps(all_rows, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    for r in all_rows:
        for side in ("tobe", "asis"):
            if side in r:
                r[side].pop("_excerpt", None)
    summary = []
    for key, code, prompt in QUESTIONS:
        rows = [r for r in all_rows if r["key"] == key and "error" not in r]
        summary.append({
            "key": key, "scenario": code, "prompt": prompt, "runs": len(rows),
            "tobe_all_found": sum(r["tobe"]["all_found"] for r in rows),
            "asis_all_found": sum(r["asis"]["all_found"] for r in rows),
            "tobe_cells": [f"{r['tobe']['reference_cells_found']}/{r['tobe']['reference_cells']}" for r in rows],
            "asis_cells": [f"{r['asis']['reference_cells_found']}/{r['asis']['reference_cells']}" for r in rows],
            "tobe_bqca_calls": [len(r["tobe"]["bqca_agents"] or []) for r in rows],
            "asis_bqca_calls": [len(r["asis"]["bqca_agents"] or []) for r in rows],
        })
        print(f"{key:28s} To-Be {summary[-1]['tobe_all_found']}/{len(rows)}  As-Is {summary[-1]['asis_all_found']}/{len(rows)}  "
              f"cells To-Be {summary[-1]['tobe_cells']} As-Is {summary[-1]['asis_cells']}")
    doc = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs_per_question": args.runs,
        "method": "A side counts as a full match when every numeric cell of the reference rows appears in its result table or answer text.",
        "questions": summary,
        "errors": [r for r in all_rows if "error" in r],
        "runs": [r for r in all_rows if "error" not in r],
    }
    OUT_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
