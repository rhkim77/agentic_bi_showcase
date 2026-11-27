#!/usr/bin/env python3
"""Runs the reference prompts of S1-S5 through the live Dual A/B engine and records measured results.

Both pipelines run for real on Google Cloud, exactly as in the portal's live workbench:

  * As-Is: a plain ADK agent using the built-in data agent tools on the monolithic data agent.
  * To-Be: the Root Router with six domain-scoped Sub-Agents and a warehouse-wide fallback Sub-Agent.

What is measured:

  * ADK tier: Vertex AI `usage_metadata` of every LLM call in the run.
  * BQCA tier: `gen_ai.usage.*` of every `generate_content` span that the Conversational Analytics
    service wrote to Cloud Trace for the `:chat` calls of the run. Each chat call is matched to its
    turn by data agent and time window. Requires `roles/cloudtrace.user`.

Nothing in the output is modeled. If a chat call cannot be matched to a trace, the turn is marked
`bqca_basis: "unmatched"` and carries no BQCA numbers.

Output: `benchmarks/scenario_benchmark_results.json`

Usage:
    python scripts/04_run_scenario_benchmarks.py            # all scenarios
    python scripts/04_run_scenario_benchmarks.py --only S4  # re-measure the S4 session, keep the rest
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import google.adk  # noqa: E402
import google.auth  # noqa: E402
from google.auth.transport.requests import AuthorizedSession  # noqa: E402

from agents.bq_caa_3domain_multi_agent.agent import (  # noqa: E402
    BASELINE_CA_ID,
    BQCA_INPUT_CACHED_USD_PER_1M,
    BQCA_INPUT_NON_CACHED_USD_PER_1M,
    BQCA_OUTPUT_USD_PER_1M,
    CUSTOMER_CA_ID,
    DATASET_ID,
    PRODUCT_CA_ID,
    PROJECT_ID,
    SUPPLY_CA_ID,
    VERTEX_FLASH_CACHED_USD_PER_1M,
    VERTEX_FLASH_INPUT_USD_PER_1M,
    VERTEX_FLASH_OUTPUT_USD_PER_1M,
)
from backend.workbench_engine import _comparison, _cost_estimate, reset_visitor_session, stream_dual_ab_scenario  # noqa: E402

OUT_JSON = REPO_ROOT / "benchmarks" / "scenario_benchmark_results.json"
VISITOR = "baseline_run"

# Two extra measured rows on the retail channel tables (static data, 1998 to 2003).
STORE_PROMPT = "For the retail store channel, show net sales and net profit by year."
CROSS_PROMPT = "Compare net profit by year across the retail store, catalog and web channels side by side in one table."

SCENARIOS: list[dict[str, Any]] = [
    {
        "code": "S1",
        "track": "Routing and schema scoping",
        "title": "One monolithic data agent vs. a router with domain-scoped data agents",
        "routing_path": "Root Router -> transfer_to_agent -> domain Sub-Agent -> scoped BQCA data agent",
        "challenge": (
            "The As-Is agent sends every question to one data agent bound to the whole warehouse (32 documented tables) "
            "with the glossary of every domain. BQCA re-reads that schema on each of its internal LLM calls."
        ),
        "architecture_mechanism": (
            "The Root Router hands the question to one of six domain Sub-Agents. Each calls a data agent bound to "
            "3 to 13 tables and its own domain glossary, so the context BQCA has to read per call is smaller. "
            "Tables that must be joined in one query stay in the same data agent."
        ),
        "prompt": "Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days.",
    },
    {
        "code": "S2",
        "track": "Multi-turn context on the stateless chat API",
        "title": "Follow-up question: one message per call vs. a 3-turn message window",
        "routing_path": "Active Sub-Agent -> stateless chat call with the last 3 turns of this domain",
        "challenge": (
            "The built-in `ask_data_agent` tool sends only the current question to BQCA. For a follow-up that refers to "
            "the previous result, the root LLM has to restate the context itself or the data agent has none."
        ),
        "architecture_mechanism": (
            "The Sub-Agent keeps the last 3 question and answer pairs per domain in ADK session state and sends them "
            "with the new question, so BQCA sees the earlier turn without a server-side conversation."
        ),
        "prompt": "Keep those exact columns from the previous result and join our 14-day cart session count and cart abandonment rate (%) for each traffic_source.",
    },
    {
        "code": "S3",
        "track": "Domain switch and parallel fan-out",
        "title": "Switching domain mid-session and asking three domains at once",
        "routing_path": "Sub-Agent -> transfer_to_agent -> other Sub-Agent | Root -> 3 parallel chat calls",
        "challenge": (
            "With one data agent, a domain switch is just another question to the same large context, and a question "
            "spanning several domains is answered in one long call."
        ),
        "architecture_mechanism": (
            "A Sub-Agent can hand over directly to another domain's Sub-Agent. For separate questions about several "
            "domains, the Root Router calls the scoped data agents concurrently and writes one synthesis. A question "
            "whose single result needs tables of several domains goes to a fallback Sub-Agent on the warehouse-wide "
            "data agent, at about the same BQCA input as As-Is."
        ),
        "prompt": "Now pivot to Supply Chain: compare average delivery lead time in days and unsold inventory holding cost ($) across all distribution centers.",
        "fanout_prompt": (
            "Why is Women's Outerwear & Coats realized profit dropping despite strong VIP sales? Run a parallel cross-domain analysis across: "
            "(1) last 30-day VIP orders and gross demand where order_id >= 9900000, "
            "(2) Women's 'Outerwear & Coats' unit margin %, return rate %, and realized profit by brand (order_id >= 9900000), and "
            "(3) recent Women's Outerwear average delivery lead time in days and unsold holding cost by distribution center (order_id >= 9900000)."
        ),
    },
    {
        "code": "S4",
        "track": "Token growth over a long session",
        "title": "Eight consecutive turns: how ADK and BQCA input tokens develop",
        "routing_path": "before_model_callback keeps the last 3 user turns | tool result holds answer and capped table only",
        "challenge": (
            "The As-Is agent replays the full session on every LLM call, including each raw `ask_data_agent` response, "
            "so its ADK prompt grows with the number of turns."
        ),
        "architecture_mechanism": (
            "The To-Be agents keep the last 3 user turns in the prompt, store only the answer and a capped table from "
            "each data call, and end single-domain turns on the tool result without a second summarization call."
        ),
        "prompt": "Compare average delivery lead time in days and unsold inventory holding cost ($) by distribution center for Women's Outerwear (order_id >= 9900000).",
        # Eight different questions. A question that repeats an earlier one lets the As-Is agent answer
        # from its own session history without calling BQCA, which measures something else.
        # Turns 5 to 8 move through the three retail channel domains.
        "append_prompts": [
            "For the retail catalog channel, show net profit by call center name and ship mode type.",
            "For the retail catalog channel, show the average inventory quantity on hand by warehouse name.",
            "For the retail store channel, show net profit by shopper education status and household income band.",
            "For the retail web channel, show net sales, net profit and return amount by web site name.",
        ],
    },
    {
        "code": "S5",
        "track": "Session state and cross-session memory",
        "title": "A brand-new session asks about earlier work",
        "routing_path": "New session -> Root Router -> inspect_session_and_memory_status (no BQCA call)",
        "challenge": (
            "The As-Is agent has no memory across sessions. In a new session it cannot refer to earlier findings; the "
            "analysis has to be asked again."
        ),
        "architecture_mechanism": (
            "The To-Be Root Router keeps the user profile and pinned insights in user-scoped state and a memory service, "
            "and answers recall questions from them without calling BQCA."
        ),
        "prompt": "This is a new session. Without running any BigQuery SQL, inspect my saved profile and long-term memory, summarize what we found in my earlier session, and give 2 concrete next steps.",
    },
]


async def run_step(code: str, prompt: str, mode: str = "burst") -> dict[str, Any]:
    payload = None
    async for chunk in stream_dual_ab_scenario(VISITOR, code, prompt, mode):
        evt = json.loads(chunk[6:])
        if evt["type"] == "progress":
            print(f"    [{evt['side']}] {evt['detail'][:160]}", flush=True)
        elif evt["type"] == "error":
            raise RuntimeError(f"{code}: {evt['message']}")
        elif evt["type"] == "complete":
            payload = evt["payload"]
    if payload is None:
        raise RuntimeError(f"{code}: stream ended without a result")
    for side in ("asis", "tobe"):
        if payload[side]["errors"]:
            print(f"    !! {side} errors: {payload[side]['errors']}")
    return payload


def fetch_chat_traces(since: datetime) -> list[dict[str, Any]]:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(PROJECT_ID)
    sess = AuthorizedSession(creds)
    params: dict[str, Any] = {
        "startTime": (since - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "view": "COMPLETE",
        "pageSize": 200,
        "filter": "span:generate_content",
    }
    traces: list[dict[str, Any]] = []
    while True:
        body = sess.get(f"https://cloudtrace.googleapis.com/v1/projects/{PROJECT_ID}/traces", params=params, timeout=90).json()
        for tr in body.get("traces", []):
            agent, start, calls = "", "", []
            for sp in sorted(tr.get("spans", []), key=lambda x: x["startTime"]):
                labels = sp.get("labels", {})
                agent = agent or labels.get("gen_ai.agent.id", "") or labels.get("gen_ai.agent.name", "")
                if sp["name"].startswith("google.cloud.geminidataanalytics.Chat"):
                    start = sp["startTime"]
                if sp["name"].startswith("generate_content"):
                    calls.append((
                        int(labels.get("gen_ai.usage.input_tokens", 0) or 0),
                        int(labels.get("gen_ai.usage.cache_read.input_tokens", 0) or 0),
                        int(labels.get("gen_ai.usage.output_tokens", 0) or 0),
                    ))
            if calls and start:
                traces.append({
                    "trace_id": tr["traceId"],
                    "agent": agent.rsplit("/", 1)[-1],
                    "start": datetime.fromisoformat(start.replace("Z", "+00:00")[:26] + "+00:00" if "." in start else start.replace("Z", "+00:00")),
                    "input_tokens": sum(c[0] for c in calls),
                    "cached_input_tokens": sum(c[1] for c in calls),
                    "output_tokens": sum(c[2] for c in calls),
                    "llm_calls": len(calls),
                    "used": False,
                })
        if not body.get("nextPageToken"):
            break
        params["pageToken"] = body["nextPageToken"]
    return traces


def match(
    traces: list[dict[str, Any]],
    agents: list[str],
    window: list[str | None],
    call_starts: list[str | None] | None = None,
) -> dict[str, Any] | None:
    """Sums the Cloud Trace usage of the chat calls a turn made. None unless every call is found.

    When the start time of each call is known (To-Be records it), a call takes the trace of its data agent
    that started closest to it. Both pipelines can call the same data agent in the same turn (the To-Be
    fallback and As-Is both use the warehouse-wide agent), so To-Be is matched first and As-Is takes the rest.
    """
    if not agents:
        return {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "llm_calls": 0}
    if not window or not window[0] or not window[1]:
        return None
    lo = datetime.fromisoformat(window[0]) - timedelta(seconds=3)
    hi = datetime.fromisoformat(window[1]) + timedelta(seconds=3)
    total = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "llm_calls": 0}
    for idx, agent in enumerate(agents):
        pool = [t for t in sorted(traces, key=lambda x: x["start"]) if not t["used"] and t["agent"] == agent and lo <= t["start"] <= hi]
        started = call_starts[idx] if call_starts and idx < len(call_starts) and call_starts[idx] else None
        if started and pool:
            ref = datetime.fromisoformat(started)
            pool.sort(key=lambda t: abs((t["start"] - ref).total_seconds()))
        hit = pool[0] if pool else None
        if hit is None:
            return None
        hit["used"] = True
        for k in total:
            total[k] += hit[k]
    return total


def apply_measured(payload: dict[str, Any], traces: list[dict[str, Any]]) -> None:
    for side in ("tobe", "asis"):
        s = payload[side]
        measured = match(traces, s["bqca_agents"], [s.get("started_at_utc"), s.get("ended_at_utc")], s.get("bqca_call_started_utc"))
        if measured is None:
            s["bqca_trace_estimate"], s["cost_estimate_usd"], s["bqca_basis"] = None, None, "unmatched"
        else:
            s["bqca_trace_estimate"] = measured
            s["cost_estimate_usd"] = _cost_estimate(s["adk_usage"], measured)
            s["bqca_basis"] = "measured"
    payload["comparison_summary"] = _comparison(payload["asis"], payload["tobe"])
    payload["bqca_basis"] = "measured" if all(payload[x]["bqca_basis"] == "measured" for x in ("asis", "tobe")) else "unmatched"
    payload.pop("calibration", None)  # medians are for live runs; this run carries its own measured values


def turn_cost(adk_prompt: int, adk_cached: int, adk_out: int, bq: dict[str, Any]) -> float:
    adk = ((adk_prompt - adk_cached) * VERTEX_FLASH_INPUT_USD_PER_1M + adk_cached * VERTEX_FLASH_CACHED_USD_PER_1M + adk_out * VERTEX_FLASH_OUTPUT_USD_PER_1M) / 1e6
    bqca = ((bq["input_tokens"] - bq["cached_input_tokens"]) * BQCA_INPUT_NON_CACHED_USD_PER_1M + bq["cached_input_tokens"] * BQCA_INPUT_CACHED_USD_PER_1M + bq["output_tokens"] * BQCA_OUTPUT_USD_PER_1M) / 1e6
    return round(adk + bqca, 5)


def wait_for_traces(run_started: datetime, expected: int) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for attempt in range(10):
        time.sleep(30)
        traces = fetch_chat_traces(run_started)
        print(f"Cloud Trace: {len(traces)} chat trace(s) found, {expected} expected (attempt {attempt + 1})")
        if len(traces) >= expected:
            break
    return traces


async def run_s4(spec: dict[str, Any]) -> dict[str, Any]:
    print("[S4] 3 warm-up turns + reference prompt")
    payload = await run_step("S4", spec["prompt"], "burst")
    for p in spec["append_prompts"]:
        print("[S4] appended turn")
        payload = await run_step("S4", p, "append")
    return payload


def finalize_s4(s4: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Attaches measured BQCA usage to every S4 turn and returns the per-turn average."""
    curve = s4["turn_curve"]
    for row in curve:
        b = match(traces, row["tobe_bqca_agents"], row["tobe_window_utc"], row.get("tobe_bqca_call_started_utc"))
        a = match(traces, row["asis_bqca_agents"], row["asis_window_utc"])
        row["bqca_basis"] = "measured" if a is not None and b is not None else "unmatched"
        if a is not None and b is not None:
            row["asis_bqca"], row["tobe_bqca"] = a, b
            row["asis_total_input_tokens"] = row["asis_adk_prompt_tokens"] + a["input_tokens"]
            row["tobe_total_input_tokens"] = row["tobe_adk_prompt_tokens"] + b["input_tokens"]
            row["asis_cost_usd"] = turn_cost(row["asis_adk_prompt_tokens"], row["asis_adk_cached_tokens"], row["asis_adk_output_tokens"], a)
            row["tobe_cost_usd"] = turn_cost(row["tobe_adk_prompt_tokens"], row["tobe_adk_cached_tokens"], row["tobe_adk_output_tokens"], b)
    last = curve[-1]
    for side in ("asis", "tobe"):
        measured = last.get(f"{side}_bqca")
        s4[side]["bqca_trace_estimate"] = measured
        s4[side]["cost_estimate_usd"] = _cost_estimate(s4[side]["adk_usage"], measured) if measured else None
        s4[side]["bqca_basis"] = "measured" if measured else "unmatched"
    s4["comparison_summary"] = _comparison(s4["asis"], s4["tobe"])
    s4["bqca_basis"] = last["bqca_basis"]
    s4.pop("calibration", None)
    rows = [r for r in curve if r["bqca_basis"] == "measured"]
    n = len(rows)
    return {
        "turns_measured": n,
        "asis_total_input_tokens": int(sum(r["asis_total_input_tokens"] for r in rows) / n) if n else None,
        "tobe_total_input_tokens": int(sum(r["tobe_total_input_tokens"] for r in rows) / n) if n else None,
        "asis_adk_prompt_tokens": int(sum(r["asis_adk_prompt_tokens"] for r in rows) / n) if n else None,
        "tobe_adk_prompt_tokens": int(sum(r["tobe_adk_prompt_tokens"] for r in rows) / n) if n else None,
        "asis_cost_usd": round(sum(r["asis_cost_usd"] for r in rows) / n, 5) if n else None,
        "tobe_cost_usd": round(sum(r["tobe_cost_usd"] for r in rows) / n, 5) if n else None,
        "asis_bqca_calls": sum(len(r["asis_bqca_agents"]) for r in curve),
        "tobe_bqca_calls": sum(len(r["tobe_bqca_agents"]) for r in curve),
    }


