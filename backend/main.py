"""FastAPI server for the PoC Architecture portal and the live S1-S5 Dual A/B Workbench.

Serves:
  - `/`, `/index.html`            English portal
  - `/ko`, `/index_ko.html`       Korean portal
  - `/diagrams/*`                 Architecture diagrams
  - `/api/health`, `/api/version`
  - `/api/benchmarks`             Pre-run baseline dataset
  - `POST /api/workbench/stream`  Live Dual A/B run (SSE): As-Is and To-Be on the evaluator's prompt
  - `POST /api/workbench/reset`   Resets an evaluator's isolated sessions and memory
  - `POST /api/verify-scenario`   Single-click re-run of the reference prompts
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from agents.bq_caa_3domain_multi_agent.agent import (
    ADK_USAGE_COLLECTOR_VAR,
    CAA_CALL_COLLECTOR_VAR,
    CUSTOMER_CA_ID,
    DATASET_ID,
    DOMAIN_CATALOG_METADATA,
    PROJECT_ID,
    _query_domain_caa_agent,
    load_bqca_trace_calibration,
    root_agent,
    run_cross_domain_caa_analysis_sync,
)
from backend.workbench_engine import reset_visitor_session, stream_dual_ab_scenario

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DIAGRAMS_DIR = DOCS_DIR / "diagrams"
BENCHMARK_JSON = REPO_ROOT / "benchmarks" / "scenario_benchmark_results.json"

app = FastAPI(
    title="Google ADK + BigQuery CAA Multi-Agent Architecture & Live Dual A/B Workbench",
    version="4.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if DIAGRAMS_DIR.exists():
    app.mount("/diagrams", StaticFiles(directory=str(DIAGRAMS_DIR)), name="diagrams")
    app.mount("/docs/diagrams", StaticFiles(directory=str(DIAGRAMS_DIR)), name="docs_diagrams")


class LiveVerifyRequest(BaseModel):
    scenario_code: str = "S1"


class WorkbenchStreamRequest(BaseModel):
    visitor_id: str = Field(default="default_eval", max_length=64)
    scenario_code: str = Field(default="S1", max_length=8)
    prompt: str = Field(..., min_length=2, max_length=600)
    s4_mode: str = Field(default="burst", max_length=32)


class WorkbenchResetRequest(BaseModel):
    visitor_id: str = Field(default="default_eval", max_length=64)


def _trace_median_input(agent_ids: list[str]) -> int | None:
    """Cloud Trace median BQCA input tokens per chat turn, summed over the agents called."""
    cal = load_bqca_trace_calibration().get("per_data_agent", {})
    if not agent_ids or any(a not in cal for a in agent_ids):
        return None
    return sum(int(cal[a]["median_input_tokens_per_turn"]) for a in agent_ids)


async def _measure_adk_runner_turn(prompt: str) -> tuple[str, int, int, int, int]:
    """Runs `root_agent` once. Returns (text, prompt_tokens, output_tokens, elapsed_ms, bqca_calls), all measured."""
    sess_svc = InMemorySessionService()
    mem_svc = InMemoryMemoryService()
    runner = Runner(app_name="live_verify", agent=root_agent, session_service=sess_svc, memory_service=mem_svc)
    await sess_svc.create_session(app_name="live_verify", user_id="analyst_01", session_id="live-sess")
    bucket: list[dict[str, Any]] = []
    caa_calls: list[dict[str, Any]] = []
    tok = ADK_USAGE_COLLECTOR_VAR.set(bucket)
    tok_caa = CAA_CALL_COLLECTOR_VAR.set(caa_calls)
    t0 = time.monotonic()
    texts: list[str] = []
    try:
        msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        async for ev in runner.run_async(user_id="analyst_01", session_id="live-sess", new_message=msg):
            if ev.is_final_response() and ev.content and ev.content.parts:
                t = "\n".join(p.text for p in ev.content.parts if getattr(p, "text", None)).strip()
                if t:
                    texts.append(t)
    finally:
        ADK_USAGE_COLLECTOR_VAR.reset(tok)
        CAA_CALL_COLLECTOR_VAR.reset(tok_caa)
    ms = int((time.monotonic() - t0) * 1000)
    p_tok = sum(int(r["prompt_token_count"]) for r in bucket)
    o_tok = sum(int(r["output_and_thoughts_token_count"]) for r in bucket)
    return "\n\n".join(texts).strip(), p_tok, o_tok, ms, len(caa_calls)


@app.get("/api/health")
async def api_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "project_id": PROJECT_ID,
        "dataset_id": DATASET_ID,
        "scoped_agents": [d["caa_agent_id"] for d in DOMAIN_CATALOG_METADATA],
        "workbench_dual_ab_sse": True,
    }


@app.get("/api/version")
async def api_version() -> dict[str, Any]:
    return {
        "repository": "https://github.com/rhkim77/agentic_bi_showcase",
        "version": "4.1.0",
        "adk_model": "gemini-2.5-flash",
        "caa_api": "geminidataanalytics.googleapis.com/v1",
        "execution_mode": "full_live_dual_run_sse",
    }


@app.get("/api/benchmarks")
async def api_benchmarks() -> JSONResponse:
    if BENCHMARK_JSON.is_file():
        return JSONResponse(json.loads(BENCHMARK_JSON.read_text(encoding="utf-8")))
    return JSONResponse({"error": "Benchmark JSON not generated yet."}, status_code=404)


@app.post("/api/workbench/stream")
async def api_workbench_stream(req: WorkbenchStreamRequest) -> StreamingResponse:
    """Streams a live As-Is vs To-Be run (SSE) for the evaluator's prompt in scenario S1..S5."""
    return StreamingResponse(
        stream_dual_ab_scenario(
            visitor_id=req.visitor_id,
            scenario_code=req.scenario_code,
            custom_prompt=req.prompt,
            s4_mode=req.s4_mode,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/workbench/reset")
async def api_workbench_reset(req: WorkbenchResetRequest) -> dict[str, Any]:
    return await reset_visitor_session(req.visitor_id)


@app.post("/api/verify-scenario")
async def api_verify_scenario(req: LiveVerifyRequest) -> dict[str, Any]:
    """Re-runs the reference prompt of a scenario on the To-Be side only.

    S1-S3 call the scoped BQCA agents directly, so no ADK tier runs and no ADK tokens are reported.
    BQCA tokens are never measured per call; the Cloud Trace median per chat turn is reported instead.
    """
    code = req.scenario_code.upper()
    t0 = time.monotonic()
    direct_basis = "Direct BQCA call, no ADK tier. BQCA tokens: Cloud Trace median per chat turn, not measured for this call."

    if code in ("S1", "S2"):
        prior = None
        query = "Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days."
        if code == "S2":
            first = await asyncio.to_thread(
                _query_domain_caa_agent,
                agent_id=CUSTOMER_CA_ID,
                domain_id="customer_marketing",
                domain_label="Domain 1: Customer CRM & Marketing Funnel",
                query=query,
            )
            prior = [
                {"userMessage": {"text": query}},
                {"systemMessage": {"text": {"parts": [(first.get("ca_final_answer") or "")[:900]]}}},
            ]
            query = "For those exact customer cohorts and acquisition channels from our previous query, add their 14-day cart session count and cart abandonment rate (%) side-by-side."
        res = await asyncio.to_thread(
            _query_domain_caa_agent,
            agent_id=CUSTOMER_CA_ID,
            domain_id="customer_marketing",
            domain_label="Domain 1: Customer CRM & Marketing Funnel",
            query=query,
            prior_messages_override=prior,
        )
        return {
            "status": res.get("status"),
            "error_details": res.get("error_details"),
            "scenario_code": code,
            "live_latency_ms": res.get("latency_ms") or int((time.monotonic() - t0) * 1000),
            "adk_measured_prompt_tokens": None,
            "bqca_calls": 2 if code == "S2" else 1,
            "bqca_trace_median_input_tokens": _trace_median_input([CUSTOMER_CA_ID]),
            "token_basis": direct_basis,
            "generated_sql": res.get("generated_sql"),
            "markdown_table": res.get("markdown_table"),
            "answer": res.get("ca_final_answer"),
        }

    if code == "S3":
        fan = await asyncio.to_thread(
            run_cross_domain_caa_analysis_sync,
            "Count distinct VIP orders and total gross demand ($) in the last 30 days where order_id >= 9900000.",
            "For Women's 'Outerwear & Coats' (order_id >= 9900000), compare unit gross margin %, return and cancellation rate %, and realized gross profit ($) by brand.",
            "For recent Women's Outerwear orders (order_id >= 9900000), compare average delivery lead time in days and unsold inventory holding cost ($) by distribution center.",
        )
        wall_ms = int((time.monotonic() - t0) * 1000)
        dmap = fan.get("domain_results", {})
        agent_ids = [str(v.get("data_agent", "")).rsplit("/", 1)[-1] for v in dmap.values()]
        failed = [k for k, v in dmap.items() if v.get("status") != "SUCCESS"]
        return {
            "status": "ERROR" if failed else fan.get("status"),
            "error_details": "; ".join(f"{k}: {dmap[k].get('error_details')}" for k in failed) or None,
            "scenario_code": "S3",
            "live_latency_ms": wall_ms,
            "sum_of_call_latencies_ms": sum(int(v.get("latency_ms", 0)) for v in dmap.values()),
            "adk_measured_prompt_tokens": None,
            "bqca_calls": len(dmap),
            "bqca_trace_median_input_tokens": _trace_median_input(agent_ids),
            "token_basis": direct_basis,
            "generated_sql": "\n\n".join(f"-- [{k}]\n{v.get('generated_sql', '')}" for k, v in dmap.items()),
            "markdown_table": "",
            "answer": "\n\n".join(f"**{k}**: {v.get('ca_final_answer', '')[:320]}" for k, v in dmap.items()),
        }

    ans, p_tok, o_tok, ms, bqca_calls = await _measure_adk_runner_turn(
        "Without running BigQuery SQL, inspect my saved analyst profile and memory status, "
        "and summarize the Nordic Luxe / Memphis TN DC #1 root-cause finding in 2 concise bullets."
    )
    return {
        "status": "SUCCESS",
        "scenario_code": code,
        "live_latency_ms": ms,
        "adk_measured_prompt_tokens": p_tok,
        "adk_measured_output_tokens": o_tok,
        "bqca_calls": bqca_calls,
        "bqca_trace_median_input_tokens": None,
        "token_basis": f"ADK tier measured from Vertex AI usage_metadata on a fresh session with no saved memory. BQCA calls made: {bqca_calls}.",
        "generated_sql": "",
        "markdown_table": "",
        "answer": ans,
    }


@app.get("/")
@app.get("/index.html")
async def serve_portal_index():
    index_file = DOCS_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return JSONResponse({"error": "docs/index.html not built yet."}, status_code=404)


@app.get("/ko")
@app.get("/index_ko.html")
async def serve_portal_index_ko():
    index_ko_file = DOCS_DIR / "index_ko.html"
    if index_ko_file.is_file():
        return FileResponse(str(index_ko_file))
    return JSONResponse({"error": "docs/index_ko.html not built yet."}, status_code=404)


@app.get("/ko/")
async def redirect_ko_slash():
    return RedirectResponse(url="/ko")
