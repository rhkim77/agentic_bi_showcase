"""Cymbal Global Commerce — Multi-Domain Multi-Agent Architecture with Live 2-Tier Token Telemetry.

Implements:
  1. Google ADK (`LlmAgent`) Root Router + 6 Domain-Scoped Sub-Agents and a warehouse-wide fallback Sub-Agent
     (`Path A` Root Delegation, `Path B` Peer Handoff, `Path C` Parallel Fan-out)
  2. 4-Scope `Session.state` (`temp:*` turn-evicted rows, `session [-6:]` window, `user:*` profile/KPIs, `app:*` counters)
  3. Upstream ADK `before_model_callback` 3-Turn History Compaction + `after_model_callback` `Vertex AI usage_metadata` Telemetry
  4. Long-Term `MemoryService` (`inspect_session_and_memory_status`, persistent JSON store) for Cross-Session Recall without BQCA calls
"""

from __future__ import annotations

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import time
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.genai import types

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import load_memory
from google.adk.tools.tool_context import ToolContext

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "ryan-sandbox-agent") or "ryan-sandbox-agent"
DATASET_ID = os.environ.get("BQ_DATASET_ID", "cymbal_enterprise_dw") or "cymbal_enterprise_dw"

CUSTOMER_CA_ID = os.environ.get("CYMBAL_CUSTOMER_CA_ID", "cymbal_customer_marketing_ca")
PRODUCT_CA_ID = os.environ.get("CYMBAL_PRODUCT_CA_ID", "cymbal_product_profitability_ca")
SUPPLY_CA_ID = os.environ.get("CYMBAL_SUPPLY_CA_ID", "cymbal_supply_chain_ca")
STORE_CA_ID = os.environ.get("CYMBAL_STORE_CA_ID", "cymbal_store_channel_ca")
CATALOG_CA_ID = os.environ.get("CYMBAL_CATALOG_CA_ID", "cymbal_catalog_channel_ca")
WEB_CA_ID = os.environ.get("CYMBAL_WEB_CA_ID", "cymbal_web_channel_ca")
BASELINE_CA_ID = os.environ.get("CYMBAL_BASELINE_CA_ID", "cymbal_enterprise_monolithic_ca")

CUSTOMER_CA_RESOURCE = f"projects/{PROJECT_ID}/locations/global/dataAgents/{CUSTOMER_CA_ID}"
PRODUCT_CA_RESOURCE = f"projects/{PROJECT_ID}/locations/global/dataAgents/{PRODUCT_CA_ID}"
SUPPLY_CA_RESOURCE = f"projects/{PROJECT_ID}/locations/global/dataAgents/{SUPPLY_CA_ID}"

# Per-request live telemetry queue for FastAPI streaming/verification
TELEMETRY_QUEUE_VAR: ContextVar[queue.Queue[dict[str, Any]] | None] = ContextVar(
    "cymbal_telemetry_queue", default=None
)

# Per-invocation collector for real Vertex AI `usage_metadata` captured in `after_model_callback`
ADK_USAGE_COLLECTOR_VAR: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "adk_usage_collector", default=None
)

# Per-invocation collector of every BigQuery CAA call result (status, SQL, messages sent, latency)
CAA_CALL_COLLECTOR_VAR: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "caa_call_collector", default=None
)

# Per-visitor isolation ID so concurrent demo evaluators never collide on persistent Memory files
VISITOR_ID_VAR: ContextVar[str] = ContextVar("cymbal_visitor_id", default="default")

_STATE_DIR = Path(os.environ.get("CYMBAL_STATE_DIR", "/tmp/cymbal_agentic_bi_state"))
_PERSISTENT_MEMORY_FILE = _STATE_DIR / "long_term_memory_bank.json"


_CALIBRATION_FILE = Path(__file__).resolve().parents[2] / "benchmarks" / "bqca_trace_token_calibration.json"


def load_bqca_trace_calibration() -> dict[str, Any]:
    """Cloud Trace medians of real BQCA token usage per data agent (see scripts/05_measure_bqca_tokens_from_trace.py)."""
    try:
        return json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_visitor_memory_file() -> Path:
    vid = VISITOR_ID_VAR.get() or "default"
    safe = "".join(ch for ch in vid if ch.isalnum() or ch in ("-", "_"))[:48] or "default"
    if safe == "default":
        return _PERSISTENT_MEMORY_FILE
    return _STATE_DIR / f"long_term_memory_bank_{safe}.json"

# Upstream ADK History Compaction cap (max pure-text user turns kept in `llm_request.contents`)
MAX_ADK_UPSTREAM_USER_TURNS = 3

# PAYG Pricing Constants (USD per 1M tokens)
# Published rates: https://cloud.google.com/products/data-agents/pricing ($3.00 input, $20.00 output)
# and https://cloud.google.com/vertex-ai/generative-ai/pricing (Gemini 2.5 Flash $0.30 / $0.03 / $2.50).
# BQCA `cache_read` spans use the standard 0.1x (90% discount) context-cache rate ($0.30 / 1M).
BQCA_INPUT_NON_CACHED_USD_PER_1M = 3.00
BQCA_INPUT_CACHED_USD_PER_1M = 0.30
BQCA_OUTPUT_USD_PER_1M = 20.00
VERTEX_FLASH_INPUT_USD_PER_1M = 0.30
VERTEX_FLASH_CACHED_USD_PER_1M = 0.03
VERTEX_FLASH_OUTPUT_USD_PER_1M = 2.50

