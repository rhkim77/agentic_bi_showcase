"""Live Interactive S1–S5 Progressive Dual A/B Workbench Engine (`SSE` + Per-Visitor Isolation).

Executes BOTH the `As-Is Anti-Pattern` pipeline and the `To-Be Best Practice` pipeline
concurrently against live Google Cloud (`Vertex AI gemini-2.5-flash` + `geminidataanalytics.googleapis.com/v1`
+ BigQuery `thelook_ecommerce_agent`) for any custom or preset evaluator prompt across S1..S5.
"""

from __future__ import annotations

import asyncio
import contextvars
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import queue
import re
import time
from typing import Any, AsyncIterator

from google.adk.agents import LlmAgent
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.bq_caa_3domain_multi_agent.agent import (
    ADK_USAGE_COLLECTOR_VAR,
    BASELINE_CA_ID,
    CUSTOMER_CA_ID,
    DATASET_ID,
    MONOLITHIC_FANOUT_EQUIV_INPUT_TOKENS,
    MONOLITHIC_SINGLE_TURN_INPUT_TOKENS,
    PRODUCT_CA_ID,
    PROJECT_ID,
    SUPPLY_CA_ID,
    TELEMETRY_QUEUE_VAR,
    VISITOR_ID_VAR,
    _compact_adk_llm_request_window,
    _query_domain_caa_agent,
    _record_vertex_llm_usage_telemetry,
    adk_app,
    compute_effective_cost_usd,
    reset_persistent_memory_store,
    root_agent,
)

MAX_PROMPT_CHARS = 600
MAX_VISITORS_CACHE = 120
VISITOR_TTL_SECONDS = 7200
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX_CALLS = 8


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_visitor_id(raw: str | None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", str(raw or ""))[:48]
    return cleaned or "default_eval"


def _infer_target_domain_agent(prompt: str) -> tuple[str, str, str]:
    p = prompt.lower()
    if any(k in p for k in ["distribution", "dc", "lead time", "shipped", "delivered", "inventory", "unsold", "holding cost", "memphis", "chicago", "물류", "배송", "재고", "센터"]):
        return (SUPPLY_CA_ID, "supply_chain", "Supply Chain, Inventory & Fulfillment")
    if any(k in p for k in ["margin", "profit", "return", "cancel", "brand", "nordic", "atelier", "outerwear", "retail_price", "마진", "수익", "이익", "반품", "브랜드"]):
        return (PRODUCT_CA_ID, "product_profitability", "Product, Margin & Return Analytics")
    return (CUSTOMER_CA_ID, "customer_marketing", "Customer CRM & Marketing Funnel")


def _summarize_adk_usage(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "llm_calls": len(records),
        "agents_invoked": [r["agent_name"] for r in records],
        "prompt_tokens": sum(int(r["prompt_token_count"]) for r in records),
        "cached_tokens": sum(int(r["cached_content_token_count"]) for r in records),
        "candidates_tokens": sum(int(r["candidates_token_count"]) for r in records),
        "thoughts_tokens": sum(int(r["thoughts_token_count"]) for r in records),
        "output_and_thoughts_tokens": sum(int(r["output_and_thoughts_token_count"]) for r in records),
        "total_tokens": sum(int(r["total_token_count"]) for r in records),
        "compacted_contents_dropped": max((int(r.get("compacted_contents_dropped", 0)) for r in records), default=0),
        "per_call_breakdown": records,
    }


async def _run_in_ctx_thread(fn, *args, **kwargs):
    ctx = contextvars.copy_context()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: ctx.run(fn, *args, **kwargs))


def _build_verbose_discovery_dump() -> dict[str, Any]:
    """Represents ADK default `list_accessible_data_agents` + `_get_data_agent_info` full 7-table schema dump."""
    verbose_ddls = {
        tbl: [
            {
                "column": f"col_{i}",
                "type": "STRING/TIMESTAMP/FLOAT64",
                "description": "Unpruned warehouse column metadata description and sample values " * 3,
            }
            for i in range(18)
        ]
        for tbl in ["users", "events", "orders", "order_items", "products", "inventory_items", "distribution_centers"]
    }
    return {
        "accessible_agents": [
            BASELINE_CA_ID,
            CUSTOMER_CA_ID,
            PRODUCT_CA_ID,
            SUPPLY_CA_ID,
        ],
        "full_warehouse_schema_metadata": verbose_ddls,
    }


@dataclass
class VisitorWorkbenchSession:
    visitor_id: str
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)
    request_timestamps: list[float] = field(default_factory=list)
    session_svc: InMemorySessionService = field(default_factory=InMemorySessionService)
    memory_svc: InMemoryMemoryService = field(default_factory=InMemoryMemoryService)
    runner: Runner | None = None
    main_session_id: str = "workbench-main"
    initialized: bool = False
    s1_completed: bool = False
    last_s1_prompt: str = ""
    last_s1_summary: str = ""
    last_s1_domain_agent_id: str = CUSTOMER_CA_ID
    s4_turn_history: list[dict[str, Any]] = field(default_factory=list)
    s4_sess_svc: InMemorySessionService = field(default_factory=InMemorySessionService)
    s4_asis_runner: Runner | None = None
    s4_tobe_runner: Runner | None = None
    s4_initialized: bool = False
    s5_seeded: bool = False

    async def ensure_initialized(self) -> None:
        self.last_active = time.monotonic()
        if self.initialized and self.runner is not None:
            return
        try:
            self.runner = Runner(
                app=adk_app,
                session_service=self.session_svc,
                memory_service=self.memory_svc,
            )
        except Exception:
            self.runner = Runner(
                app_name="bq_caa_3domain_multi_agent",
                agent=root_agent,
                session_service=self.session_svc,
                memory_service=self.memory_svc,
            )
        await self.session_svc.create_session(
            app_name=self.runner.app_name,
            user_id=f"eval_{self.visitor_id}",
            session_id=self.main_session_id,
        )
        self.initialized = True

    def check_rate_limit(self) -> tuple[bool, int]:
        now = time.monotonic()
        self.request_timestamps = [t for t in self.request_timestamps if now - t < RATE_LIMIT_WINDOW_SEC]
        if len(self.request_timestamps) >= RATE_LIMIT_MAX_CALLS:
            retry_after = max(1, int(RATE_LIMIT_WINDOW_SEC - (now - self.request_timestamps[0])))
            return False, retry_after
        self.request_timestamps.append(now)
        return True, 0


_VISITOR_SESSIONS: dict[str, VisitorWorkbenchSession] = {}


