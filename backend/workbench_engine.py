"""Live S1-S5 Dual A/B Workbench engine (SSE, per-visitor isolation).

For each evaluator prompt this runs two pipelines against live Google Cloud at the same time:

  * To-Be:  `root_agent` (Root Router + 3 domain Sub-Agents, sliding window, compaction, memory).
  * As-Is:  a plain `LlmAgent` using ADK's built-in data agent tools
            (`list_accessible_data_agents`, `get_data_agent_info`, `ask_data_agent`) against the
            single monolithic data agent. The tools are the real ADK implementations; only the
            credentials are injected (ADC with the `cloud-platform` scope).

What is measured and what is not:

  * Measured per run: ADK-tier `usage_metadata` tokens, latency, number of BQCA `:chat` calls,
    messages sent per call, tool-response size, generated SQL and answers.
  * Not measured per run: BQCA-tier tokens. The `:chat` API returns no token usage. The engine
    reports the Cloud Trace median per chat turn for each data agent, taken from
    `benchmarks/bqca_trace_token_calibration.json` (see `scripts/05_measure_bqca_tokens_from_trace.py`).

The As-Is pipeline runs in its own thread and event loop because ADK calls sync tools on the event
loop, and the built-in data agent tools are sync and block for the whole `:chat` call.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import time
from typing import Any, AsyncIterator

import google.adk
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.memory import InMemoryMemoryService
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.data_agent import data_agent_tool
from google.adk.tools.data_agent.config import DataAgentToolConfig
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from agents.bq_caa_3domain_multi_agent.agent import (
    ADK_USAGE_COLLECTOR_VAR,
    BASELINE_CA_ID,
    BQCA_INPUT_CACHED_USD_PER_1M,
    BQCA_INPUT_NON_CACHED_USD_PER_1M,
    BQCA_OUTPUT_USD_PER_1M,
    CAA_CALL_COLLECTOR_VAR,
    DATASET_ID,
    PROJECT_ID,
    VERTEX_FLASH_CACHED_USD_PER_1M,
    VERTEX_FLASH_INPUT_USD_PER_1M,
    VERTEX_FLASH_OUTPUT_USD_PER_1M,
    VISITOR_ID_VAR,
    _get_cloud_platform_adc,
    adk_app,
    load_bqca_trace_calibration,
    reset_persistent_memory_store,
    root_agent,
)

MAX_PROMPT_CHARS = 600
MAX_VISITORS_CACHE = 120
VISITOR_TTL_SECONDS = 7200
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX_CALLS = 8

ASIS_APP_NAME = "asis_default_data_agent_tools"
BASELINE_AGENT_RESOURCE = f"projects/{PROJECT_ID}/locations/global/dataAgents/{BASELINE_CA_ID}"

TURN1_PROMPT = (
    "Show VIP customer count, total gross revenue, and average order value (AOV) "
    "by acquisition traffic source over the last 30 days."
)
S4_WARMUP_PROMPTS = [
    "Show VIP customer count and total gross revenue by traffic source over the last 30 days.",
    "Add the average order value (AOV) for each of those traffic sources.",
    "Now show the 14-day cart abandonment rate (%) by traffic source.",
]
S5_SEED_PROMPT = (
    "Save my profile role as 'Principal Supply Chain & Merchandising Analyst' focusing on "
    "'Women Outerwear Margin & DC Lead Time', and pin this insight: "
    "'Nordic Luxe 50.0% return rate is driven by a 6.0-day shipping delay at Memphis TN DC #1.'"
)

_ASIS_TOOL_SETTINGS = DataAgentToolConfig(max_query_result_rows=50, location="global")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_visitor_id(raw: str | None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", str(raw or ""))[:48]
    return cleaned or "default_eval"


# --------------------------------------------------------------------------------------------
# As-Is agent: ADK built-in data agent tools with ADC injected
# --------------------------------------------------------------------------------------------
def list_accessible_data_agents(project_id: str) -> dict[str, Any]:
    return data_agent_tool.list_accessible_data_agents(
        project_id=project_id,
        credentials=_get_cloud_platform_adc(),
        settings=_ASIS_TOOL_SETTINGS,
    )


def get_data_agent_info(data_agent_name: str) -> dict[str, Any]:
    return data_agent_tool.get_data_agent_info(
        data_agent_name=data_agent_name,
        credentials=_get_cloud_platform_adc(),
        settings=_ASIS_TOOL_SETTINGS,
    )


def ask_data_agent(data_agent_name: str, query: str, tool_context: ToolContext) -> dict[str, Any]:
    return data_agent_tool.ask_data_agent(
        data_agent_name=data_agent_name,
        query=query,
        credentials=_get_cloud_platform_adc(),
        settings=_ASIS_TOOL_SETTINGS,
        tool_context=tool_context,
    )


# The model sees the same tool descriptions it would see with the built-in toolset.
list_accessible_data_agents.__doc__ = data_agent_tool.list_accessible_data_agents.__doc__
get_data_agent_info.__doc__ = data_agent_tool.get_data_agent_info.__doc__
ask_data_agent.__doc__ = data_agent_tool.ask_data_agent.__doc__


def _asis_usage_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    """Records Vertex AI `usage_metadata` for the As-Is agent. Measurement only; changes nothing."""
    if getattr(llm_response, "partial", False):
        return None
    um = getattr(llm_response, "usage_metadata", None)
    collector = ADK_USAGE_COLLECTOR_VAR.get()
    if um is None or collector is None:
        return None
    prompt_tok = int(getattr(um, "prompt_token_count", 0) or 0)
    cand_tok = int(getattr(um, "candidates_token_count", 0) or 0)
    thought_tok = int(getattr(um, "thoughts_token_count", 0) or 0)
    collector.append({
        "agent_name": getattr(callback_context, "agent_name", ASIS_APP_NAME),
        "prompt_token_count": prompt_tok,
        "cached_content_token_count": int(getattr(um, "cached_content_token_count", 0) or 0),
        "candidates_token_count": cand_tok,
        "thoughts_token_count": thought_tok,
        "output_and_thoughts_token_count": cand_tok + thought_tok,
        "total_token_count": int(getattr(um, "total_token_count", 0) or (prompt_tok + cand_tok + thought_tok)),
        "compacted_contents_dropped": 0,
    })
    return None


def _build_asis_agent() -> LlmAgent:
    # A fresh model object per run: its HTTP client must belong to the thread's own event loop.
    return LlmAgent(
        model=Gemini(model="gemini-2.5-flash"),
        name=ASIS_APP_NAME,
        instruction=(
            "You are a BI analytics assistant for Cymbal Global Commerce. Answer data questions with the "
            f"data agent tools. The organization's data agent is `{BASELINE_AGENT_RESOURCE}`, which covers "
            f"the whole enterprise warehouse `{PROJECT_ID}.{DATASET_ID}`."
        ),
        tools=[list_accessible_data_agents, get_data_agent_info, ask_data_agent],
        after_model_callback=_asis_usage_callback,
    )


# --------------------------------------------------------------------------------------------
# Running one turn and reading what happened
# --------------------------------------------------------------------------------------------
def _summarize_adk_usage(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "llm_calls": len(records),
        "agents_invoked": [r["agent_name"] for r in records],
        "prompt_tokens": sum(int(r["prompt_token_count"]) for r in records),
        "cached_tokens": sum(int(r["cached_content_token_count"]) for r in records),
        "output_and_thoughts_tokens": sum(int(r["output_and_thoughts_token_count"]) for r in records),
        "total_tokens": sum(int(r["total_token_count"]) for r in records),
        "compacted_contents_dropped": max((int(r.get("compacted_contents_dropped", 0)) for r in records), default=0),
    }


async def _run_turn(runner: Runner, user_id: str, session_id: str, prompt: str) -> dict[str, Any]:
    usage_bucket: list[dict[str, Any]] = []
    caa_bucket: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    texts: list[str] = []
    tok_usage = ADK_USAGE_COLLECTOR_VAR.set(usage_bucket)
    tok_caa = CAA_CALL_COLLECTOR_VAR.set(caa_bucket)
    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc)
    try:
        msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        async for ev in runner.run_async(user_id=user_id, session_id=session_id, new_message=msg):
            parts = ev.content.parts if ev.content and ev.content.parts else []
            for p in parts:
                fc = getattr(p, "function_call", None)
                if fc is not None:
                    tool_events.append({"kind": "call", "name": fc.name, "args": dict(fc.args or {})})
                fr = getattr(p, "function_response", None)
                if fr is not None:
                    tool_events.append({"kind": "response", "name": fr.name, "response": fr.response})
            if ev.is_final_response() and parts:
                t = "\n".join(p.text for p in parts if getattr(p, "text", None)).strip()
                if t:
                    texts.append(t)
    finally:
        ADK_USAGE_COLLECTOR_VAR.reset(tok_usage)
        CAA_CALL_COLLECTOR_VAR.reset(tok_caa)
    return {
        "answer": "\n\n".join(texts).strip(),
        "usage": _summarize_adk_usage(usage_bucket),
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "started_at_utc": started_at.isoformat(),
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
        "caa_calls": caa_bucket,
        "tool_events": tool_events,
    }


def _run_asis_turn_blocking(session_svc: InMemorySessionService, user_id: str, session_id: str, prompt: str) -> dict[str, Any]:
    async def _go() -> dict[str, Any]:
        runner = Runner(app_name=ASIS_APP_NAME, agent=_build_asis_agent(), session_service=session_svc)
        return await _run_turn(runner, user_id, session_id, prompt)

    return asyncio.run(_go())


def _walk_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dicts(v)


def _parse_ask_data_agent_response(response: Any) -> dict[str, Any]:
    sql = ""
    finals: list[str] = []
    for d in _walk_dicts(response):
        for k, v in d.items():
            if isinstance(v, str) and "sql" in k.lower() and "select" in v.lower():
                sql = v.strip()
        if "parts" in d and isinstance(d.get("parts"), list) and str(d.get("textType", "")).upper() == "FINAL_RESPONSE":
            finals.append("".join(str(p) for p in d["parts"]).strip())
    status = response.get("status") if isinstance(response, dict) else None
    return {
        "status": status or "UNKNOWN",
        "error_details": response.get("error_details", "") if isinstance(response, dict) else "",
        "generated_sql": sql,
        "final_text": "\n\n".join(f for f in finals if f),
        "response_chars": len(json.dumps(response, ensure_ascii=False, default=str)),
    }


def _trace_estimate(agent_ids: list[str]) -> dict[str, Any] | None:
    """Sums the Cloud Trace median per chat turn for each BQCA call. None if any agent is uncalibrated."""
    cal = load_bqca_trace_calibration().get("per_data_agent", {})
    total_in = total_cached = total_out = 0
    for aid in agent_ids:
        row = cal.get(aid)
        if not row:
            return None
        total_in += int(row["median_input_tokens_per_turn"])
        total_cached += int(row["median_cached_input_tokens_per_turn"])
        total_out += int(row["median_output_tokens_per_turn"])
    return {"input_tokens": total_in, "cached_input_tokens": total_cached, "output_tokens": total_out}


def _cost_estimate(usage: dict[str, Any], trace: dict[str, Any] | None) -> dict[str, Any] | None:
    if trace is None:
        return None
    adk_non_cached = max(0, usage["prompt_tokens"] - usage["cached_tokens"])
    adk = (
        adk_non_cached * VERTEX_FLASH_INPUT_USD_PER_1M
        + usage["cached_tokens"] * VERTEX_FLASH_CACHED_USD_PER_1M
        + usage["output_and_thoughts_tokens"] * VERTEX_FLASH_OUTPUT_USD_PER_1M
    ) / 1_000_000
    bq_non_cached = max(0, trace["input_tokens"] - trace["cached_input_tokens"])
    bqca = (
        bq_non_cached * BQCA_INPUT_NON_CACHED_USD_PER_1M
        + trace["cached_input_tokens"] * BQCA_INPUT_CACHED_USD_PER_1M
        + trace["output_tokens"] * BQCA_OUTPUT_USD_PER_1M
    ) / 1_000_000
    return {"adk_usd": round(adk, 5), "bqca_usd": round(bqca, 5), "total_usd": round(adk + bqca, 5)}


def _finish_side(side: dict[str, Any], agent_ids: list[str]) -> dict[str, Any]:
    trace = _trace_estimate(agent_ids)
    side["bqca_calls"] = len(agent_ids)
    side["bqca_agents"] = agent_ids
    side["bqca_trace_estimate"] = trace
    side["cost_estimate_usd"] = _cost_estimate(side["adk_usage"], trace)
    side["status"] = "ERROR" if side["errors"] else "OK"
    return side


def _tobe_side(turn: dict[str, Any], label: str) -> dict[str, Any]:
    calls = turn["caa_calls"]
    ok = [c for c in calls if c.get("status") == "SUCCESS"]
    errors = [f"{c.get('data_agent', '').rsplit('/', 1)[-1]}: {c.get('error_details', 'unknown error')}" for c in calls if c.get("status") != "SUCCESS"]
    agent_ids = [c.get("data_agent", "").rsplit("/", 1)[-1] for c in calls]
    if len(ok) > 1:
        sql = "\n\n".join(f"-- [{c['data_agent'].rsplit('/', 1)[-1]}]\n{c.get('generated_sql', '')}" for c in ok)
        table = "\n\n".join(f"**{c['domain']}**\n{c['markdown_table']}" for c in ok if c.get("markdown_table"))
    else:
        sql = ok[0].get("generated_sql", "") if ok else ""
        table = ok[0].get("markdown_table", "") if ok else ""
    return _finish_side(
        {
            "label": label,
            "latency_ms": turn["latency_ms"],
            "started_at_utc": turn["started_at_utc"],
            "ended_at_utc": turn["ended_at_utc"],
            # Single-domain turns end on the tool result (no summarization call), so the answer is BQCA's own text.
            "answer": turn["answer"] or "\n\n".join(c.get("ca_final_answer", "") for c in ok if c.get("ca_final_answer")),
            "generated_sql": sql,
            "markdown_table": table,
            "adk_usage": turn["usage"],
            "bqca_messages_sent": [c.get("multiturn_context_messages_sent") for c in ok],
            "bqca_call_latency_ms": [c.get("latency_ms") for c in ok],
            "tool_calls": [e["name"] for e in turn["tool_events"] if e["kind"] == "call"],
            "errors": errors,
        },
        agent_ids,
    )


def _asis_side(turn: dict[str, Any], label: str) -> dict[str, Any]:
    ask_calls = [e for e in turn["tool_events"] if e["kind"] == "call" and e["name"] == "ask_data_agent"]
    ask_resps = [_parse_ask_data_agent_response(e["response"]) for e in turn["tool_events"] if e["kind"] == "response" and e["name"] == "ask_data_agent"]
    agent_ids = [str(c["args"].get("data_agent_name", "")).rsplit("/", 1)[-1] for c in ask_calls]
    errors = [f"ask_data_agent: {r['error_details'] or r['status']}" for r in ask_resps if r["status"] != "SUCCESS"]
    sqls = [r["generated_sql"] for r in ask_resps if r["generated_sql"]]
    return _finish_side(
        {
            "label": label,
            "latency_ms": turn["latency_ms"],
            "started_at_utc": turn["started_at_utc"],
            "ended_at_utc": turn["ended_at_utc"],
            "answer": turn["answer"],
            "generated_sql": "\n\n".join(f"-- [ask_data_agent call {i + 1}]\n{s}" for i, s in enumerate(sqls)) if len(sqls) > 1 else (sqls[0] if sqls else ""),
            "markdown_table": "",
            "adk_usage": turn["usage"],
            # ask_data_agent always sends exactly one userMessage per call.
            "bqca_messages_sent": [1 for _ in ask_calls],
            "tool_calls": [e["name"] for e in turn["tool_events"] if e["kind"] == "call"],
            "tool_response_chars": sum(r["response_chars"] for r in ask_resps),
            "errors": errors,
        },
        agent_ids,
    )


def _failed_side(label: str, exc: BaseException) -> dict[str, Any]:
    return {
        "label": label, "status": "ERROR", "errors": [f"{type(exc).__name__}: {exc}"], "latency_ms": 0, "answer": "",
        "generated_sql": "", "markdown_table": "", "bqca_calls": 0, "bqca_agents": [], "bqca_messages_sent": [],
        "tool_calls": [], "bqca_trace_estimate": None, "cost_estimate_usd": None,
        "adk_usage": _summarize_adk_usage([]),
    }


def _delta_pct(asis: float | None, tobe: float | None) -> float | None:
    if not asis or tobe is None:
        return None
    return round((tobe - asis) / asis * 100.0, 1)


def _comparison(asis: dict[str, Any], tobe: dict[str, Any]) -> dict[str, Any]:
    a_u, b_u = asis["adk_usage"], tobe["adk_usage"]
    measured = {
        "asis_adk_prompt_tokens": a_u["prompt_tokens"],
        "tobe_adk_prompt_tokens": b_u["prompt_tokens"],
        "adk_prompt_delta_pct": _delta_pct(a_u["prompt_tokens"], b_u["prompt_tokens"]),
        "asis_adk_cached_tokens": a_u["cached_tokens"],
        "tobe_adk_cached_tokens": b_u["cached_tokens"],
        "asis_llm_calls": a_u["llm_calls"],
        "tobe_llm_calls": b_u["llm_calls"],
        "asis_bqca_calls": asis["bqca_calls"],
        "tobe_bqca_calls": tobe["bqca_calls"],
        "asis_latency_ms": asis["latency_ms"],
        "tobe_latency_ms": tobe["latency_ms"],
    }
    a_t, b_t = asis["bqca_trace_estimate"], tobe["bqca_trace_estimate"]
    a_c, b_c = asis["cost_estimate_usd"], tobe["cost_estimate_usd"]
    trace = None
    if a_t is not None and b_t is not None:
        a_total = a_u["prompt_tokens"] + a_t["input_tokens"]
        b_total = b_u["prompt_tokens"] + b_t["input_tokens"]
        trace = {
            "asis_bqca_input_tokens": a_t["input_tokens"],
            "tobe_bqca_input_tokens": b_t["input_tokens"],
            "asis_total_input_tokens": a_total,
            "tobe_total_input_tokens": b_total,
            "total_input_delta_pct": _delta_pct(a_total, b_total),
            "asis_cost_usd": a_c["total_usd"] if a_c else None,
            "tobe_cost_usd": b_c["total_usd"] if b_c else None,
            "cost_delta_pct": _delta_pct(a_c["total_usd"] if a_c else None, b_c["total_usd"] if b_c else None),
        }
    return {"measured": measured, "trace_estimate": trace}


# --------------------------------------------------------------------------------------------
# Per-visitor state
# --------------------------------------------------------------------------------------------
@dataclass
class VisitorWorkbenchSession:
    visitor_id: str
    last_active: float = field(default_factory=time.monotonic)
    request_timestamps: list[float] = field(default_factory=list)
    session_svc: InMemorySessionService = field(default_factory=InMemorySessionService)
    asis_session_svc: InMemorySessionService = field(default_factory=InMemorySessionService)
    memory_svc: InMemoryMemoryService = field(default_factory=InMemoryMemoryService)
    runner: Runner | None = None
    busy: bool = False
    epoch: int = 0
    main_turns: int = 0
    s4_epoch: int = 0
    s4_turn_history: list[dict[str, Any]] = field(default_factory=list)
    s5_runs: int = 0
    memory_seeded: bool = False

    @property
    def user_id(self) -> str:
        return f"eval_{self.visitor_id}"

    def ensure_runner(self) -> Runner:
        self.last_active = time.monotonic()
        if self.runner is None:
            self.runner = Runner(app=adk_app, session_service=self.session_svc, memory_service=self.memory_svc)
        return self.runner

    async def create_pair(self, tobe_sid: str, asis_sid: str | None) -> None:
        runner = self.ensure_runner()
        await self.session_svc.create_session(app_name=runner.app_name, user_id=self.user_id, session_id=tobe_sid)
        if asis_sid:
            await self.asis_session_svc.create_session(app_name=ASIS_APP_NAME, user_id=self.user_id, session_id=asis_sid)

    async def new_main_sessions(self) -> None:
        self.epoch += 1
        self.main_turns = 0
        await self.create_pair(f"tobe-main-{self.epoch}", f"asis-main-{self.epoch}")

    def check_rate_limit(self) -> tuple[bool, int]:
        now = time.monotonic()
        self.request_timestamps = [t for t in self.request_timestamps if now - t < RATE_LIMIT_WINDOW_SEC]
        if len(self.request_timestamps) >= RATE_LIMIT_MAX_CALLS:
            return False, max(1, int(RATE_LIMIT_WINDOW_SEC - (now - self.request_timestamps[0])))
        self.request_timestamps.append(now)
        return True, 0


_VISITOR_SESSIONS: dict[str, VisitorWorkbenchSession] = {}


def _evict_stale_visitors() -> None:
    now = time.monotonic()
    for k in [k for k, v in _VISITOR_SESSIONS.items() if now - v.last_active > VISITOR_TTL_SECONDS and not v.busy]:
        _VISITOR_SESSIONS.pop(k, None)
    while len(_VISITOR_SESSIONS) > MAX_VISITORS_CACHE:
        _VISITOR_SESSIONS.pop(min(_VISITOR_SESSIONS, key=lambda k: _VISITOR_SESSIONS[k].last_active), None)


def get_visitor_session(visitor_id: str) -> VisitorWorkbenchSession:
    _evict_stale_visitors()
    vid = sanitize_visitor_id(visitor_id)
    sess = _VISITOR_SESSIONS.get(vid)
    if sess is None:
        sess = VisitorWorkbenchSession(visitor_id=vid)
        _VISITOR_SESSIONS[vid] = sess
    sess.ensure_runner()
    return sess


async def reset_visitor_session(visitor_id: str) -> dict[str, Any]:
    vid = sanitize_visitor_id(visitor_id)
    tok = VISITOR_ID_VAR.set(vid)
    try:
        reset_persistent_memory_store()
    finally:
        VISITOR_ID_VAR.reset(tok)
    _VISITOR_SESSIONS.pop(vid, None)
    return {"status": "ok", "visitor_id": get_visitor_session(vid).visitor_id, "reset_at_utc": _utc_now()}


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, 'ts': _utc_now(), **data}, ensure_ascii=False, default=str)}\n\n"


# --------------------------------------------------------------------------------------------
# Scenario stream
# --------------------------------------------------------------------------------------------
async def stream_dual_ab_scenario(
    visitor_id: str,
    scenario_code: str,
    custom_prompt: str,
    s4_mode: str = "burst",
) -> AsyncIterator[str]:
    code = scenario_code.strip().upper()
    prompt = custom_prompt.strip()[:MAX_PROMPT_CHARS]
    vid = sanitize_visitor_id(visitor_id)
    vsess = get_visitor_session(vid)

    if code not in ("S1", "S2", "S3", "S4", "S5"):
        yield _sse_event("error", {"message": f"Unknown scenario code: {code}"})
        return
    if vsess.busy:
        yield _sse_event("error", {"message": "A live run is already in progress for this session."})
        return
    allowed, retry_sec = vsess.check_rate_limit()
    if not allowed:
        yield _sse_event("error", {"message": f"Rate limit reached ({RATE_LIMIT_MAX_CALLS} live runs / min). Retry in {retry_sec}s."})
        return

    event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(side: str, detail: str) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, {"kind": "progress", "side": side, "detail": detail})

    async def run_tobe(sid: str, text: str, label: str) -> dict[str, Any]:
        runner = vsess.ensure_runner()
        turn = await _run_turn(runner, vsess.user_id, sid, text)
        side = _tobe_side(turn, label)
        emit("tobe", f"Finished in {side['latency_ms'] / 1000:.1f}s: ADK prompt {side['adk_usage']['prompt_tokens']:,} tok (measured), {side['bqca_calls']} BQCA call(s), agents {' > '.join(side['adk_usage']['agents_invoked'])}")
        return side

    async def run_asis(sid: str, text: str, label: str) -> dict[str, Any]:
        turn = await asyncio.to_thread(_run_asis_turn_blocking, vsess.asis_session_svc, vsess.user_id, sid, text)
        side = _asis_side(turn, label)
        emit("asis", f"Finished in {side['latency_ms'] / 1000:.1f}s: ADK prompt {side['adk_usage']['prompt_tokens']:,} tok (measured), {side['bqca_calls']} BQCA call(s), tools {', '.join(side['tool_calls']) or 'none'}")
        return side

    async def run_both(tobe_sid: str, asis_sid: str, text: str, tobe_label: str, asis_label: str) -> tuple[dict[str, Any], dict[str, Any]]:
        res = await asyncio.gather(run_tobe(tobe_sid, text, tobe_label), run_asis(asis_sid, text, asis_label), return_exceptions=True)
        tobe = res[0] if isinstance(res[0], dict) else _failed_side(tobe_label, res[0])
        asis = res[1] if isinstance(res[1], dict) else _failed_side(asis_label, res[1])
        return tobe, asis

    tobe_label = "To-Be: Root Router + domain-scoped Sub-Agents (sliding window, compaction, memory)"
    asis_label = f"As-Is: ADK built-in data agent tools on one monolithic data agent ({BASELINE_CA_ID})"

    async def worker() -> None:
        v_tok = VISITOR_ID_VAR.set(vid)
        vsess.busy = True
        t_start = time.monotonic()
        prerequisite: dict[str, Any] | None = None
        extra: dict[str, Any] = {}
        try:
            emit("both", f"Running To-Be and As-Is in parallel on {PROJECT_ID}.{DATASET_ID} (google-adk {google.adk.__version__})")

            async def ensure_turn1() -> dict[str, Any] | None:
                if vsess.main_turns > 0:
                    emit("both", f"Continuing your live session (turn {vsess.main_turns + 1}).")
                    return None
                await vsess.new_main_sessions()
                emit("both", "No earlier turn in this session, so Turn 1 runs first on both pipelines. Its tokens are reported separately.")
                p_tobe, p_asis = await run_both(f"tobe-main-{vsess.epoch}", f"asis-main-{vsess.epoch}", TURN1_PROMPT, tobe_label, asis_label)
                vsess.main_turns = 1
                return {
                    "prompt": TURN1_PROMPT,
                    "tobe_adk_prompt_tokens": p_tobe["adk_usage"]["prompt_tokens"],
                    "asis_adk_prompt_tokens": p_asis["adk_usage"]["prompt_tokens"],
                    "tobe_errors": p_tobe["errors"],
                    "asis_errors": p_asis["errors"],
                }

            if code == "S1":
                await vsess.new_main_sessions()
                tobe, asis = await run_both(f"tobe-main-{vsess.epoch}", f"asis-main-{vsess.epoch}", prompt, tobe_label, asis_label)
                vsess.main_turns = 1

            elif code in ("S2", "S3"):
                prerequisite = await ensure_turn1()
                tobe, asis = await run_both(f"tobe-main-{vsess.epoch}", f"asis-main-{vsess.epoch}", prompt, tobe_label, asis_label)
                vsess.main_turns += 1

            elif code == "S4":
                append = "append" in (s4_mode or "").lower() and bool(vsess.s4_turn_history)
                if not append:
                    vsess.s4_epoch += 1
                    vsess.s4_turn_history = []
                    await vsess.create_pair(f"tobe-s4-{vsess.s4_epoch}", f"asis-s4-{vsess.s4_epoch}")
                t_sid, a_sid = f"tobe-s4-{vsess.s4_epoch}", f"asis-s4-{vsess.s4_epoch}"

                def record(text: str, tb: dict[str, Any], ai: dict[str, Any]) -> None:
                    vsess.s4_turn_history.append({
                        "turn": len(vsess.s4_turn_history) + 1,
                        "prompt": text,
                        "asis_adk_prompt_tokens": ai["adk_usage"]["prompt_tokens"],
                        "tobe_adk_prompt_tokens": tb["adk_usage"]["prompt_tokens"],
                        "tobe_compacted_dropped": tb["adk_usage"]["compacted_contents_dropped"],
                        "asis_latency_ms": ai["latency_ms"],
                        "tobe_latency_ms": tb["latency_ms"],
                        "asis_bqca_agents": ai["bqca_agents"],
                        "tobe_bqca_agents": tb["bqca_agents"],
                        "asis_adk_cached_tokens": ai["adk_usage"]["cached_tokens"],
                        "tobe_adk_cached_tokens": tb["adk_usage"]["cached_tokens"],
                        "asis_adk_output_tokens": ai["adk_usage"]["output_and_thoughts_tokens"],
                        "tobe_adk_output_tokens": tb["adk_usage"]["output_and_thoughts_tokens"],
                        "asis_window_utc": [ai.get("started_at_utc"), ai.get("ended_at_utc")],
                        "tobe_window_utc": [tb.get("started_at_utc"), tb.get("ended_at_utc")],
                        "errors": tb["errors"] + ai["errors"],
                    })

                if not append:
                    for w_prompt in S4_WARMUP_PROMPTS:
                        emit("both", f"Turn {len(vsess.s4_turn_history) + 1} (real warm-up turn): {w_prompt}")
                        w_tobe, w_asis = await run_both(t_sid, a_sid, w_prompt, tobe_label, asis_label)
                        record(w_prompt, w_tobe, w_asis)
                emit("both", f"Turn {len(vsess.s4_turn_history) + 1} (your prompt)")
                tobe, asis = await run_both(t_sid, a_sid, prompt, tobe_label, asis_label)
                record(prompt, tobe, asis)
                extra["turn_curve"] = list(vsess.s4_turn_history)

            else:  # S5
                runner = vsess.ensure_runner()
                if vsess.main_turns == 0 and not vsess.memory_seeded:
                    emit("tobe", "No earlier session for this visitor, so a seed session saves a profile and one pinned insight first.")
                    await vsess.create_pair("tobe-s5-seed", None)
                    seed = await run_tobe("tobe-s5-seed", S5_SEED_PROMPT, tobe_label)
                    vsess.memory_seeded = True
                    prerequisite = {"prompt": S5_SEED_PROMPT, "tobe_adk_prompt_tokens": seed["adk_usage"]["prompt_tokens"], "asis_adk_prompt_tokens": None, "tobe_errors": seed["errors"], "asis_errors": []}
                vsess.s5_runs += 1
                t_sid, a_sid = f"tobe-s5-{vsess.s5_runs}", f"asis-s5-{vsess.s5_runs}"
                await vsess.create_pair(t_sid, a_sid)
                emit("both", "Brand-new session on both pipelines. The prompt is sent unchanged to each.")
                tobe, asis = await run_both(t_sid, a_sid, prompt, tobe_label, asis_label)
                new_sess = await vsess.session_svc.get_session(app_name=runner.app_name, user_id=vsess.user_id, session_id=t_sid)
                state = new_sess.state if new_sess else {}
                extra["state_summary"] = {
                    "new_session_id": t_sid,
                    "rehydrated_user_profile": state.get("user:profile"),
                    "rehydrated_pinned_insights": len(state.get("user:pinned_insights") or []),
                }

            cal = load_bqca_trace_calibration()
            sides_failed = [s["status"] == "ERROR" for s in (asis, tobe)]
            await event_queue.put({
                "kind": "complete",
                "result": {
                    "status": "ERROR" if all(sides_failed) else ("PARTIAL" if any(sides_failed) else "SUCCESS"),
                    "scenario_code": code,
                    "visitor_id": vid,
                    "prompt_executed": prompt,
                    "wall_clock_ms": int((time.monotonic() - t_start) * 1000),
                    "prerequisite": prerequisite,
                    "comparison_summary": _comparison(asis, tobe),
                    "asis": asis,
                    "tobe": tobe,
                    "calibration": {
                        "measured_at_utc": cal.get("measured_at_utc"),
                        "source": cal.get("source"),
                        "per_data_agent": cal.get("per_data_agent", {}),
                    },
                    "adk_version": google.adk.__version__,
                    **extra,
                },
            })
        except Exception as exc:  # pylint: disable=broad-except
            await event_queue.put({"kind": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            vsess.busy = False
            vsess.last_active = time.monotonic()
            VISITOR_ID_VAR.reset(v_tok)

    task = asyncio.create_task(worker())
    try:
        while True:
            try:
                item = await asyncio.wait_for(event_queue.get(), timeout=1.5)
            except asyncio.TimeoutError:
                if task.done() and event_queue.empty():
                    break
                yield _sse_event("heartbeat", {"status": "running"})
                continue
            if item["kind"] == "progress":
                yield _sse_event("progress", {"side": item["side"], "detail": item["detail"]})
            elif item["kind"] == "complete":
                yield _sse_event("complete", {"payload": item["result"]})
                break
            else:
                yield _sse_event("error", {"message": item["message"]})
                break
    finally:
        if not task.done():
            task.cancel()