DOMAIN_CATALOG_METADATA: list[dict[str, Any]] = [
    {
        "domain_id": "customer_marketing",
        "domain_label": "Customer CRM & Marketing Funnel",
        "sub_agent_name": "customer_marketing_subagent",
        "caa_agent_id": CUSTOMER_CA_ID,
        "caa_resource": CUSTOMER_CA_RESOURCE,
        "scoped_tables": ["users", "events", "orders", "order_items"],
        "glossary_terms": [
            {
                "term": "VIP Customer",
                "formula": "SUM(order_items.sale_price) >= $500 OR COUNT(DISTINCT order_id) >= 5",
            },
            {
                "term": "Dormant / Churned Customer",
                "formula": "Zero orders in last 90 days (orders.created_at)",
            },
            {
                "term": "Acquisition Traffic Source",
                "formula": "users.traffic_source IN ('Search','Email','Organic','Display','Facebook')",
            },
            {
                "term": "Cart Abandonment Rate (%)",
                "formula": "Cart sessions without purchase / Total cart sessions * 100",
            },
            {
                "term": "Average Order Value (AOV)",
                "formula": "SUM(sale_price) / COUNT(DISTINCT order_id)",
            },
        ],
    },
    {
        "domain_id": "product_profitability",
        "domain_label": "Product, Margin & Return Analytics",
        "sub_agent_name": "product_profitability_subagent",
        "caa_agent_id": PRODUCT_CA_ID,
        "caa_resource": PRODUCT_CA_RESOURCE,
        "scoped_tables": ["products", "order_items", "orders"],
        "glossary_terms": [
            {
                "term": "Product Gross Margin %",
                "formula": "SAFE_DIVIDE(retail_price - cost, retail_price) * 100",
            },
            {
                "term": "Net Revenue",
                "formula": "SUM(sale_price) WHERE status NOT IN ('Returned','Cancelled')",
            },
            {
                "term": "Realized Gross Profit",
                "formula": "SUM(sale_price - cost) excluding Returned & Cancelled items",
            },
            {
                "term": "Return & Cancellation Rate (%)",
                "formula": "COUNTIF(status IN ('Returned','Cancelled')) * 100.0 / COUNT(*)",
            },
        ],
    },
    {
        "domain_id": "supply_chain",
        "domain_label": "Supply Chain, Inventory & Fulfillment",
        "sub_agent_name": "supply_chain_logistics_subagent",
        "caa_agent_id": SUPPLY_CA_ID,
        "caa_resource": SUPPLY_CA_RESOURCE,
        "scoped_tables": ["distribution_centers", "inventory_items", "order_items", "orders", "products"],
        "glossary_terms": [
            {
                "term": "Distribution Center (DC)",
                "formula": "distribution_centers.id = products.distribution_center_id",
            },
            {
                "term": "Average Delivery Lead Time (Days)",
                "formula": "AVG(TIMESTAMP_DIFF(delivered_at, shipped_at, DAY))",
            },
            {
                "term": "Unsold Inventory Rate (%)",
                "formula": "COUNTIF(inventory_items.sold_at IS NULL) * 100.0 / COUNT(*)",
            },
            {
                "term": "Unsold Inventory Holding Cost ($)",
                "formula": "SUM(cost) WHERE inventory_items.sold_at IS NULL",
            },
        ],
    },
    {
        "domain_id": "store_channel",
        "domain_label": "Store Channel Sales & Returns",
        "sub_agent_name": "store_channel_subagent",
        "caa_agent_id": STORE_CA_ID,
        "caa_resource": f"projects/{PROJECT_ID}/locations/global/dataAgents/{STORE_CA_ID}",
        "scoped_tables": [
            "store_sales", "store_returns", "store", "date_dim", "time_dim", "item", "customer", "customer_address",
            "customer_demographics", "household_demographics", "income_band", "promotion", "reason",
        ],
        "glossary_terms": [
            {"term": "Store Net Sales / Net Profit", "formula": "SUM(ss_ext_sales_price) / SUM(ss_net_profit)"},
            {"term": "Store Return Amount Rate (%)", "formula": "SUM(sr_return_amt) * 100 / SUM(ss_ext_sales_price), aggregated separately"},
        ],
    },
    {
        "domain_id": "catalog_channel",
        "domain_label": "Catalog Channel Sales, Returns & Inventory",
        "sub_agent_name": "catalog_channel_subagent",
        "caa_agent_id": CATALOG_CA_ID,
        "caa_resource": f"projects/{PROJECT_ID}/locations/global/dataAgents/{CATALOG_CA_ID}",
        "scoped_tables": [
            "catalog_sales", "catalog_returns", "catalog_page", "call_center", "inventory", "warehouse", "ship_mode",
            "date_dim", "item", "customer", "promotion",
        ],
        "glossary_terms": [
            {"term": "Catalog Net Sales / Net Profit", "formula": "SUM(cs_ext_sales_price) / SUM(cs_net_profit)"},
            {"term": "Warehouse Inventory On Hand", "formula": "inventory.inv_quantity_on_hand per weekly snapshot"},
        ],
    },
    {
        "domain_id": "web_channel",
        "domain_label": "Web Channel Sales & Returns",
        "sub_agent_name": "web_channel_subagent",
        "caa_agent_id": WEB_CA_ID,
        "caa_resource": f"projects/{PROJECT_ID}/locations/global/dataAgents/{WEB_CA_ID}",
        "scoped_tables": [
            "web_sales", "web_returns", "web_site", "web_page", "ship_mode", "warehouse", "time_dim", "date_dim", "item",
            "customer", "promotion",
        ],
        "glossary_terms": [
            {"term": "Web Net Sales / Net Profit", "formula": "SUM(ws_ext_sales_price) / SUM(ws_net_profit)"},
            {"term": "Web Return Amount Rate (%)", "formula": "SUM(wr_return_amt) * 100 / SUM(ws_ext_sales_price), aggregated separately"},
        ],
    },
]

