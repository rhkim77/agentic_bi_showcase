#!/usr/bin/env python3
"""Measures real BigQuery CAA token usage per Data Agent from Cloud Trace.

The Conversational Analytics `:chat` API does not return token usage, but each chat turn writes
OpenTelemetry spans to Cloud Trace. Every `generate_content` span carries `gen_ai.usage.*`
attributes. This script sums those per chat turn (one trace = one `:chat` call), groups the turns
by Data Agent, and writes medians to `benchmarks/bqca_trace_token_calibration.json`.

Requires `roles/cloudtrace.user` on the project. Read-only.

Usage:
    python scripts/05_measure_bqca_tokens_from_trace.py [--hours 48] [--since 2026-11-26T02:37:00Z]

Use `--since` after re-provisioning data agents so that only turns of the current configuration count.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import statistics
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "ryan-sandbox-agent") or "ryan-sandbox-agent"
OUT_JSON = Path(__file__).resolve().parent.parent / "benchmarks" / "bqca_trace_token_calibration.json"


def _int(labels: dict[str, str], key: str) -> int:
    try:
        return int(labels.get(key, 0) or 0)
    except ValueError:
        return 0


def fetch_chat_turns(hours: int, since: str | None = None) -> list[dict[str, Any]]:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(PROJECT_ID)
    sess = AuthorizedSession(creds)
    now = datetime.now(timezone.utc)
    params: dict[str, Any] = {
        "startTime": since or (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "view": "COMPLETE",
        "pageSize": 200,
        "filter": "span:generate_content",
    }
    turns: list[dict[str, Any]] = []
    while True:
        resp = sess.get(f"https://cloudtrace.googleapis.com/v1/projects/{PROJECT_ID}/traces", params=params, timeout=90)
        resp.raise_for_status()
        body = resp.json()
        for tr in body.get("traces", []):
            agent_id = ""
            messages_hint = ""
            start_time = ""
            in_tok = cached_tok = out_tok = llm_calls = bq_bytes = 0
            is_chat = False
            for sp in tr.get("spans", []):
                labels = sp.get("labels", {})
                name = sp.get("name", "")
                if name.startswith("google.cloud.geminidataanalytics.Chat"):
                    is_chat = True
                    start_time = sp.get("startTime", "")
                agent_id = agent_id or labels.get("gen_ai.agent.id", "") or labels.get("gen_ai.agent.name", "")
                messages_hint = messages_hint or labels.get("gcp.geminidataanalytics.data_sources", "")
                bq_bytes = max(bq_bytes, _int(labels, "gcp.geminidataanalytics.bq_bytes_processed"))
                if name.startswith("generate_content"):
                    llm_calls += 1
                    in_tok += _int(labels, "gen_ai.usage.input_tokens")
                    cached_tok += _int(labels, "gen_ai.usage.cache_read.input_tokens")
                    out_tok += _int(labels, "gen_ai.usage.output_tokens")
            if is_chat and llm_calls:
                turns.append({
                    "trace_id": tr.get("traceId"),
                    "start_time": start_time,
                    "data_agent": agent_id or "unknown",
                    "data_sources": messages_hint,
                    "llm_calls": llm_calls,
                    "input_tokens": in_tok,
                    "cached_input_tokens": cached_tok,
                    "output_tokens": out_tok,
                    "bq_bytes_processed": bq_bytes,
                })
        token = body.get("nextPageToken")
        if not token:
            break
        params["pageToken"] = token
    return turns


def summarize(turns: list[dict[str, Any]]) -> dict[str, Any]:
    by_agent: dict[str, list[dict[str, Any]]] = {}
    for t in turns:
        by_agent.setdefault(t["data_agent"].rsplit("/", 1)[-1], []).append(t)
    out: dict[str, Any] = {}
    for agent, rows in sorted(by_agent.items()):
        ins = [r["input_tokens"] for r in rows]
        out[agent] = {
            "chat_turns_sampled": len(rows),
            "median_input_tokens_per_turn": int(statistics.median(ins)),
            "min_input_tokens_per_turn": min(ins),
            "max_input_tokens_per_turn": max(ins),
            "median_cached_input_tokens_per_turn": int(statistics.median(r["cached_input_tokens"] for r in rows)),
            "median_output_tokens_per_turn": int(statistics.median(r["output_tokens"] for r in rows)),
            "median_llm_calls_per_turn": statistics.median(r["llm_calls"] for r in rows),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--since", type=str, default=None, help="UTC start time, e.g. 2026-11-26T02:37:00Z")
    args = ap.parse_args()
    turns = fetch_chat_turns(args.hours, args.since)
    doc = {
        "measured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Cloud Trace generate_content spans (gen_ai.usage.*), one trace per :chat call",
        "gcp_project": PROJECT_ID,
        "window_hours": args.hours,
        "window_since_utc": args.since,
        "total_chat_turns": len(turns),
        "per_data_agent": summarize(turns),
    }
    OUT_JSON.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps(doc, indent=2))


if __name__ == "__main__":
    main()
