"""Pattern A: ADK Built-in DataAgent Toolset Reference (`cymbal_customer_marketing_ca` vs. Baseline).

Demonstrates wrapping `google.adk.tools.data_agent.data_agent_tool` (`list_accessible_data_agents`,
`get_data_agent_info`, `ask_data_agent`) with Keyless Vertex AI Application Default Credentials
(`cloud-platform` OAuth scope), comparing Unscoped Baseline vs. Glossary-Governed Data Agents,
while illustrating why default `ask_data_agent` is One-Shot Stateless (1 UserMessage per turn).
"""

from __future__ import annotations

import os
from typing import Any

import google.auth
from google.adk.agents import LlmAgent
from google.adk.tools.data_agent import data_agent_tool
from google.adk.tools.data_agent.config import DataAgentToolConfig
from google.adk.tools.tool_context import ToolContext

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "ryan-sandbox-agent") or "ryan-sandbox-agent"
DATASET_ID = os.environ.get("BQ_DATASET_ID", "cymbal_enterprise_dw") or "cymbal_enterprise_dw"
BASELINE_CA_ID = os.environ.get("CYMBAL_BASELINE_CA_ID", "cymbal_enterprise_monolithic_ca")

GOVERNED_CUSTOMER_AGENT = f"projects/{PROJECT_ID}/locations/global/dataAgents/cymbal_customer_marketing_ca"
BASELINE_DATA_AGENT = f"projects/{PROJECT_ID}/locations/global/dataAgents/{BASELINE_CA_ID}"

_TOOL_SETTINGS = DataAgentToolConfig(
    max_query_result_rows=50,
    location="global",
)


def _get_cloud_platform_adc():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(PROJECT_ID)
    return creds


def list_accessible_data_agents(project_id: str = PROJECT_ID) -> dict[str, Any]:
    """Lists accessible BigQuery Conversational Analytics Data Agents in the target GCP project."""
    target_project = PROJECT_ID if not project_id or project_id == "your-gcp-project-id" else project_id
    return data_agent_tool.list_accessible_data_agents(
        project_id=target_project,
        credentials=_get_cloud_platform_adc(),
        settings=_TOOL_SETTINGS,
    )


def get_data_agent_info(data_agent_name: str) -> dict[str, Any]:
    """Fetches published table references and system instructions of a Data Agent."""
    if not data_agent_name.startswith("projects/"):
        data_agent_name = f"projects/{PROJECT_ID}/locations/global/dataAgents/{data_agent_name}"
    return data_agent_tool.get_data_agent_info(
        data_agent_name=data_agent_name,
        credentials=_get_cloud_platform_adc(),
        settings=_TOOL_SETTINGS,
    )


def ask_data_agent(
    query: str,
    data_agent_name: str = GOVERNED_CUSTOMER_AGENT,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Executes a single-turn (one-shot stateless) question against a BigQuery CAA Data Agent."""
    if not data_agent_name.startswith("projects/"):
        data_agent_name = f"projects/{PROJECT_ID}/locations/global/dataAgents/{data_agent_name}"
    return data_agent_tool.ask_data_agent(
        data_agent_name=data_agent_name,
        query=query,
        credentials=_get_cloud_platform_adc(),
        settings=_TOOL_SETTINGS,
        tool_context=tool_context,  # type: ignore[arg-type]
    )


root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="bq_caa_toolset_agent",
    description=(
        "Pattern A Reference: ADK data_agent_tool comparing Baseline Schema-Only vs. Glossary-Governed BigQuery CAA."
    ),
    instruction=(
        f"You are a BigQuery Conversational Analytics comparison coordinator on `{PROJECT_ID}.{DATASET_ID}`.\n"
        f"- Governed Scoped Data Agent: `{GOVERNED_CUSTOMER_AGENT}`\n"
        f"- Unscoped Baseline Data Agent: `{BASELINE_DATA_AGENT}`\n\n"
        "Guidelines:\n"
        "1. Use `ask_data_agent` on the Governed agent by default.\n"
        "2. When asked to compare Baseline vs. Governed SQL generation, invoke `ask_data_agent` against both agents and present a structured Markdown comparison of generated SQL and returned metrics."
    ),
    tools=[list_accessible_data_agents, get_data_agent_info, ask_data_agent],
)
