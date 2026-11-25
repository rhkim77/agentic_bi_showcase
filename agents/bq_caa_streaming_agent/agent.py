"""Pattern B: Custom Streaming `BaseAgent` + `temp:*` State Handoff (`ca-api-adk-streaming` Pattern).

Demonstrates:
  1. `ConversationalAnalyticsStreamingAgent` (`BaseAgent`): Reconstructs multi-turn history from
     `ctx.session.events`, streams `:chat` chunks, and stores structured outputs in `temp:data_result`.
  2. `ExecutiveInsightSubAgent` (`LlmAgent`): Reads `{temp:data_result}` from session state with zero
     redundant BigQuery queries.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncGenerator

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.genai import types

from google.adk.agents import BaseAgent, LlmAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "ryan-sandbox-agent") or "ryan-sandbox-agent"
DATASET_ID = os.environ.get("BQ_DATASET_ID", "thelook_ecommerce_agent") or "thelook_ecommerce_agent"
DATA_AGENT_ID = os.environ.get("CAA_DATA_AGENT_ID", "cymbal_customer_marketing_ca")
DATA_AGENT_RESOURCE = f"projects/{PROJECT_ID}/locations/global/dataAgents/{DATA_AGENT_ID}"


def _build_multiturn_ca_messages(ctx: InvocationContext) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for ev in ctx.session.events:
        if not ev.content or not ev.content.parts:
            continue
        text = "\n".join(p.text for p in ev.content.parts if getattr(p, "text", None)).strip()
        if not text:
            continue
        if ev.content.role == "user":
            messages.append({"userMessage": {"text": text}})
        elif ev.author == "ca_query_agent":
            messages.append({"systemMessage": {"text": {"parts": [text]}}})
    return messages[-7:]


def _format_markdown_table(rows: list[dict[str, Any]], max_rows: int = 20) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = ["| " + " | ".join(str(r.get(h, "")) for h in headers) + " |" for r in rows[:max_rows]]
    return "\n".join([header_line, sep_line, *body_lines])


def _call_caa_stream_sync(project_id: str, data_agent_name: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if hasattr(credentials, "with_quota_project"):
        credentials = credentials.with_quota_project(project_id)
    session = AuthorizedSession(credentials)
    url = f"https://geminidataanalytics.googleapis.com/v1/projects/{project_id}/locations/global:chat"
    payload = {"messages": messages, "dataAgentContext": {"dataAgent": data_agent_name}}
    chunks: list[dict[str, Any]] = []
    accumulator = ""
    with session.post(url, json=payload, headers={"Content-Type": "application/json"}, stream=True, timeout=120) as resp:
        resp.raise_for_status()
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
    return chunks


class ConversationalAnalyticsStreamingAgent(BaseAgent):
    """Custom ADK BaseAgent streaming BigQuery CAA chunks and writing `temp:*` state."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        ctx.session.state["temp:data_result"] = ""
        messages = _build_multiturn_ca_messages(ctx)
        if not messages:
            return
        chunks = await asyncio.to_thread(_call_caa_stream_sync, PROJECT_ID, DATA_AGENT_RESOURCE, messages)
        sql_text = ""
        rows: list[dict[str, Any]] = []
        answer_parts: list[str] = []
        for item in chunks:
            sm = item.get("systemMessage", {})
            if "text" in sm and sm["text"].get("textType") not in ("THOUGHT", "PROGRESS"):
                answer_parts.append("".join(sm["text"].get("parts", [])))
            if "data" in sm:
                if sm["data"].get("generatedSql"):
                    sql_text = sm["data"]["generatedSql"].strip()
                res = sm["data"].get("result", {})
                if isinstance(res, dict) and isinstance(res.get("data"), list):
                    rows = res["data"]

        md_table = _format_markdown_table(rows)
        ctx.session.state["temp:data_result"] = md_table
        ctx.session.state["temp:generated_sql"] = sql_text
        combined = f"```sql\n{sql_text}\n```\n\n{md_table}\n\n" + "\n".join(answer_parts)
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.Content(role="model", parts=[types.Part.from_text(text=combined)]),
        )


ca_query_agent = ConversationalAnalyticsStreamingAgent(name="ca_query_agent")
insight_synthesizer = LlmAgent(
    model="gemini-2.5-flash",
    name="executive_insight_synthesizer",
    instruction=(
        "Synthesize 2 concise executive action items from `{temp:data_result?}` and `{temp:generated_sql?}` "
        "without re-querying BigQuery."
    ),
)

root_agent = SequentialAgent(
    name="bq_caa_streaming_pipeline",
    description="Pattern B Reference: Sequential `BaseAgent` CAA Streamer + `temp:*` State Synthesizer.",
    sub_agents=[ca_query_agent, insight_synthesizer],
)