_DEFAULT_USER_PROFILE = {
    "role": "Principal Supply Chain & Merchandising Analyst",
    "focus_department": "Women (Outerwear & Coats)",
    "focus_channel": "Search & Email",
}
_DEFAULT_PREFERRED_KPIS = [
    "VIP Customer Revenue",
    "Realized Gross Margin %",
    "Return & Cancellation Rate (%)",
    "DC Average Delivery Lead Time",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit_telemetry(event_type: str, payload: dict[str, Any]) -> None:
    q = TELEMETRY_QUEUE_VAR.get()
    if q is not None:
        q.put({"type": event_type, "data": payload})


def load_persistent_memory_store() -> dict[str, Any]:
    mem_file = _get_visitor_memory_file()
    if not mem_file.exists():
        return {
            "user_profiles": {},
            "sessions": {},
            "explicit_memories": [],
            "total_caa_queries_executed": 0,
        }
    try:
        return json.loads(mem_file.read_text(encoding="utf-8"))
    except Exception:
        return {
            "user_profiles": {},
            "sessions": {},
            "explicit_memories": [],
            "total_caa_queries_executed": 0,
        }


def save_persistent_memory_store(store: dict[str, Any]) -> None:
    try:
        mem_file = _get_visitor_memory_file()
        mem_file.parent.mkdir(parents=True, exist_ok=True)
        mem_file.write_text(
            json.dumps(store, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def reset_persistent_memory_store() -> None:
    mem_file = _get_visitor_memory_file()
    if mem_file.exists():
        try:
            mem_file.unlink()
        except Exception:
            pass


def _detect_matched_glossary_terms(query: str, sql: str, domain_id: str) -> list[str]:
    blob = f"{query} {sql}".lower()
    matched: list[str] = []
    checks = [
        ("VIP Customer (>= $500 / >= 5 Orders)", ["500", "vip", "having sum"]),
        ("Average Order Value (AOV)", ["aov", "average order", "count(distinct"]),
        ("Acquisition Traffic Source", ["traffic_source", "channel"]),
        ("Cart Abandonment Rate (%)", ["cart", "event_type", "abandon"]),
        ("Product Gross Margin %", ["retail_price", "margin"]),
        ("Realized Gross Profit & Net Revenue", ["not in ('returned'", "gross profit", "net revenue"]),
        ("Return & Cancellation Rate (%)", ["returned", "cancelled", "return"]),
        ("Distribution Center (DC)", ["distribution_center", "chicago", "memphis"]),
        ("Average Delivery Lead Time (Days)", ["delivered_at", "shipped_at", "timestamp_diff", "lead"]),
        ("Unsold Inventory Holding Cost ($)", ["sold_at is null", "inventory_items", "unsold"]),
    ]
    for label, kws in checks:
        if any(k in blob for k in kws):
            matched.append(label)
    if not matched:
        if domain_id == CUSTOMER_CA_ID:
            matched.append("Customer CRM Scoped Schema")
        elif domain_id == PRODUCT_CA_ID:
            matched.append("Merchandising Margin Scoped Schema")
        else:
            matched.append("Supply Chain Lead-Time Scoped Schema")
    return matched[:4]


async def _sync_store_into_adk_memory_service(
    inv_ctx: Any,
    app_name: str,
    user_id: str,
    store: dict[str, Any],
) -> None:
    if inv_ctx is None or getattr(inv_ctx, "memory_service", None) is None:
        return

    def _stable_id(text: str) -> str:
        # InMemoryMemoryService skips events whose id it already holds. A new Event gets a random id,
        # so without a content-derived id every sync would add the same entries again.
        return "ltm-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:24]

    rehydrated_events: list[Event] = []
    for sess_data in store.get("sessions", {}).values():
        for q_item in sess_data.get("domain_query_history", []):
            summary_txt = (
                f"[Past Domain Analysis] Domain={q_item.get('domain')} | "
                f"Question={q_item.get('query')} | Insight={q_item.get('answer_preview')}"
            )
            rehydrated_events.append(
                Event(
                    id=_stable_id(summary_txt),
                    author=q_item.get("caa_agent_id", "domain_caa_subagent"),
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=summary_txt)],
                    ),
                )
            )
    for mem_item in store.get("explicit_memories", []):
        text = mem_item.get("text", "").strip()
        if text:
            rehydrated_events.append(
                Event(
                    id=_stable_id(text),
                    author="long_term_memory_bank",
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=f"[Long-Term Executive Insight] {text}")],
                    ),
                )
            )
    if rehydrated_events:
        try:
            await inv_ctx.memory_service.add_events_to_memory(
                app_name=app_name,
                user_id=user_id,
                events=rehydrated_events,
                session_id="persisted_long_term_memory",
            )
        except Exception:
            pass


def _is_pure_user_text_turn(content: types.Content) -> bool:
    """True when a Content item is a fresh user prompt (not a tool function_response)."""
    if getattr(content, "role", "") != "user" or not getattr(content, "parts", None):
        return False
    has_text = any(bool(getattr(p, "text", None)) for p in content.parts)
    has_fn_resp = any(getattr(p, "function_response", None) is not None for p in content.parts)
    return has_text and not has_fn_resp


def _content_text(content: types.Content) -> str:
    return "\n".join(p.text for p in (content.parts or []) if getattr(p, "text", None)).strip()


def _user_prompt_texts(callback_context: CallbackContext) -> set[str]:
    """Texts the user actually typed in this session (events authored by `user`)."""
    texts: set[str] = set()
    try:
        events = callback_context.session.events
    except Exception:  # pylint: disable=broad-except
        return texts
    for ev in events:
        if getattr(ev, "author", "") == "user" and ev.content and ev.content.parts:
            t = _content_text(ev.content)
            if t:
                texts.add(t)
    return texts