def curve_calls(curve: list[dict[str, Any]]) -> int:
    return sum(len(r["asis_bqca_agents"]) + len(r["tobe_bqca_agents"]) for r in curve)


def print_summary(doc: dict[str, Any]) -> None:
    for s in doc["scenarios"]:
        m = s["result"]["comparison_summary"]["measured"]
        t = s["result"]["comparison_summary"]["trace_estimate"] or {}
        print(
            f"  {s['code']} [{s['result']['bqca_basis']}] ADK prompt To-Be {m['tobe_adk_prompt_tokens']:,} vs As-Is {m['asis_adk_prompt_tokens']:,} | "
            f"BQCA input To-Be {t.get('tobe_bqca_input_tokens')} vs As-Is {t.get('asis_bqca_input_tokens')} | total delta {t.get('total_input_delta_pct')}% | "
            f"BQCA calls {m['tobe_bqca_calls']} vs {m['asis_bqca_calls']}"
        )
    print("  S4 average per turn:", doc["s4_average_per_turn"])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["S4"], default=None, help="Re-measure only this scenario and keep the others.")
    args = ap.parse_args()
    run_started = datetime.now(timezone.utc)
    spec = {s["code"]: s for s in SCENARIOS}
    print(f"Measured baseline on {PROJECT_ID}.{DATASET_ID} (google-adk {google.adk.__version__})")
    await reset_visitor_session(VISITOR)

    if args.only == "S4":
        doc = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        s4 = await run_s4(spec["S4"])
        traces = wait_for_traces(run_started, curve_calls(s4["turn_curve"]))
        doc["s4_average_per_turn"] = finalize_s4(s4, traces)
        doc["s4_turn_curve"] = s4["turn_curve"]
        doc["s4_measured_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for sc in doc["scenarios"]:
            if sc["code"] == "S4":
                sc.update({k: v for k, v in spec["S4"].items() if k != "append_prompts"})
                sc["result"] = s4
        OUT_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"\nUpdated S4 in {OUT_JSON}")
        print_summary(doc)
        return

    results: dict[str, dict[str, Any]] = {}
    extra: dict[str, dict[str, Any]] = {}
    print("[S1 store channel]")
    extra["S1"] = {"store_channel": await run_step("S1", STORE_PROMPT)}
    for code in ("S1", "S2", "S3"):
        print(f"[{code}]")
        results[code] = await run_step(code, spec[code]["prompt"])
    print("[S3 fan-out]")
    extra["S3"] = {"fanout": await run_step("S3", spec["S3"]["fanout_prompt"])}
    print("[S3 cross-channel, warehouse-wide fallback]")
    extra["S3"]["cross_channel"] = await run_step("S3", CROSS_PROMPT)
    print("[S5]")
    results["S5"] = await run_step("S5", spec["S5"]["prompt"])
    results["S4"] = await run_s4(spec["S4"])

    s4 = results["S4"]
    others = [p for p in list(results.values()) + [x for group in extra.values() for x in group.values()] if p is not s4]
    expected = sum(len(p[side]["bqca_agents"]) for p in others for side in ("asis", "tobe")) + curve_calls(s4["turn_curve"])
    traces = wait_for_traces(run_started, expected)
    s4_average = finalize_s4(s4, traces)  # S4 first: its turns own their chat calls
    for p in others:
        apply_measured(p, traces)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = {
        "schema_version": 2,
        "generated_at_utc": now_utc,
        "s4_measured_at_utc": now_utc,
        "environment": {
            "gcp_project": PROJECT_ID,
            "bigquery_dataset": f"{PROJECT_ID}.{DATASET_ID}",
            "adk_model": "gemini-2.5-flash",
            "adk_version": google.adk.__version__,
            "caa_endpoint": "geminidataanalytics.googleapis.com/v1",
            "asis_data_agent": BASELINE_CA_ID,
            "tobe_data_agents": [CUSTOMER_CA_ID, PRODUCT_CA_ID, SUPPLY_CA_ID],
            "list_prices_usd_per_1m": {
                "bqca_input": BQCA_INPUT_NON_CACHED_USD_PER_1M,
                "bqca_cached_input": BQCA_INPUT_CACHED_USD_PER_1M,
                "bqca_output": BQCA_OUTPUT_USD_PER_1M,
                "adk_flash_input": VERTEX_FLASH_INPUT_USD_PER_1M,
                "adk_flash_cached_input": VERTEX_FLASH_CACHED_USD_PER_1M,
                "adk_flash_output": VERTEX_FLASH_OUTPUT_USD_PER_1M,
            },
        },
        "scenarios": [
            {**{k: v for k, v in s.items() if k not in ("fanout_prompt", "append_prompts")}, "result": results[s["code"]], **extra.get(s["code"], {})}
            for s in SCENARIOS
        ],
        "s4_turn_curve": s4["turn_curve"],
        "s4_average_per_turn": s4_average,
    }
    OUT_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nWrote {OUT_JSON}")
    print_summary(doc)


if __name__ == "__main__":
    asyncio.run(main())