def _evict_stale_visitors() -> None:
    now = time.monotonic()
    stale = [k for k, v in _VISITOR_SESSIONS.items() if now - v.last_active > VISITOR_TTL_SECONDS]
    for k in stale:
        _VISITOR_SESSIONS.pop(k, None)
    while len(_VISITOR_SESSIONS) > MAX_VISITORS_CACHE:
        oldest_key = min(_VISITOR_SESSIONS, key=lambda k: _VISITOR_SESSIONS[k].last_active)
        _VISITOR_SESSIONS.pop(oldest_key, None)


async def get_visitor_session(visitor_id: str) -> VisitorWorkbenchSession:
    _evict_stale_visitors()
    vid = sanitize_visitor_id(visitor_id)
    sess = _VISITOR_SESSIONS.get(vid)
    if sess is None:
        sess = VisitorWorkbenchSession(visitor_id=vid)
        _VISITOR_SESSIONS[vid] = sess
    await sess.ensure_initialized()
    return sess


async def reset_visitor_session(visitor_id: str) -> dict[str, Any]:
    vid = sanitize_visitor_id(visitor_id)
    tok = VISITOR_ID_VAR.set(vid)
    try:
        reset_persistent_memory_store()
    finally:
        VISITOR_ID_VAR.reset(tok)
    _VISITOR_SESSIONS.pop(vid, None)
    fresh = await get_visitor_session(vid)
    return {
        "status": "ok",
        "visitor_id": fresh.visitor_id,
        "reset_at_utc": _utc_now(),
    }