def _compact_adk_llm_request_window(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """Upstream ADK Token Diet: bounds `llm_request.contents` to the last `MAX_ADK_UPSTREAM_USER_TURNS`
    user prompts so `function_call`/`function_response` history never grows O(N) across long sessions.

    ADK hands another agent's tool calls to the current agent as user-role text ("For context: ...").
    Those are not user turns, so a turn boundary is a user-role text that the user really typed.
    """
    contents = getattr(llm_request, "contents", None)
    if not contents or not isinstance(contents, list):
        return None

    typed = _user_prompt_texts(callback_context)

    def is_user_prompt(c: types.Content) -> bool:
        if not _is_pure_user_text_turn(c):
            return False
        text = _content_text(c)
        return (text in typed) if typed else not text.startswith("For context:")

    user_turn_indices = [idx for idx, c in enumerate(contents) if is_user_prompt(c)]
    if len(user_turn_indices) > MAX_ADK_UPSTREAM_USER_TURNS:
        cut_idx = user_turn_indices[-MAX_ADK_UPSTREAM_USER_TURNS]
        dropped_count = cut_idx
        llm_request.contents = contents[cut_idx:]
        callback_context.state["temp:adk_compacted_contents_dropped"] = dropped_count
    else:
        callback_context.state["temp:adk_compacted_contents_dropped"] = 0
    return None


def _record_vertex_llm_usage_telemetry(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Captures 100% real Vertex AI `usage_metadata` after every non-partial ADK LLM call."""
    if getattr(llm_response, "partial", False):
        return None
    um = getattr(llm_response, "usage_metadata", None)
    if um is None:
        return None

    prompt_tok = int(getattr(um, "prompt_token_count", 0) or 0)
    cand_tok = int(getattr(um, "candidates_token_count", 0) or 0)
    thought_tok = int(getattr(um, "thoughts_token_count", 0) or 0)
    cached_tok = int(getattr(um, "cached_content_token_count", 0) or 0)
    total_tok = int(getattr(um, "total_token_count", 0) or (prompt_tok + cand_tok + thought_tok))

    record = {
        "timestamp": _utc_now_iso(),
        "agent_name": getattr(callback_context, "agent_name", "adk_agent"),
        "prompt_token_count": prompt_tok,
        "cached_content_token_count": cached_tok,
        "candidates_token_count": cand_tok,
        "thoughts_token_count": thought_tok,
        "output_and_thoughts_token_count": cand_tok + thought_tok,
        "total_token_count": total_tok,
        "compacted_contents_dropped": int(callback_context.state.get("temp:adk_compacted_contents_dropped", 0)),
    }

    collector = ADK_USAGE_COLLECTOR_VAR.get()
    if collector is not None:
        collector.append(record)

    usage_log = list(callback_context.state.get("adk_llm_usage_log", []))
    usage_log.append(record)
    callback_context.state["adk_llm_usage_log"] = usage_log[-30:]
    return None


async def _initialize_session_and_rehydrate_memory(callback_context: CallbackContext) -> None:
    state = callback_context.state
    session = callback_context.session
    user_id = callback_context.user_id or "analyst_01"
    app_name = session.app_name or "cymbal_agentic_bi_showcase"

    store = load_persistent_memory_store()
    persisted_user = store.get("user_profiles", {}).get(user_id, {})
    is_new_session = "session_started_at" not in state

    if is_new_session:
        state["session_started_at"] = _utc_now_iso()
        state["session_turn_count"] = 0
        state["active_domain"] = "Root Router"
        state["domain_query_history"] = []
        state["compact_routing_digest"] = []
        state["domain_ca_multiturn_messages"] = {}
        state["adk_llm_usage_log"] = []

    if is_new_session or "user:profile" not in state:
        state["user:profile"] = persisted_user.get("profile", dict(_DEFAULT_USER_PROFILE))
    if is_new_session or "user:preferred_kpis" not in state:
        state["user:preferred_kpis"] = persisted_user.get("preferred_kpis", list(_DEFAULT_PREFERRED_KPIS))
    if is_new_session or "user:pinned_insights" not in state:
        state["user:pinned_insights"] = persisted_user.get("pinned_insights", [])
    if is_new_session or "app:total_caa_queries_executed" not in state:
        state["app:total_caa_queries_executed"] = store.get("total_caa_queries_executed", 0)

    inv_ctx = callback_context._invocation_context  # pylint: disable=protected-access
    await _sync_store_into_adk_memory_service(inv_ctx, app_name, user_id, store)


async def _save_session_to_long_term_memory(
    callback_context: CallbackContext,
) -> types.Content | None:
    session = callback_context.session
    state = callback_context.state
    user_id = callback_context.user_id or "analyst_01"
    app_name = session.app_name or "cymbal_agentic_bi_showcase"

    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass

    store = load_persistent_memory_store()
    existing_user = store.get("user_profiles", {}).get(user_id, {})

    cur_profile = state.get("user:profile")
    merged_profile = (
        cur_profile
        if (cur_profile and cur_profile != _DEFAULT_USER_PROFILE)
        else (existing_user.get("profile") or cur_profile or dict(_DEFAULT_USER_PROFILE))
    )
    cur_kpis = state.get("user:preferred_kpis")
    merged_kpis = (
        cur_kpis
        if (cur_kpis and cur_kpis != _DEFAULT_PREFERRED_KPIS)
        else (existing_user.get("preferred_kpis") or cur_kpis or list(_DEFAULT_PREFERRED_KPIS))
    )
    cur_pinned = state.get("user:pinned_insights") or existing_user.get("pinned_insights", [])

    store.setdefault("user_profiles", {})[user_id] = {
        "profile": merged_profile,
        "preferred_kpis": merged_kpis,
        "pinned_insights": cur_pinned,
        "updated_at": _utc_now_iso(),
    }
    store["total_caa_queries_executed"] = max(
        int(store.get("total_caa_queries_executed", 0)),
        int(state.get("app:total_caa_queries_executed", 0)),
    )

    existing_sess = store.get("sessions", {}).get(session.id, {})
    cur_history = state.get("domain_query_history") or existing_sess.get("domain_query_history", [])
    store.setdefault("sessions", {})[session.id] = {
        "session_id": session.id,
        "user_id": user_id,
        "updated_at": _utc_now_iso(),
        "active_domain": state.get("active_domain", "Root Router"),
        "domain_query_history": cur_history[-15:],
    }
    save_persistent_memory_store(store)

    inv_ctx = callback_context._invocation_context  # pylint: disable=protected-access
    await _sync_store_into_adk_memory_service(inv_ctx, app_name, user_id, store)
    return None


def _get_cloud_platform_adc():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(PROJECT_ID)
    return creds


def _format_markdown_table(rows: list[dict[str, Any]], max_rows: int = 20) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = [
        "| " + " | ".join(str(r.get(h, "")) for h in headers) + " |"
        for r in rows[:max_rows]
    ]
    footer = (
        f"\n*(Top {max_rows} of {len(rows)} rows — Slim 20-Row Token Diet applied)*"
        if len(rows) > max_rows
        else f"\n*(Total {len(rows)} rows)*"
    )
    return "\n".join([header_line, sep_line, *body_lines]) + footer


def _record_caa_result_into_session_state(
    state: Any,
    agent_id: str,
    domain_label: str,
    data_agent_name: str,
    query: str,
    generated_sql: str,
    rows: list[dict[str, Any]],
    ca_final_answer: str,
    session_id: str = "active_session",
    user_id: str = "analyst_01",
) -> None:
    # 1. `temp:*` Turn-only buffer (auto-evicted post-turn; never serialized into LLM prompt)
    state["temp:last_caa_domain"] = domain_label
    state["temp:last_caa_agent"] = data_agent_name
    state["temp:last_caa_sql"] = generated_sql
    state["temp:last_caa_row_count"] = len(rows)
    state["temp:last_caa_rows"] = rows[:20]

    turn_num = int(state.get("session_turn_count", 0)) + 1
    state["session_turn_count"] = turn_num
    state["active_domain"] = domain_label

    prior_agent_msgs = list((state.get("domain_ca_multiturn_messages") or {}).get(agent_id, []))[-6:]
    msgs_sent_this_turn = len(prior_agent_msgs) + 1

    # Full audit record stored in Session.state for UI/telemetry inspection and MemoryService indexing
    history_entry = {
        "turn": turn_num,
        "timestamp": _utc_now_iso(),
        "domain": domain_label,
        "caa_agent_id": agent_id,
        "query": query,
        "generated_sql": generated_sql,
        "markdown_table": _format_markdown_table(rows, max_rows=20),
        "multiturn_context_messages_sent": msgs_sent_this_turn,
        "row_count": len(rows),
        "answer_preview": ca_final_answer[:280],
    }
    history = list(state.get("domain_query_history", []))
    history.append(history_entry)
    state["domain_query_history"] = history[-15:]

    # Ultra-lightweight Cross-Domain Filter Digest (<= 3 items, 1 line each, zero SQL bloat -> < 90 tokens!)
    first_sentence = (ca_final_answer.split("\n")[0] if ca_final_answer else "")[:140]
    digest = list(state.get("compact_routing_digest", []))
    digest.append(f"T{turn_num} [{agent_id}]: Q='{query[:90]}' -> {first_sentence}")
    state["compact_routing_digest"] = digest[-3:]

    # 2. `session` Sliding Window (`[-6:]` = max 3 turns = 6 compact messages per domain)
    multiturn_map = dict(state.get("domain_ca_multiturn_messages", {}))
    agent_msgs = list(multiturn_map.get(agent_id, []))
    agent_msgs.append({"userMessage": {"text": query}})
    sys_summary = ca_final_answer or f"Returned {len(rows)} rows."
    agent_msgs.append({"systemMessage": {"text": {"parts": [sys_summary[:900]]}}})
    multiturn_map[agent_id] = agent_msgs[-6:]
    state["domain_ca_multiturn_messages"] = multiturn_map

    # 3. `user:*` Auto-pin high-signal anomalies across sessions
    if any(k in (ca_final_answer + " " + generated_sql).lower() for k in ["nordic", "memphis", "returned", "lead"]):
        pinned = list(state.get("user:pinned_insights", []))
        auto_note = (
            f"[{domain_label}] {ca_final_answer[:220].replace(chr(10), ' ')}"
            if ca_final_answer
            else f"[{domain_label}] Verified query executed ({len(rows)} rows)."
        )
        if not any(p.get("insight") == auto_note for p in pinned):
            pinned.append({"timestamp": _utc_now_iso(), "insight": auto_note})
            state["user:pinned_insights"] = pinned[-8:]

    # 4. `app:*` Global telemetry counter + disk sync
    store = load_persistent_memory_store()
    new_total = max(
        int(store.get("total_caa_queries_executed", 0)),
        int(state.get("app:total_caa_queries_executed", 0)),
    ) + 1
    state["app:total_caa_queries_executed"] = new_total
    store["total_caa_queries_executed"] = new_total

    sess_entry = store.setdefault("sessions", {}).setdefault(
        session_id,
        {"session_id": session_id, "user_id": user_id, "domain_query_history": []},
    )
    sess_entry["updated_at"] = _utc_now_iso()
    sess_entry["active_domain"] = domain_label
    sess_entry["domain_query_history"] = state["domain_query_history"][-15:]
    if state.get("user:pinned_insights"):
        u_prof = store.setdefault("user_profiles", {}).setdefault(user_id, {})
        u_prof["profile"] = state.get("user:profile", dict(_DEFAULT_USER_PROFILE))
        u_prof["preferred_kpis"] = state.get("user:preferred_kpis", list(_DEFAULT_PREFERRED_KPIS))
        u_prof["pinned_insights"] = state.get("user:pinned_insights", [])
        u_prof["updated_at"] = _utc_now_iso()
    save_persistent_memory_store(store)


def _query_domain_caa_agent(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Calls a BigQuery CAA Data Agent and records the raw result in the per-invocation collector."""
    res = _query_domain_caa_agent_impl(*args, **kwargs)
    collector = CAA_CALL_COLLECTOR_VAR.get()
    if collector is not None:
        collector.append(res)
    return res


def _query_domain_caa_agent_impl(
    agent_id: str,
    domain_id: str,
    domain_label: str,
    query: str,
    tool_context: ToolContext | None = None,
    prior_messages_override: list[dict[str, Any]] | None = None,
    include_raw_thoughts_for_baseline: bool = False,
    max_table_rows: int = 20,
) -> dict[str, Any]:
    t0 = time.monotonic()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    data_agent_name = f"projects/{PROJECT_ID}/locations/global/dataAgents/{agent_id}"
    session = AuthorizedSession(_get_cloud_platform_adc())
    url = f"https://geminidataanalytics.googleapis.com/v1/projects/{PROJECT_ID}/locations/global:chat"

    messages: list[dict[str, Any]] = []
    if prior_messages_override is not None:
        messages.extend(prior_messages_override[-6:] if not include_raw_thoughts_for_baseline else prior_messages_override)
    elif tool_context is not None:
        multiturn_map = tool_context.state.get("domain_ca_multiturn_messages", {})
        if isinstance(multiturn_map, dict) and agent_id in multiturn_map:
            messages.extend(multiturn_map[agent_id][-6:])
    messages.append({"userMessage": {"text": query}})

    _emit_telemetry(
        "step",
        {
            "phase": "caa_execution",
            "detail": f"Calling {agent_id} (:chat stateless DataAgentContext, {len(messages)} msg window)...",
            "active_domains": [domain_id],
        },
    )

    payload = {
        "messages": messages,
        "dataAgentContext": {"dataAgent": data_agent_name},
    }
    headers = {"Content-Type": "application/json"}

    chunks: list[dict[str, Any]] = []
    accumulator = ""
    try:
        with session.post(url, json=payload, headers=headers, stream=True, timeout=95) as resp:
            if not resp.ok:
                return {
                    "status": "ERROR",
                    "domain_id": domain_id,
                    "domain": domain_label,
                    "data_agent": data_agent_name,
                    "error_details": f"HTTP {resp.status_code}: {resp.text[:400]}",
                }
            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if decoded == "[{":
                    accumulator = "{"
                elif decoded == "}]":
                    accumulator += "}"
                elif decoded == ",":
                    continue
                else:
                    accumulator += decoded
                try:
                    parsed = json.loads(accumulator)
                    accumulator = ""
                    if isinstance(parsed, dict):
                        chunks.append(parsed)
                except ValueError:
                    continue
    except Exception as exc:
        return {
            "status": "ERROR",
            "domain_id": domain_id,
            "domain": domain_label,
            "data_agent": data_agent_name,
            "error_details": str(exc),
        }

    thoughts: list[str] = []
    final_texts: list[str] = []
    generated_sql = ""
    rows: list[dict[str, Any]] = []

    for item in chunks:
        sm = item.get("systemMessage", {})
        if not isinstance(sm, dict):
            continue
        if "text" in sm and isinstance(sm["text"], dict):
            parts = sm["text"].get("parts", [])
            text_type = sm["text"].get("textType", "")
            joined = "".join(str(p) for p in parts).strip()
            if joined:
                if text_type in ("THOUGHT", "PROGRESS"):
                    thoughts.append(joined)
                else:
                    final_texts.append(joined)
        if "data" in sm and isinstance(sm["data"], dict):
            data_obj = sm["data"]
            if data_obj.get("generatedSql"):
                generated_sql = data_obj["generatedSql"].strip()
            res_obj = data_obj.get("result")
            if isinstance(res_obj, dict) and isinstance(res_obj.get("data"), list):
                rows = res_obj["data"]

    latency_ms = int((time.monotonic() - t0) * 1000)
    markdown_table = _format_markdown_table(rows, max_rows=max_table_rows)
    ca_final_answer = "\n\n".join(final_texts).strip()
    glossary_matched = _detect_matched_glossary_terms(query, generated_sql, agent_id)
    raw_thoughts_chars = sum(len(t) for t in thoughts)

    if tool_context is not None and not include_raw_thoughts_for_baseline:
        _record_caa_result_into_session_state(
            state=tool_context.state,
            agent_id=agent_id,
            domain_label=domain_label,
            data_agent_name=data_agent_name,
            query=query,
            generated_sql=generated_sql,
            rows=rows,
            ca_final_answer=ca_final_answer,
            session_id=tool_context.session.id,
            user_id=tool_context.user_id or "analyst_01",
        )

    result_payload: dict[str, Any] = {
        "status": "SUCCESS",
        "domain_id": domain_id,
        "domain": domain_label,
        "data_agent": data_agent_name,
        "query": query,
        "multiturn_context_messages_sent": len(messages),
        "glossary_matched": glossary_matched,
        "generated_sql": generated_sql,
        "row_count": len(rows),
        "markdown_table": markdown_table,
        "ca_final_answer": ca_final_answer,
        "stripped_thought_chars": raw_thoughts_chars,
        "latency_ms": latency_ms,
        "started_at_utc": started_at_utc,
    }
    if include_raw_thoughts_for_baseline:
        # Simulates ADK default `ask_data_agent` returning full THOUGHT logs + up to 50 raw JSON rows to the parent LLM
        result_payload["raw_thoughts_log"] = thoughts
        result_payload["raw_rows_json"] = rows[:50]
    return result_payload


async def save_user_preference_and_memory(
    role: str = "",
    focus_department: str = "",
    focus_channel: str = "",
    preferred_kpis_csv: str = "",
    key_insight_to_remember: str = "",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Saves executive profile preferences (`user:*`) and explicit cross-session insights (`MemoryService`)."""
    if tool_context is None:
        return {"status": "ERROR", "message": "ToolContext required."}

    state = tool_context.state
    user_id = tool_context.user_id or "analyst_01"
    app_name = tool_context.session.app_name or "cymbal_agentic_bi_showcase"

    store = load_persistent_memory_store()
    existing_user = store.get("user_profiles", {}).get(user_id, {})

    profile = dict(state.get("user:profile") or existing_user.get("profile") or _DEFAULT_USER_PROFILE)
    if role.strip():
        profile["role"] = role.strip()
    if focus_department.strip():
        profile["focus_department"] = focus_department.strip()
    if focus_channel.strip():
        profile["focus_channel"] = focus_channel.strip()
    state["user:profile"] = profile

    if preferred_kpis_csv.strip():
        kpis = [k.strip() for k in preferred_kpis_csv.split(",") if k.strip()]
        if kpis:
            state["user:preferred_kpis"] = kpis

    pinned = list(state.get("user:pinned_insights") or existing_user.get("pinned_insights", []))
    summary_parts = [
        f"[Executive Profile] Role={profile.get('role')}, FocusDept={profile.get('focus_department')}, "
        f"Channel={profile.get('focus_channel')}, KPIs={state.get('user:preferred_kpis')}"
    ]
    if key_insight_to_remember.strip():
        clean_ins = key_insight_to_remember.strip()
        if not any(p.get("insight") == clean_ins for p in pinned):
            pinned.append({"timestamp": _utc_now_iso(), "insight": clean_ins})
        state["user:pinned_insights"] = pinned[-10:]
        summary_parts.append(f"[Pinned Insight] {clean_ins}")

    memory_text = " | ".join(summary_parts)
    store.setdefault("user_profiles", {})[user_id] = {
        "profile": state["user:profile"],
        "preferred_kpis": state.get("user:preferred_kpis", []),
        "pinned_insights": state.get("user:pinned_insights", []),
        "updated_at": _utc_now_iso(),
    }
    store.setdefault("explicit_memories", []).append(
        {"timestamp": _utc_now_iso(), "user_id": user_id, "text": memory_text}
    )
    save_persistent_memory_store(store)

    inv_ctx = tool_context._invocation_context  # pylint: disable=protected-access
    await _sync_store_into_adk_memory_service(inv_ctx, app_name, user_id, store)

    return {
        "status": "SUCCESS",
        "updated_user_profile": state["user:profile"],
        "updated_preferred_kpis": state.get("user:preferred_kpis", []),
        "pinned_insights": state.get("user:pinned_insights", [])[-5:],
    }


async def inspect_session_and_memory_status(
    memory_search_query: str = "Nordic Luxe Memphis return lead time",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Retrieves current 4-Scope ADK Session State and cross-session Long-Term Memory matches (Zero BigQuery scan)."""
    if tool_context is None:
        return {"status": "ERROR", "message": "ToolContext required."}

    session = tool_context.session
    state = tool_context.state
    user_id = tool_context.user_id or "analyst_01"
    app_name = session.app_name or "cymbal_agentic_bi_showcase"

    store = load_persistent_memory_store()
    inv_ctx = tool_context._invocation_context  # pylint: disable=protected-access
    await _sync_store_into_adk_memory_service(inv_ctx, app_name, user_id, store)

    matched_memories: list[dict[str, str]] = []
    try:
        mem_resp = await tool_context.search_memory(memory_search_query)
        for m in mem_resp.memories[:6]:
            parts_text = " ".join(
                p.text
                for p in (m.content.parts if m.content and m.content.parts else [])
                if getattr(p, "text", None)
            )
            matched_memories.append({"author": m.author or "agent", "text_preview": parts_text[:280]})
    except Exception:
        pass

    return {
        "status": "SUCCESS",
        "current_session_id": session.id,
        "session_turn_count": state.get("session_turn_count", 0),
        "user_profile": state.get("user:profile"),
        "preferred_kpis": state.get("user:preferred_kpis"),
        "pinned_insights": state.get("user:pinned_insights", []),
        "memory_service_matches": matched_memories[:5],
        "explicit_memories": store.get("explicit_memories", [])[-5:],
    }


# The tool functions are async and run the blocking HTTP call in a worker thread. ADK invokes sync
# tools on the event loop, so a sync tool that waits 20-40s on `:chat` stalls every other request.
def _llm_view(res: dict[str, Any]) -> dict[str, Any]:
    """What the calling LLM sees and what stays in session history: the answer and the capped table.

    SQL, THOUGHT text, raw rows and metadata are left out. They are replayed on every later LLM call
    and add nothing the model needs to route or to restate a follow-up question.
    """
    if res.get("status") != "SUCCESS":
        return {"status": res.get("status", "ERROR"), "error_details": res.get("error_details", "")}
    return {"status": "SUCCESS", "answer": res.get("ca_final_answer", ""), "markdown_table": res.get("markdown_table", "")}


async def _ask_domain(agent_id: str, domain_id: str, domain_label: str, query: str, tool_context: ToolContext | None) -> dict[str, Any]:
    res = await asyncio.to_thread(
        _query_domain_caa_agent,
        agent_id=agent_id,
        domain_id=domain_id,
        domain_label=domain_label,
        query=query,
        tool_context=tool_context,
    )
    if res.get("status") == "SUCCESS" and tool_context is not None:
        # BQCA already wrote the answer. Skipping the summarization call saves one LLM round trip per turn.
        tool_context.actions.skip_summarization = True
    return _llm_view(res)


async def ask_customer_marketing_caa(query: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Queries the Customer & Marketing data agent (users, events, orders, order_items)."""
    return await _ask_domain(CUSTOMER_CA_ID, "customer_marketing", "Customer CRM & Marketing Funnel", query, tool_context)


async def ask_product_profitability_caa(query: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Queries the Product & Profitability data agent (products, order_items, orders)."""
    return await _ask_domain(PRODUCT_CA_ID, "product_profitability", "Product, Margin & Return Analytics", query, tool_context)


async def ask_supply_chain_logistics_caa(query: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Queries the Supply Chain data agent (distribution_centers, inventory_items, order_items, orders, products)."""
    return await _ask_domain(SUPPLY_CA_ID, "supply_chain", "Supply Chain, Inventory & Fulfillment", query, tool_context)


async def ask_store_channel_caa(query: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Queries the Store Channel data agent (store_sales, store_returns, store and their dimensions; 1998-2003)."""
    return await _ask_domain(STORE_CA_ID, "store_channel", "Store Channel Sales & Returns", query, tool_context)


async def ask_catalog_channel_caa(query: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Queries the Catalog Channel data agent (catalog_sales, catalog_returns, call_center, inventory, warehouse; 1998-2003)."""
    return await _ask_domain(CATALOG_CA_ID, "catalog_channel", "Catalog Channel Sales, Returns & Inventory", query, tool_context)


async def ask_web_channel_caa(query: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Queries the Web Channel data agent (web_sales, web_returns, web_site, web_page; 1998-2003)."""
    return await _ask_domain(WEB_CA_ID, "web_channel", "Web Channel Sales & Returns", query, tool_context)


async def ask_enterprise_warehouse_caa(query: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Queries the warehouse-wide data agent (all 32 tables). Costs about twice the input of a domain data agent."""
    return await _ask_domain(BASELINE_CA_ID, "enterprise_warehouse", "Enterprise Warehouse (all tables)", query, tool_context)


async def run_cross_domain_caa_analysis(
    customer_marketing_query: str = "",
    product_profitability_query: str = "",
    supply_chain_logistics_query: str = "",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Runs 2 or 3 domain data agents concurrently. Pass one targeted sub-question per domain needed."""
    full = await asyncio.to_thread(
        run_cross_domain_caa_analysis_sync,
        customer_marketing_query,
        product_profitability_query,
        supply_chain_logistics_query,
        tool_context,
    )
    return {
        "status": full.get("status"),
        "domain_results": {label: _llm_view(res) for label, res in full.get("domain_results", {}).items()},
    }


def run_cross_domain_caa_analysis_sync(
    customer_marketing_query: str = "",
    product_profitability_query: str = "",
    supply_chain_logistics_query: str = "",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Blocking implementation: 2 or 3 Domain-Scoped CAA calls in parallel (`ThreadPoolExecutor`)."""
    tasks: list[tuple[str, str, str, str]] = []
    if customer_marketing_query.strip():
        tasks.append((
            CUSTOMER_CA_ID,
            "customer_marketing",
            "Customer CRM & Marketing Funnel",
            customer_marketing_query.strip(),
        ))
    if product_profitability_query.strip():
        tasks.append((
            PRODUCT_CA_ID,
            "product_profitability",
            "Product, Margin & Return Analytics",
            product_profitability_query.strip(),
        ))
    if supply_chain_logistics_query.strip():
        tasks.append((
            SUPPLY_CA_ID,
            "supply_chain",
            "Supply Chain, Inventory & Fulfillment",
            supply_chain_logistics_query.strip(),
        ))

    if not tasks:
        return {"status": "NO_QUERIES_PROVIDED"}

    multiturn_snapshot: dict[str, list[dict[str, Any]]] = {}
    if tool_context is not None:
        raw_map = tool_context.state.get("domain_ca_multiturn_messages", {})
        if isinstance(raw_map, dict):
            multiturn_snapshot = {k: list(v)[-6:] for k, v in raw_map.items() if isinstance(v, list)}

    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        future_map = {
            pool.submit(
                _query_domain_caa_agent,
                aid,
                did,
                dlabel,
                q,
                None,
                multiturn_snapshot.get(aid, []),
            ): (aid, did, dlabel, q)
            for aid, did, dlabel, q in tasks
        }
        collector = CAA_CALL_COLLECTOR_VAR.get()
        for fut, (aid, did, dlabel, q) in future_map.items():
            res = fut.result()
            results[dlabel] = res
            # Pool threads do not inherit contextvars, so record fan-out calls here.
            if collector is not None:
                collector.append(res)
            if tool_context is not None and res.get("status") == "SUCCESS":
                _record_caa_result_into_session_state(
                    state=tool_context.state,
                    agent_id=aid,
                    domain_label=f"Parallel Fan-out ({dlabel})",
                    data_agent_name=res.get("data_agent", ""),
                    query=q,
                    generated_sql=res.get("generated_sql", ""),
                    rows=[],
                    ca_final_answer=res.get("ca_final_answer", ""),
                    session_id=tool_context.session.id,
                    user_id=tool_context.user_id or "analyst_01",
                )

    return {
        "status": "SUCCESS",
        "executed_domains": len(tasks),
        "domain_results": results,
    }


# Agent instructions are fully static. Session state, the user profile and memory are NOT templated
# into the system instruction: a prefix that changes every turn cannot be served from the prompt cache
# and is re-sent on every LLM call. Profile and memory are read on demand through tools on the root.
_DOMAIN_GUIDE = (
    "`customer_marketing_subagent` (online shop customers: VIP, traffic source, AOV, cart abandonment), "
    "`product_profitability_subagent` (online shop products: margin, profit, returns by product or brand), "
    "`supply_chain_logistics_subagent` (online shop distribution centers, delivery lead time, inventory items), "
    "`store_channel_subagent` (retail store channel 1998-2003: store sales and returns, stores, promotions, return reasons, "
    "shopper education and income band), "
    "`catalog_channel_subagent` (retail catalog channel 1998-2003: catalog sales and returns, call centers, ship modes, "
    "catalog pages, warehouse inventory on hand), "
    "`web_channel_subagent` (retail web channel 1998-2003: web sales and returns, web sites, web pages)"
)

_FALLBACK_RULE = (
    "Only if a single result table has to join tables of several domains (for example comparing the store, catalog and web "
    "channels side by side), or no domain fits, use `enterprise_warehouse_subagent`: it queries all 32 tables in one call"
)

_FANOUT_CASE = (
    "the message lists separate questions (for example numbered parts) that belong to two or three different online shop "
    "domains (customers, products, supply chain)"
)

_SUB_AGENT_RULES = (
    "Rules:\n"
    "1. Call your data tool with a standalone English question that restates any filters, cohorts or columns "
    "the user refers to from earlier turns. Keep every condition of the user's question as written: product "
    "department, category and brand names, date ranges, and ID filters such as `order_id >= 9900000`. "
    "Do not drop, shorten or generalize them. The tool result is shown to the user as the answer.\n"
    "2. If the whole question belongs to one other domain, call `transfer_to_agent` for that sub-agent instead of calling your tool: "
    + _DOMAIN_GUIDE + ".\n"
    "3. If " + _FANOUT_CASE + ", or the user asks to save a preference or recall earlier sessions, call `transfer_to_agent` for "
    "`cymbal_enterprise_root_router`. It answers each part with its own scoped data agent in parallel.\n"
    "4. " + _FALLBACK_RULE + ". Call `transfer_to_agent` for it."
)

_AGENT_CALLBACKS = dict(
    before_agent_callback=_initialize_session_and_rehydrate_memory,
    after_agent_callback=_save_session_to_long_term_memory,
    before_model_callback=_compact_adk_llm_request_window,
    after_model_callback=_record_vertex_llm_usage_telemetry,
)

customer_marketing_subagent = LlmAgent(
    model="gemini-2.5-flash",
    name="customer_marketing_subagent",
    description="Customer CRM and marketing: VIP cohorts, acquisition traffic source, AOV, cart abandonment.",
    instruction="You are the Customer CRM & Marketing sub-agent.\n" + _SUB_AGENT_RULES,
    tools=[ask_customer_marketing_caa],
    **_AGENT_CALLBACKS,
)

product_profitability_subagent = LlmAgent(
    model="gemini-2.5-flash",
    name="product_profitability_subagent",
    description="Product and profitability: gross margin %, realized profit, return and cancellation rates.",
    instruction="You are the Product & Profitability sub-agent.\n" + _SUB_AGENT_RULES,
    tools=[ask_product_profitability_caa],
    **_AGENT_CALLBACKS,
)

supply_chain_logistics_subagent = LlmAgent(
    model="gemini-2.5-flash",
    name="supply_chain_logistics_subagent",
    description="Supply chain: distribution center delivery lead time and unsold inventory holding cost.",
    instruction="You are the Supply Chain & Fulfillment sub-agent.\n" + _SUB_AGENT_RULES,
    tools=[ask_supply_chain_logistics_caa],
    **_AGENT_CALLBACKS,
)

store_channel_subagent = LlmAgent(
    model="gemini-2.5-flash",
    name="store_channel_subagent",
    description="Retail store channel (1998-2003): store sales and returns, stores, promotions, return reasons, shopper demographics.",
    instruction="You are the Store Channel sub-agent.\n" + _SUB_AGENT_RULES,
    tools=[ask_store_channel_caa],
    **_AGENT_CALLBACKS,
)

catalog_channel_subagent = LlmAgent(
    model="gemini-2.5-flash",
    name="catalog_channel_subagent",
    description="Retail catalog channel (1998-2003): catalog sales and returns, call centers, ship modes, warehouse inventory on hand.",
    instruction="You are the Catalog Channel sub-agent.\n" + _SUB_AGENT_RULES,
    tools=[ask_catalog_channel_caa],
    **_AGENT_CALLBACKS,
)

web_channel_subagent = LlmAgent(
    model="gemini-2.5-flash",
    name="web_channel_subagent",
    description="Retail web channel (1998-2003): web sales and returns by web site and web page.",
    instruction="You are the Web Channel sub-agent.\n" + _SUB_AGENT_RULES,
    tools=[ask_web_channel_caa],
    **_AGENT_CALLBACKS,
)

enterprise_warehouse_subagent = LlmAgent(
    model="gemini-2.5-flash",
    name="enterprise_warehouse_subagent",
    description="Fallback on the warehouse-wide data agent (all 32 tables): questions that combine several domains in one result or fit no domain.",
    instruction=(
        "You are the warehouse-wide fallback sub-agent. Your data tool queries all 32 tables in one call.\n"
        "Rules:\n"
        "1. Call your data tool with a standalone English question that keeps every condition of the user's question as written. "
        "The tool result is shown to the user as the answer.\n"
        "2. If the question fits exactly one domain, call `transfer_to_agent` for that sub-agent instead, because it costs less: "
        + _DOMAIN_GUIDE + ".\n"
        "3. If " + _FANOUT_CASE + ", or the user asks to save a preference or recall earlier sessions, "
        "call `transfer_to_agent` for `cymbal_enterprise_root_router`."
    ),
    tools=[ask_enterprise_warehouse_caa],
    **_AGENT_CALLBACKS,
)

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="cymbal_enterprise_root_router",
    description="Root router for six domain-scoped BigQuery CAA sub-agents and a warehouse-wide fallback, with session state and cross-session memory.",
    instruction=(
        "You are the Enterprise Agentic BI root orchestrator.\n"
        "1. Saving a profile or preference, or recalling earlier sessions, the profile or pinned insights: call "
        "`save_user_preference_and_memory` or `inspect_session_and_memory_status` and answer from the result. Do not run SQL for recall.\n"
        "2. Question that fits one domain: delegate with `transfer_to_agent` to that sub-agent: " + _DOMAIN_GUIDE + ".\n"
        "3. Only if " + _FANOUT_CASE + ": call `run_cross_domain_caa_analysis` with one targeted sub-question per part, "
        "then give a short synthesis. Copy into each sub-question every condition the user gave for that part: product department, "
        "category and brand names, date ranges, and ID filters such as `order_id >= 9900000`. Do not drop, shorten or generalize them. "
        "Never use this tool for a question that one domain can answer: VIP counts, revenue or AOV by traffic source is a customer "
        "question only.\n"
        "4. " + _FALLBACK_RULE + ". Delegate with `transfer_to_agent`."
    ),
    sub_agents=[
        customer_marketing_subagent,
        product_profitability_subagent,
        supply_chain_logistics_subagent,
        store_channel_subagent,
        catalog_channel_subagent,
        web_channel_subagent,
        enterprise_warehouse_subagent,
    ],
    tools=[
        load_memory,
        run_cross_domain_caa_analysis,
        save_user_preference_and_memory,
        inspect_session_and_memory_status,
    ],
    **_AGENT_CALLBACKS,
)


adk_app = App(
    name="bq_caa_3domain_multi_agent",
    root_agent=root_agent,
)