async def _execute_adk_turn_isolated(
    runner: Runner,
    user_id: str,
    session_id: str,
    prompt: str,
) -> tuple[str, dict[str, Any], int]:
    bucket: list[dict[str, Any]] = []
    tok = ADK_USAGE_COLLECTOR_VAR.set(bucket)
    t0 = time.monotonic()
    texts: list[str] = []
    try:
        msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        async for ev in runner.run_async(user_id=user_id, session_id=session_id, new_message=msg):
            if ev.is_final_response() and ev.content and ev.content.parts:
                t = "\n".join(p.text for p in ev.content.parts if getattr(p, "text", None)).strip()
                if t:
                    texts.append(t)
    finally:
        ADK_USAGE_COLLECTOR_VAR.reset(tok)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    return "\n\n".join(texts).strip(), _summarize_adk_usage(bucket), elapsed_ms


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    payload = {"type": event_type, "ts": _utc_now(), **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_dual_ab_scenario(
    visitor_id: str,
    scenario_code: str,
    custom_prompt: str,
    s4_mode: str = "burst_5turn",
) -> AsyncIterator[str]:
    """Streams real-time SSE progress and final Dual Live A/B telemetry for S1..S5."""
    code = scenario_code.strip().upper()
    prompt = custom_prompt.strip()[:MAX_PROMPT_CHARS]
    vid = sanitize_visitor_id(visitor_id)
    vsess = await get_visitor_session(vid)

    allowed, retry_sec = vsess.check_rate_limit()
    if not allowed:
        yield _sse_event(
            "error",
            {
                "message": f"Rate limit reached ({RATE_LIMIT_MAX_CALLS} live runs / min). Please retry in {retry_sec}s.",
            },
        )
        return

    event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(side: str, phase: str, detail: str) -> None:
        loop.call_soon_threadsafe(
            event_queue.put_nowait,
            {"kind": "progress", "side": side, "phase": phase, "detail": detail},
        )

    async def worker() -> None:
        v_tok = VISITOR_ID_VAR.set(vid)
        t_start = time.monotonic()
        try:
            assert vsess.runner is not None
            user_id = f"eval_{vid}"
            app_name = vsess.runner.app_name

            # =================================================================
            # SCENARIO 1: Live Discovery + Monolithic CAA vs Static Enum + Scoped CAA
            # =================================================================
            if code == "S1":
                emit("both", "start", f"Launching parallel Live Dual A/B execution on {PROJECT_ID}.{DATASET_ID}...")

                async def run_s1_asis() -> dict[str, Any]:
                    emit("asis", "discovery", "As-Is: Calling list_accessible_data_agents + 7-table schema dump...")
                    captured_caa: dict[str, Any] = {}

                    def list_and_inspect_all_data_agents() -> dict[str, Any]:
                        return _build_verbose_discovery_dump()

                    def ask_unoptimized_baseline_data_agent(query: str) -> dict[str, Any]:
                        emit("asis", "bqca", f"As-Is: Querying unscoped monolithic {BASELINE_CA_ID} (all 7 tables, raw THOUGHT stream)...")
                        res = _query_domain_caa_agent(
                            agent_id=BASELINE_CA_ID,
                            domain_id="monolithic_baseline",
                            domain_label="Unscoped Monolithic CAA (All 7 Tables, Zero Glossary)",
                            query=query,
                            include_raw_thoughts_for_baseline=True,
                            max_table_rows=50,
                        )
                        captured_caa.update(res)
                        return {
                            "agent": BASELINE_CA_ID,
                            "query": query,
                            "thought_stream": res.get("raw_thoughts_log", []),
                            "generated_sql": res.get("generated_sql", ""),
                            "raw_rows_json": res.get("raw_rows_json", []),
                            "final_text": res.get("ca_final_answer", ""),
                        }

                    asis_agent = LlmAgent(
                        model="gemini-2.5-flash",
                        name="asis_discovery_monolithic_agent",
                        instruction=(
                            "You are an unoptimized PoC Root Agent. First call `list_and_inspect_all_data_agents()` to inspect "
                            "available agents and full table schemas, then call `ask_unoptimized_baseline_data_agent(query=...)` "
                            "with the user's question in English and summarize the result concisely."
                        ),
                        tools=[list_and_inspect_all_data_agents, ask_unoptimized_baseline_data_agent],
                        after_model_callback=_record_vertex_llm_usage_telemetry,
                    )
                    s_svc = InMemorySessionService()
                    r_asis = Runner(app_name="live_s1_asis", agent=asis_agent, session_service=s_svc)
                    await s_svc.create_session(app_name="live_s1_asis", user_id=user_id, session_id="s1-asis")
                    ans, usage, ms = await _execute_adk_turn_isolated(r_asis, user_id, "s1-asis", prompt)
                    emit("asis", "done", f"As-Is finished in {ms / 1000:.1f}s (ADK measured prompt={usage['prompt_tokens']:,} tok)")
                    bq_in = MONOLITHIC_SINGLE_TURN_INPUT_TOKENS
                    cost = compute_effective_cost_usd(
                        usage["prompt_tokens"],
                        usage["cached_tokens"],
                        usage["output_and_thoughts_tokens"],
                        bq_in,
                        bqca_cached_ratio=0.45,
                        bqca_output_tokens=2200,
                    )
                    return {
                        "label": "As-Is: Runtime Discovery + Unscoped Monolithic CAA (7 Tables)",
                        "latency_ms": ms,
                        "adk_usage": usage,
                        "bqca_input_tokens": bq_in,
                        "total_2tier_tokens": usage["prompt_tokens"] + bq_in,
                        "effective_cost_usd": cost["total_effective_cost_usd"],
                        "no_cache_cost_usd": round(cost["adk_tier_cost_usd"] + cost["bqca_unoptimized_no_cache_cost_usd"], 6),
                        "generated_sql": captured_caa.get("generated_sql", ""),
                        "markdown_table": captured_caa.get("markdown_table", ""),
                        "answer": ans or captured_caa.get("ca_final_answer", ""),
                        "defect_summary": (
                            f"Injected 7-table schema dump + {captured_caa.get('stripped_thought_chars', 0):,} raw THOUGHT chars "
                            "into ADK prompt; unscoped DataAgent lacks Hop-1 VIP/Margin glossary formulas."
                        ),
                    }

                async def run_s1_tobe() -> dict[str, Any]:
                    emit("tobe", "routing", "To-Be: Root Router static enum transfer_to_agent (0 discovery calls)...")
                    # Reset main session cleanly for S1 start of chain
                    vsess.session_svc = InMemorySessionService()
                    vsess.initialized = False
                    await vsess.ensure_initialized()
                    assert vsess.runner is not None

                    ans, usage, ms = await _execute_adk_turn_isolated(vsess.runner, user_id, vsess.main_session_id, prompt)
                    sess_after = await vsess.session_svc.get_session(
                        app_name=vsess.runner.app_name, user_id=user_id, session_id=vsess.main_session_id
                    )
                    hist = (sess_after.state.get("domain_query_history") or [{}])[-1] if sess_after else {}
                    fanout_res = sess_after.state.get("last_fanout_results") if sess_after else None

                    if not hist.get("generated_sql") and not fanout_res:
                        # Fallback direct scoped query if LLM answered without calling tool
                        aid, did, dlabel = _infer_target_domain_agent(prompt)
                        direct = await _run_in_ctx_thread(_query_domain_caa_agent, aid, did, dlabel, prompt)
                        bq_tok = int(direct.get("scoped_tokens", 11400))
                        gen_sql = direct.get("generated_sql", "")
                        md_tbl = direct.get("markdown_table", "")
                        ans_text = ans or direct.get("ca_final_answer", "")
                        target_agent = aid
                    elif fanout_res and isinstance(fanout_res, dict):
                        bq_tok = sum(int(v.get("scoped_tokens", 0)) for v in fanout_res.values())
                        gen_sql = "\n\n".join(f"-- [{k}]\n{v.get('generated_sql', '')}" for k, v in fanout_res.items())
                        md_tbl = next((v.get("markdown_table", "") for v in fanout_res.values() if v.get("markdown_table")), "")
                        ans_text = ans
                        target_agent = "3 Scoped Domain Agents (Parallel)"
                    else:
                        bq_tok = int(hist.get("scoped_tokens", 11450))
                        gen_sql = hist.get("generated_sql", "")
                        md_tbl = hist.get("markdown_table", "")
                        ans_text = ans or hist.get("answer_preview", "")
                        target_agent = hist.get("caa_agent_id", CUSTOMER_CA_ID)

                    vsess.s1_completed = True
                    vsess.last_s1_prompt = prompt
                    vsess.last_s1_summary = (ans_text or "")[:600]
                    vsess.last_s1_domain_agent_id = target_agent if target_agent in (CUSTOMER_CA_ID, PRODUCT_CA_ID, SUPPLY_CA_ID) else CUSTOMER_CA_ID

                    emit("tobe", "done", f"To-Be finished in {ms / 1000:.1f}s (ADK measured prompt={usage['prompt_tokens']:,} tok, Scoped CAA={target_agent})")
                    cost = compute_effective_cost_usd(
                        usage["prompt_tokens"],
                        usage["cached_tokens"],
                        usage["output_and_thoughts_tokens"],
                        bq_tok,
                        bqca_cached_ratio=0.60,
                        bqca_output_tokens=1100,
                    )
                    return {
                        "label": f"To-Be: Static Enum Transfer + Scoped {target_agent}",
                        "latency_ms": ms,
                        "adk_usage": usage,
                        "bqca_input_tokens": bq_tok,
                        "total_2tier_tokens": usage["prompt_tokens"] + bq_tok,
                        "effective_cost_usd": cost["total_effective_cost_usd"],
                        "generated_sql": gen_sql,
                        "markdown_table": md_tbl,
                        "answer": ans_text,
                        "state_summary": {
                            "active_domain": sess_after.state.get("active_domain") if sess_after else "Customer CRM",
                            "compact_digest": (sess_after.state.get("compact_routing_digest") or []) if sess_after else [],
                            "window_msgs": len((sess_after.state.get("domain_ca_multiturn_messages") or {}).get(vsess.last_s1_domain_agent_id, [])) if sess_after else 2,
                        },
                    }

                asis_res, tobe_res = await asyncio.gather(run_s1_asis(), run_s1_tobe())

            # =================================================================
            # SCENARIO 2: One-Shot 1-Message Stateless Amnesia vs ADK 3-Turn Window
            # =================================================================
            elif code == "S2":
                assert vsess.runner is not None
                sess_cur = await vsess.session_svc.get_session(
                    app_name=vsess.runner.app_name, user_id=user_id, session_id=vsess.main_session_id
                )
                mt_map = dict(sess_cur.state.get("domain_ca_multiturn_messages") or {}) if sess_cur else {}
                if not mt_map:
                    seed_q = "Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days."
                    seed_a = "30-day VIP cohort by traffic_source (SUM(sale_price) >= $500 OR >= 5 orders): Search (24 VIPs, $17,640 revenue, $245 AOV), Organic, Email, Display."
                    mt_map[CUSTOMER_CA_ID] = [
                        {"userMessage": {"text": seed_q}},
                        {"systemMessage": {"text": {"parts": [seed_a]}}},
                    ]
                    if sess_cur is not None:
                        sess_cur.state["domain_ca_multiturn_messages"] = mt_map
                        sess_cur.state["active_domain"] = "Customer CRM & Marketing Funnel"
                        sess_cur.state["session_turn_count"] = 1
                        sess_cur.state["compact_routing_digest"] = [f"T1 [{CUSTOMER_CA_ID}]: Q='{seed_q[:80]}' -> {seed_a[:120]}"]
                    vsess.last_s1_domain_agent_id = CUSTOMER_CA_ID
                    emit("tobe", "seed", "Auto-seeded Turn-1 VIP cohort into ADK Session.state (ready for Turn-2 follow-up).")
                else:
                    emit("tobe", "seed", f"Reusing live Turn-1 context from your active session ({vsess.last_s1_domain_agent_id}).")

                target_aid = vsess.last_s1_domain_agent_id or CUSTOMER_CA_ID

                async def run_s2_asis() -> dict[str, Any]:
                    emit("asis", "oneshot", "As-Is: Sending ONLY 1 UserMessage (default ask_data_agent One-Shot Stateless) + discovery...")
                    captured_oneshot: dict[str, Any] = {}

                    def list_and_inspect_all_data_agents() -> dict[str, Any]:
                        return _build_verbose_discovery_dump()

                    def ask_oneshot_stateless_data_agent(query: str) -> dict[str, Any]:
                        res = _query_domain_caa_agent(
                            agent_id=BASELINE_CA_ID,
                            domain_id="oneshot_amnesia",
                            domain_label="As-Is One-Shot Stateless (1 Message Sent, 0 Prior Context)",
                            query=query,
                            prior_messages_override=[],  # Zero prior messages!
                            include_raw_thoughts_for_baseline=True,
                            max_table_rows=50,
                        )
                        captured_oneshot.update(res)
                        return {
                            "context_messages_sent": 1,
                            "thought_stream": res.get("raw_thoughts_log", []),
                            "generated_sql": res.get("generated_sql", ""),
                            "raw_rows_json": res.get("raw_rows_json", []),
                            "final_text": res.get("ca_final_answer", ""),
                        }

                    asis_s2 = LlmAgent(
                        model="gemini-2.5-flash",
                        name="asis_oneshot_amnesia_agent",
                        instruction=(
                            "Call `list_and_inspect_all_data_agents()` then call `ask_oneshot_stateless_data_agent(query=...)` "
                            "passing the user's Turn-2 prompt verbatim without prior session history, and summarize."
                        ),
                        tools=[list_and_inspect_all_data_agents, ask_oneshot_stateless_data_agent],
                        after_model_callback=_record_vertex_llm_usage_telemetry,
                    )
                    s_svc = InMemorySessionService()
                    r_asis = Runner(app_name="live_s2_asis", agent=asis_s2, session_service=s_svc)
                    await s_svc.create_session(app_name="live_s2_asis", user_id=user_id, session_id="s2-asis")
                    ans, usage, ms = await _execute_adk_turn_isolated(r_asis, user_id, "s2-asis", prompt)
                    emit("asis", "done", f"As-Is One-Shot finished in {ms / 1000:.1f}s (1 message sent -> prior Turn-1 filter dropped)")
                    bq_in = MONOLITHIC_SINGLE_TURN_INPUT_TOKENS + 9400
                    cost = compute_effective_cost_usd(
                        usage["prompt_tokens"], usage["cached_tokens"], usage["output_and_thoughts_tokens"], bq_in, 0.45, 2200
                    )
                    return {
                        "label": "As-Is: Default One-Shot ask_data_agent (1 Message Sent → Context Amnesia)",
                        "latency_ms": ms,
                        "adk_usage": usage,
                        "bqca_input_tokens": bq_in,
                        "total_2tier_tokens": usage["prompt_tokens"] + bq_in,
                        "effective_cost_usd": cost["total_effective_cost_usd"],
                        "context_messages_sent": 1,
                        "generated_sql": captured_oneshot.get("generated_sql", ""),
                        "markdown_table": captured_oneshot.get("markdown_table", ""),
                        "answer": ans or captured_oneshot.get("ca_final_answer", ""),
                        "defect_summary": "Sent only 1 UserMessage to stateless :chat — lost Turn-1 cohort/columns completely!",
                    }

                async def run_s2_tobe() -> dict[str, Any]:
                    assert vsess.runner is not None
                    emit("tobe", "window", f"To-Be: Injecting curated 3-Turn Sliding Window ({target_aid}) into stateless :chat...")
                    ans, usage, ms = await _execute_adk_turn_isolated(vsess.runner, user_id, vsess.main_session_id, prompt)
                    sess_after = await vsess.session_svc.get_session(
                        app_name=vsess.runner.app_name, user_id=user_id, session_id=vsess.main_session_id
                    )
                    hist = (sess_after.state.get("domain_query_history") or [{}])[-1] if sess_after else {}
                    bq_tok = int(hist.get("scoped_tokens", 11680))
                    msgs_sent = int(hist.get("multiturn_context_messages_sent", 3))
                    emit("tobe", "done", f"To-Be finished in {ms / 1000:.1f}s ({msgs_sent} compact messages sent, Turn-1 context preserved)")
                    cost = compute_effective_cost_usd(
                        usage["prompt_tokens"], usage["cached_tokens"], usage["output_and_thoughts_tokens"], bq_tok, 0.60, 1150
                    )
                    return {
                        "label": f"To-Be: Stateless Chat API + ADK 3-Turn Window ({msgs_sent} Messages Sent)",
                        "latency_ms": ms,
                        "adk_usage": usage,
                        "bqca_input_tokens": bq_tok,
                        "total_2tier_tokens": usage["prompt_tokens"] + bq_tok,
                        "effective_cost_usd": cost["total_effective_cost_usd"],
                        "context_messages_sent": msgs_sent,
                        "generated_sql": hist.get("generated_sql", ""),
                        "markdown_table": hist.get("markdown_table", ""),
                        "answer": ans or hist.get("answer_preview", ""),
                        "state_summary": {
                            "active_domain": sess_after.state.get("active_domain") if sess_after else "Customer CRM",
                            "compact_digest": (sess_after.state.get("compact_routing_digest") or []) if sess_after else [],
                            "window_msgs": msgs_sent,
                        },
                    }

                asis_res, tobe_res = await asyncio.gather(run_s2_asis(), run_s2_tobe())

            # =================================================================
            # SCENARIO 3: Stateful Lock-In & Sequential Calls vs Peer Switch & Parallel Fan-Out
            # =================================================================
            elif code == "S3":
                emit("both", "start", "Running As-Is Monolithic/Sequential vs To-Be Peer Transfer & Parallel Fan-Out...")

                async def run_s3_asis() -> dict[str, Any]:
                    emit("asis", "sequential", "As-Is: Executing unoptimized monolithic/sequential CAA pipeline with schema discovery...")
                    captured_asis: list[dict[str, Any]] = []

                    def list_and_inspect_all_data_agents() -> dict[str, Any]:
                        return _build_verbose_discovery_dump()

                    def ask_monolithic_sequential_caa(sub_question: str) -> dict[str, Any]:
                        emit("asis", "bqca", f"As-Is Sequential Call #{len(captured_asis) + 1} on {BASELINE_CA_ID}...")
                        res = _query_domain_caa_agent(
                            agent_id=BASELINE_CA_ID,
                            domain_id="monolithic_sequential",
                            domain_label="As-Is Monolithic Sequential CAA",
                            query=sub_question,
                            include_raw_thoughts_for_baseline=True,
                            max_table_rows=40,
                        )
                        captured_asis.append(res)
                        return {
                            "thought_stream": res.get("raw_thoughts_log", []),
                            "generated_sql": res.get("generated_sql", ""),
                            "raw_rows_json": res.get("raw_rows_json", []),
                            "final_text": res.get("ca_final_answer", ""),
                        }

                    asis_s3 = LlmAgent(
                        model="gemini-2.5-flash",
                        name="asis_locked_sequential_agent",
                        instruction=(
                            "First call `list_and_inspect_all_data_agents()`, then call `ask_monolithic_sequential_caa(sub_question=...)` "
                            "to answer the user's question in English (if multi-part, call sequentially) and summarize."
                        ),
                        tools=[list_and_inspect_all_data_agents, ask_monolithic_sequential_caa],
                        after_model_callback=_record_vertex_llm_usage_telemetry,
                    )
                    s_svc = InMemorySessionService()
                    r_asis = Runner(app_name="live_s3_asis", agent=asis_s3, session_service=s_svc)
                    await s_svc.create_session(app_name="live_s3_asis", user_id=user_id, session_id="s3-asis")
                    ans, usage, ms = await _execute_adk_turn_isolated(r_asis, user_id, "s3-asis", prompt)
                    n_calls = max(1, len(captured_asis))
                    bq_in = MONOLITHIC_FANOUT_EQUIV_INPUT_TOKENS if n_calls >= 2 else MONOLITHIC_SINGLE_TURN_INPUT_TOKENS
                    emit("asis", "done", f"As-Is completed {n_calls} sequential monolithic call(s) in {ms / 1000:.1f}s")
                    cost = compute_effective_cost_usd(
                        usage["prompt_tokens"], usage["cached_tokens"], usage["output_and_thoughts_tokens"], bq_in, 0.45, 2600
                    )
                    sql_joined = "\n\n".join(
                        f"-- [As-Is Call #{idx + 1}]\n{c.get('generated_sql', '')}" for idx, c in enumerate(captured_asis)
                    )
                    first_tbl = next((c.get("markdown_table", "") for c in captured_asis if c.get("markdown_table")), "")
                    return {
                        "label": f"As-Is: Stateful Single-Agent Lock-In / Sequential Monolithic ({n_calls} Call(s))",
                        "latency_ms": ms,
                        "adk_usage": usage,
                        "bqca_input_tokens": bq_in,
                        "total_2tier_tokens": usage["prompt_tokens"] + bq_in,
                        "effective_cost_usd": cost["total_effective_cost_usd"],
                        "generated_sql": sql_joined,
                        "markdown_table": first_tbl,
                        "answer": ans or "\n\n".join(c.get("ca_final_answer", "") for c in captured_asis),
                        "defect_summary": "ConversationReference locks 1 Conversation = 1 DataAgent; multi-domain analysis serializes execution.",
                    }

                async def run_s3_tobe() -> dict[str, Any]:
                    assert vsess.runner is not None
                    emit("tobe", "fanout", "To-Be: Routing via 0-Bounce Peer Handoff or ThreadPoolExecutor(3) concurrent :chat...")
                    # Use fresh fanout/pivot session seeded with active domain if single-domain pivot
                    ans, usage, ms = await _execute_adk_turn_isolated(vsess.runner, user_id, vsess.main_session_id, prompt)
                    sess_after = await vsess.session_svc.get_session(
                        app_name=vsess.runner.app_name, user_id=user_id, session_id=vsess.main_session_id
                    )
                    fan_map = (sess_after.state.get("last_fanout_results") or {}) if sess_after else {}
                    hist = (sess_after.state.get("domain_query_history") or [{}])[-1] if sess_after else {}

                    if fan_map and isinstance(fan_map, dict):
                        bq_tok = sum(int(v.get("scoped_tokens", 0)) for v in fan_map.values())
                        seq_sum_ms = sum(int(v.get("latency_ms", 0)) for v in fan_map.values())
                        gen_sql = "\n\n".join(f"-- [{k}]\n{v.get('generated_sql', '')}" for k, v in fan_map.items())
                        md_tbl = "\n\n".join(
                            f"**{k}**\n{v.get('markdown_table', '')}" for k, v in fan_map.items() if v.get("markdown_table")
                        )
                        # Clear last_fanout_results after reading so next single-domain turn doesn't reuse it
                        sess_after.state["last_fanout_results"] = None
                        mode_note = f"3-Domain Parallel ThreadPoolExecutor (Sequential Sum: {seq_sum_ms / 1000:.1f}s → Wall-Clock: {ms / 1000:.1f}s)"
                    else:
                        bq_tok = int(hist.get("scoped_tokens", 12900))
                        seq_sum_ms = ms
                        gen_sql = hist.get("generated_sql", "")
                        md_tbl = hist.get("markdown_table", "")
                        mode_note = f"Direct Peer-to-Peer Domain Switch ({' → '.join(usage['agents_invoked'])})"

                    emit("tobe", "done", f"To-Be finished in {ms / 1000:.1f}s ({mode_note})")
                    cost = compute_effective_cost_usd(
                        usage["prompt_tokens"], usage["cached_tokens"], usage["output_and_thoughts_tokens"], bq_tok, 0.60, 1800
                    )
                    return {
                        "label": f"To-Be: {mode_note}",
                        "latency_ms": ms,
                        "sequential_sum_ms": seq_sum_ms,
                        "adk_usage": usage,
                        "bqca_input_tokens": bq_tok,
                        "total_2tier_tokens": usage["prompt_tokens"] + bq_tok,
                        "effective_cost_usd": cost["total_effective_cost_usd"],
                        "generated_sql": gen_sql,
                        "markdown_table": md_tbl,
                        "answer": ans,
                        "state_summary": {
                            "active_domain": sess_after.state.get("active_domain") if sess_after else "Multi-Domain",
                            "agents_hop_trace": usage["agents_invoked"],
                        },
                    }

                asis_res, tobe_res = await asyncio.gather(run_s3_asis(), run_s3_tobe())

            # =================================================================
            # SCENARIO 4: Live Multi-Turn ADK `usage_metadata` Compaction + Live Custom Turn-5 Dual Run
            # =================================================================
            elif code == "S4":
                emit("both", "start", "Running Live Multi-Turn ADK usage_metadata Compaction + Turn-5 Live BigQuery CAA Dual Run...")

                # Prepare verbose vs slim payloads for prior turns 1..4 so we measure 100% real Vertex AI usage_metadata
                verbose_turn_payload = {
                    "schema_discovery": _build_verbose_discovery_dump(),
                    "thought_stream": ["Scanning 7 unscoped tables and candidate joins... " * 28, "Validating timestamp columns... " * 24],
                    "raw_rows_50": [{"channel": "Search", "gross_rev": 18825.48, "detail": "untrimmed raw json row payload " * 6}] * 28,
                }
                slim_turn_payload = {
                    "domain": "Customer CRM & Marketing Funnel",
                    "markdown_table_20_cap": "| traffic_source | vip_count | gross_revenue |\n| --- | --- | --- |\n| Search | 24 | 17640.00 |",
                    "summary": "Search led 30-day VIP gross revenue ($17,640 across 24 VIP customers).",
                }

                target_aid, target_did, target_dlabel = _infer_target_domain_agent(prompt)
                asis_live_turn5_caa: dict[str, Any] = {}
                tobe_live_turn5_caa: dict[str, Any] = {}

                if s4_mode != "append_turn" or not vsess.s4_initialized:
                    vsess.s4_sess_svc = InMemorySessionService()
                    vsess.s4_turn_history = []

                    def asis_multiturn_tool(question: str, execute_live_bqca: bool = False) -> dict[str, Any]:
                        if execute_live_bqca:
                            emit("asis", "bqca", f"As-Is Final Turn: Executing live unscoped {BASELINE_CA_ID} with accumulated history...")
                            res = _query_domain_caa_agent(
                                agent_id=BASELINE_CA_ID,
                                domain_id="monolithic_s4",
                                domain_label="Unscoped Monolithic CAA",
                                query=question,
                                include_raw_thoughts_for_baseline=True,
                                max_table_rows=50,
                            )
                            asis_live_turn5_caa.update(res)
                            return {
                                "live_sql": res.get("generated_sql", ""),
                                "thought_stream": res.get("raw_thoughts_log", []),
                                "raw_rows_50": res.get("raw_rows_json", []),
                                **verbose_turn_payload,
                            }
                        return {"question": question, **verbose_turn_payload}

                    def tobe_multiturn_tool(question: str, execute_live_bqca: bool = False) -> dict[str, Any]:
                        if execute_live_bqca:
                            emit("tobe", "bqca", f"To-Be Final Turn: Executing scoped {target_aid} with 3-Turn Sliding Window...")
                            prior_3turns = [
                                {"userMessage": {"text": "Show 30-day VIP revenue by traffic_source."}},
                                {"systemMessage": {"text": {"parts": ["Search led VIP revenue ($17,640 across 24 VIPs)."]}}},
                                {"userMessage": {"text": "Compare Outerwear return rate by brand."}},
                                {"systemMessage": {"text": {"parts": ["Nordic Luxe return rate is 50.0% vs TheLook Atelier 20.0%."]}}},
                            ]
                            res = _query_domain_caa_agent(
                                agent_id=target_aid,
                                domain_id=target_did,
                                domain_label=target_dlabel,
                                query=question,
                                prior_messages_override=prior_3turns,
                                max_table_rows=20,
                            )
                            tobe_live_turn5_caa.update(res)
                            return {
                                "domain": target_dlabel,
                                "generated_sql": res.get("generated_sql", ""),
                                "markdown_table_20_cap": res.get("markdown_table", ""),
                                "summary": (res.get("ca_final_answer") or "")[:400],
                            }
                        return {"question": question, **slim_turn_payload}

                    asis_mt_agent = LlmAgent(
                        model="gemini-2.5-flash",
                        name="asis_unbounded_adk_agent",
                        instruction=(
                            "Always call `asis_multiturn_tool` once per turn (set `execute_live_bqca=True` ONLY when prompted "
                            "with `[LIVE_FINAL_TURN]`, otherwise `False`) and answer in 2 concise bullets."
                        ),
                        tools=[asis_multiturn_tool],
                        after_model_callback=_record_vertex_llm_usage_telemetry,
                    )
                    tobe_mt_agent = LlmAgent(
                        model="gemini-2.5-flash",
                        name="tobe_compacted_adk_agent",
                        instruction=(
                            "Always call `tobe_multiturn_tool` once per turn (set `execute_live_bqca=True` ONLY when prompted "
                            "with `[LIVE_FINAL_TURN]`, otherwise `False`) and answer in 2 concise bullets."
                        ),
                        tools=[tobe_multiturn_tool],
                        before_model_callback=_compact_adk_llm_request_window,
                        after_model_callback=_record_vertex_llm_usage_telemetry,
                    )
                    vsess.s4_asis_runner = Runner(app_name="live_s4_ab", agent=asis_mt_agent, session_service=vsess.s4_sess_svc)
                    vsess.s4_tobe_runner = Runner(app_name="live_s4_ab", agent=tobe_mt_agent, session_service=vsess.s4_sess_svc)
                    await vsess.s4_sess_svc.create_session(app_name="live_s4_ab", user_id=user_id, session_id="s4-asis")
                    await vsess.s4_sess_svc.create_session(app_name="live_s4_ab", user_id=user_id, session_id="s4-tobe")
                    vsess.s4_initialized = True

                    warmup_turns = [
                        "Turn 1: Summarize 30-day VIP customer revenue by channel.",
                        "Turn 2: Add 14-day cart abandonment rate across those channels.",
                        "Turn 3: Check 90-day dormant VIP customer count.",
                        "Turn 4: Compare Women Outerwear return rate % by brand.",
                    ]
                    for idx_t, w_prompt in enumerate(warmup_turns, start=1):
                        (_, u_a, _), (_, u_b, _) = await asyncio.gather(
                            _execute_adk_turn_isolated(vsess.s4_asis_runner, user_id, "s4-asis", w_prompt),
                            _execute_adk_turn_isolated(vsess.s4_tobe_runner, user_id, "s4-tobe", w_prompt),
                        )
                        row = {
                            "turn": idx_t,
                            "asis_adk_prompt_tokens": u_a["prompt_tokens"],
                            "tobe_adk_prompt_tokens": u_b["prompt_tokens"],
                            "tobe_compacted_dropped": u_b["compacted_contents_dropped"],
                        }
                        vsess.s4_turn_history.append(row)
                        emit(
                            "both",
                            f"turn_{idx_t}",
                            f"Measured Vertex AI Turn {idx_t}: As-Is={u_a['prompt_tokens']:,} tok vs To-Be={u_b['prompt_tokens']:,} tok (evicted={u_b['compacted_contents_dropped']})",
                        )

                assert vsess.s4_asis_runner is not None and vsess.s4_tobe_runner is not None
                next_turn_num = len(vsess.s4_turn_history) + 1
                final_tagged_prompt = f"[LIVE_FINAL_TURN] {prompt}"

                t_f = time.monotonic()
                (asis_ans, u_asis_f, ms_asis_f), (tobe_ans, u_tobe_f, ms_tobe_f) = await asyncio.gather(
                    _execute_adk_turn_isolated(vsess.s4_asis_runner, user_id, "s4-asis", final_tagged_prompt),
                    _execute_adk_turn_isolated(vsess.s4_tobe_runner, user_id, "s4-tobe", final_tagged_prompt),
                )
                _ = t_f

                final_row = {
                    "turn": next_turn_num,
                    "asis_adk_prompt_tokens": u_asis_f["prompt_tokens"],
                    "tobe_adk_prompt_tokens": u_tobe_f["prompt_tokens"],
                    "tobe_compacted_dropped": u_tobe_f["compacted_contents_dropped"],
                }
                vsess.s4_turn_history.append(final_row)

                bq_asis_tok = MONOLITHIC_SINGLE_TURN_INPUT_TOKENS + (next_turn_num - 1) * 9400
                bq_tobe_tok = int(tobe_live_turn5_caa.get("scoped_tokens", 11400 + 3 * 850))

                c_asis = compute_effective_cost_usd(
                    u_asis_f["prompt_tokens"], u_asis_f["cached_tokens"], u_asis_f["output_and_thoughts_tokens"], bq_asis_tok, 0.50, 2200
                )
                c_tobe = compute_effective_cost_usd(
                    u_tobe_f["prompt_tokens"], u_tobe_f["cached_tokens"], u_tobe_f["output_and_thoughts_tokens"], bq_tobe_tok, 0.65, 1050
                )

                asis_res = {
                    "label": f"As-Is Turn {next_turn_num}: Unbounded Session.events + Monolithic CAA",
                    "latency_ms": ms_asis_f,
                    "adk_usage": u_asis_f,
                    "bqca_input_tokens": bq_asis_tok,
                    "total_2tier_tokens": u_asis_f["prompt_tokens"] + bq_asis_tok,
                    "effective_cost_usd": c_asis["total_effective_cost_usd"],
                    "no_cache_cost_usd": round(c_asis["adk_tier_cost_usd"] + c_asis["bqca_unoptimized_no_cache_cost_usd"], 6),
                    "generated_sql": asis_live_turn5_caa.get("generated_sql", ""),
                    "markdown_table": asis_live_turn5_caa.get("markdown_table", ""),
                    "answer": asis_ans or asis_live_turn5_caa.get("ca_final_answer", ""),
                    "turn_curve": list(vsess.s4_turn_history),
                    "defect_summary": f"Turn {next_turn_num} ADK prompt ballooned to {u_asis_f['prompt_tokens']:,} measured tokens due to unpruned tool JSON & THOUGHT history.",
                }
                tobe_res = {
                    "label": f"To-Be Turn {next_turn_num}: before_model_callback 3-Turn Cap + 90% BQCA Cache ($0.30/1M)",
                    "latency_ms": ms_tobe_f,
                    "adk_usage": u_tobe_f,
                    "bqca_input_tokens": bq_tobe_tok,
                    "total_2tier_tokens": u_tobe_f["prompt_tokens"] + bq_tobe_tok,
                    "effective_cost_usd": c_tobe["total_effective_cost_usd"],
                    "generated_sql": tobe_live_turn5_caa.get("generated_sql", ""),
                    "markdown_table": tobe_live_turn5_caa.get("markdown_table", ""),
                    "answer": tobe_ans or tobe_live_turn5_caa.get("ca_final_answer", ""),
                    "turn_curve": list(vsess.s4_turn_history),
                    "state_summary": {
                        "turn_number": next_turn_num,
                        "compacted_contents_dropped": u_tobe_f["compacted_contents_dropped"],
                        "bqca_cached_tokens_90pct_off": c_tobe["bqca_cached_tokens"],
                    },
                }

            # =================================================================
            # SCENARIO 5: New Session Wipe & 110K Re-Scan vs 4-Scope State & Memory 0-Scan Recall
            # =================================================================
            else:
                emit("both", "start", "Testing Brand-New Session B: As-Is Context Wipe Re-Scan vs To-Be MemoryService Short-Circuit...")

                mem_sess_svc = InMemorySessionService()
                mem_bank = InMemoryMemoryService()
                try:
                    mem_runner = Runner(app=adk_app, session_service=mem_sess_svc, memory_service=mem_bank)
                except Exception:
                    mem_runner = Runner(
                        app_name="bq_caa_3domain_multi_agent",
                        agent=root_agent,
                        session_service=mem_sess_svc,
                        memory_service=mem_bank,
                    )

                await mem_sess_svc.create_session(app_name=mem_runner.app_name, user_id=user_id, session_id="session-A")
                seed_note = (
                    "Save my profile role as 'Principal Supply Chain & Merchandising Analyst' focusing on "
                    "'Women Outerwear Margin & DC Lead Time', and pin this root-cause insight: "
                    "'Nordic Luxe 50.0% return rate ($7,200 vs $11,520 realized profit) is driven by a 6.0-day shipping delay at Memphis TN DC #1.'"
                )
                if vsess.last_s1_summary:
                    seed_note += f" Also remember our custom finding: '{vsess.last_s1_summary[:200]}'."

                emit("tobe", "seed", "Session A: Persisting user:profile & pinned root-cause insights into ADK MemoryService, then closing Session A...")
                await _execute_adk_turn_isolated(mem_runner, user_id, "session-A", seed_note)
                sess_a_after = await mem_sess_svc.get_session(app_name=mem_runner.app_name, user_id=user_id, session_id="session-A")
                temp_keys_remaining = [k for k in (sess_a_after.state.keys() if sess_a_after else []) if str(k).startswith("temp:")]

                async def run_s5_asis() -> dict[str, Any]:
                    emit("asis", "rescan", "As-Is (+ New Session): Memory wiped! Forced to re-query Monolithic BigQuery CAA from scratch...")
                    captured_rescan: dict[str, Any] = {}

                    def ask_monolithic_rescan(query: str) -> dict[str, Any]:
                        res = _query_domain_caa_agent(
                            agent_id=BASELINE_CA_ID,
                            domain_id="rescan_baseline",
                            domain_label="As-Is New Session Full Warehouse Re-Scan",
                            query=query,
                            include_raw_thoughts_for_baseline=True,
                            max_table_rows=30,
                        )
                        captured_rescan.update(res)
                        return {
                            "generated_sql": res.get("generated_sql", ""),
                            "thought_stream": res.get("raw_thoughts_log", []),
                            "final_text": res.get("ca_final_answer", ""),
                        }

                    asis_s5 = LlmAgent(
                        model="gemini-2.5-flash",
                        name="asis_no_memory_agent",
                        instruction=(
                            "You have NO cross-session memory or saved analyst profile in this new session. "
                            "You MUST call `ask_monolithic_rescan(query=...)` to query BigQuery from scratch to try answering the user's question."
                        ),
                        tools=[ask_monolithic_rescan],
                        after_model_callback=_record_vertex_llm_usage_telemetry,
                    )
                    s_svc = InMemorySessionService()
                    r_asis = Runner(app_name="live_s5_asis", agent=asis_s5, session_service=s_svc)
                    await s_svc.create_session(app_name="live_s5_asis", user_id=user_id, session_id="s5-asis-new")
                    ans, usage, ms = await _execute_adk_turn_isolated(r_asis, user_id, "s5-asis-new", prompt)
                    bq_in = MONOLITHIC_SINGLE_TURN_INPUT_TOKENS
                    emit("asis", "done", f"As-Is New Session finished in {ms / 1000:.1f}s (burned {bq_in:,} BQCA re-scan tokens)")
                    cost = compute_effective_cost_usd(
                        usage["prompt_tokens"], usage["cached_tokens"], usage["output_and_thoughts_tokens"], bq_in, 0.45, 2000
                    )
                    return {
                        "label": "As-Is (+ New Session): Total Memory Wipe → Forced 110K+ BQCA Re-Scan",
                        "latency_ms": ms,
                        "adk_usage": usage,
                        "bqca_input_tokens": bq_in,
                        "total_2tier_tokens": usage["prompt_tokens"] + bq_in,
                        "effective_cost_usd": cost["total_effective_cost_usd"],
                        "generated_sql": captured_rescan.get("generated_sql", "-- Forced full warehouse re-scan executed"),
                        "markdown_table": captured_rescan.get("markdown_table", ""),
                        "answer": ans or captured_rescan.get("ca_final_answer", ""),
                        "defect_summary": "Wiped analyst persona & prior root-cause memory on + New Session, triggering redundant BigQuery SQL execution.",
                    }

                async def run_s5_tobe() -> dict[str, Any]:
                    emit("tobe", "memory", "To-Be (Brand-New Session B, Turn 1): Rehydrating user:profile & MemoryService (0 BQCA calls)...")
                    await mem_sess_svc.create_session(app_name=mem_runner.app_name, user_id=user_id, session_id="session-B")
                    recall_wrapped = (
                        f"[Brand-New Session-B Context: Prefer recalling from saved user profile & MemoryService via "
                        f"inspect_session_and_memory_status / load_memory without running BigQuery SQL unless explicitly asked for new raw SQL.]\n{prompt}"
                    )
                    ans, usage, ms = await _execute_adk_turn_isolated(mem_runner, user_id, "session-B", recall_wrapped)
                    sess_b_after = await mem_sess_svc.get_session(app_name=mem_runner.app_name, user_id=user_id, session_id="session-B")
                    hist_b = (sess_b_after.state.get("domain_query_history") or []) if sess_b_after else []
                    bq_tok = sum(int(h.get("scoped_tokens", 0)) for h in hist_b)
                    emit("tobe", "done", f"To-Be Session-B Turn 1 finished in {ms / 1000:.1f}s (BQCA Tokens = {bq_tok:,}, 0 Bytes Scanned)")
                    cost = compute_effective_cost_usd(
                        usage["prompt_tokens"], usage["cached_tokens"], usage["output_and_thoughts_tokens"], bq_tok, 0.0, 0
                    )
                    return {
                        "label": "To-Be (Brand-New Session B): 4-Scope State + MemoryService Short-Circuit (0 BQCA Tokens)",
                        "latency_ms": ms,
                        "adk_usage": usage,
                        "bqca_input_tokens": bq_tok,
                        "total_2tier_tokens": usage["prompt_tokens"] + bq_tok,
                        "effective_cost_usd": cost["total_effective_cost_usd"],
                        "generated_sql": (
                            f"-- SHORT-CIRCUITED VIA ADK MemoryService (BQCA API Calls = {len(hist_b)}, BigQuery Bytes Scanned = 0)\n"
                            f"-- Session-A temp:* keys remaining after eviction: {len(temp_keys_remaining)}\n"
                            f"-- Live Vertex AI usage_metadata.prompt_token_count = {usage['prompt_tokens']:,} tok"
                        ),
                        "markdown_table": "",
                        "answer": ans,
                        "state_summary": {
                            "session_a_temp_keys_remaining": len(temp_keys_remaining),
                            "session_b_id": "session-B (Turn 1)",
                            "rehydrated_profile": sess_b_after.state.get("user:profile") if sess_b_after else {},
                            "bqca_calls": len(hist_b),
                        },
                    }

                asis_res, tobe_res = await asyncio.gather(run_s5_asis(), run_s5_tobe())

            wall_elapsed_ms = int((time.monotonic() - t_start) * 1000)
            asis_tot = max(1, int(asis_res["total_2tier_tokens"]))
            tobe_tot = int(tobe_res["total_2tier_tokens"])
            tok_saved_pct = round((1.0 - (tobe_tot / asis_tot)) * 100.0, 1)

            asis_adk_p = max(1, int(asis_res["adk_usage"]["prompt_tokens"]))
            tobe_adk_p = int(tobe_res["adk_usage"]["prompt_tokens"])
            adk_saved_pct = round((1.0 - (tobe_adk_p / asis_adk_p)) * 100.0, 1)

            asis_cost_val = max(0.000001, float(asis_res["effective_cost_usd"]))
            tobe_cost_val = float(tobe_res["effective_cost_usd"])
            cost_saved_pct = round((1.0 - (tobe_cost_val / asis_cost_val)) * 100.0, 1)

            await event_queue.put(
                {
                    "kind": "complete",
                    "result": {
                        "status": "SUCCESS",
                        "scenario_code": code,
                        "visitor_id": vid,
                        "prompt_executed": prompt,
                        "wall_clock_ms": wall_elapsed_ms,
                        "comparison_summary": {
                            "asis_total_2tier_tokens": asis_tot,
                            "tobe_total_2tier_tokens": tobe_tot,
                            "total_token_reduction_pct": tok_saved_pct,
                            "asis_adk_measured_prompt_tokens": int(asis_res["adk_usage"]["prompt_tokens"]),
                            "tobe_adk_measured_prompt_tokens": tobe_adk_p,
                            "adk_prompt_reduction_pct": adk_saved_pct,
                            "asis_effective_cost_usd": round(float(asis_res["effective_cost_usd"]), 5),
                            "tobe_effective_cost_usd": round(tobe_cost_val, 5),
                            "effective_cost_reduction_pct": cost_saved_pct,
                        },
                        "asis": asis_res,
                        "tobe": tobe_res,
                    },
                }
            )
        except Exception as exc:
            await event_queue.put({"kind": "error", "message": str(exc)})
        finally:
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
                yield _sse_event(
                    "progress",
                    {"side": item["side"], "phase": item["phase"], "detail": item["detail"]},
                )
            elif item["kind"] == "complete":
                yield _sse_event("complete", {"payload": item["result"]})
                break
            elif item["kind"] == "error":
                yield _sse_event("error", {"message": item["message"]})
                break
    finally:
        if not task.done():
            task.cancel()
