# Governed Multi-Agent Analytics with Google ADK & BigQuery CAA: State, Routing & 2-Tier Token Optimization Blueprint

> **PoC Reference Architecture, Live `As-Is` vs `To-Be` Benchmark Suite & Verification Portals**  
> **GitHub Repository**: [https://github.com/rhkim77/agentic_bi_showcase](https://github.com/rhkim77/agentic_bi_showcase)  
> **Live English Portal (`Cloud Run`)**: [https://cymbal-agentic-bi-showcase-gleccs7jxa-uc.a.run.app](https://cymbal-agentic-bi-showcase-gleccs7jxa-uc.a.run.app)  
> **Live Korean Verification Portal (`한국어 검증 사이트`)**: [https://cymbal-agentic-bi-showcase-gleccs7jxa-uc.a.run.app/ko](https://cymbal-agentic-bi-showcase-gleccs7jxa-uc.a.run.app/ko)

![End-to-End 3-Tier Enterprise System Architecture](./docs/diagrams/fig1_3tier_system_architecture.png)

---

## 1. Two Core Enterprise PoC Challenges Addressed

When integrating **Google Agent Development Kit (`google-adk`)** with **BigQuery Conversational Analytics (`BQCA` / `geminidataanalytics.googleapis.com/v1`)** for enterprise NL2SQL platforms, engineering teams consistently hit two architectural walls:

1. **Challenge 1 — `Root Agent <-> Sub-Agent (BQCA)` State, Stateless, Memory & Routing Friction**:
   - ADK's built-in `DataAgentToolset` (`ask_data_agent`) invokes runtime discovery (`_get_data_agent_info`) every turn and sends `[1 UserMessage]` only—causing **Turn-2 context amnesia**.
   - Conversely, BQCA's server-managed `ConversationReference` locks **`1 Conversation = 1 Fixed DataAgent`**, blocking cross-domain pivots, serializing multi-domain queries, and lacking `CMEK` support in `global`.
   - Without `App(context_cache_config=...)`, ADK `transfer_to_agent` swaps system instructions and invalidates prefix caches on every agent handoff.
2. **Challenge 2 — 2-Tier Token Explosion (`ADK Tier` + `BQCA Tier`)**:
   - Binding an entire warehouse schema into one monolithic `DataAgent` burns **`110,764+` BQCA input tokens/turn**, while ADK's default `include_contents='default'` replays raw JSON rows and `THOUGHT` logs—driving upstream ADK `prompt_token_count` from `5,807` (Turn 1) to **`51,376` (Turn 5)** and beyond.

---

## 2. Empirical `As-Is` vs. `To-Be` Benchmark Scorecard (Measured on GCP)

Executed live via [`scripts/04_run_scenario_benchmarks.py`](./scripts/04_run_scenario_benchmarks.py) with real **`Vertex AI usage_metadata`** (`after_model_callback`) and official **BQCA `90%` Cached Input (`$0.30/1M` vs `$3.00/1M`)** cost accounting ([`benchmarks/scenario_benchmark_results.json`](./benchmarks/scenario_benchmark_results.json)):

| PoC Scenario | As-Is Anti-Pattern (Measured) | To-Be Best Practice (Measured) | Measured Improvement |
| :--- | :--- | :--- | :--- |
| **`S1` · Routing & Schema Diet** | Discovery + Monolithic CAA (`122,137` 2-tier tok; ADK `11,373` tok; guessed `spend >= 100`) | Static `enum transfer_to_agent` + 4-Table Customer CAA (`15,737` 2-tier tok; ADK `4,298` tok) | **`-87.1%` Combined Tokens** (`-62.2%` ADK Prompt) + exact Hop-1 VIP SQL |
| **`S2` · Stateless Multi-Turn** | Default `ask_data_agent` (`[1 Msg]` -> dropped Turn-1 VIP cohort & revenue) | Stateless `:chat` + ADK `[-6:]` Window (`[3 Msgs]`, `18,701` 2-tier tok) | **100% Context Retention** (`FULL OUTER JOIN` generated) + **`-85.8%` Tokens** |
| **`S3` · Peer Switch & Parallel `:chat`** | `1 Conv = 1 Agent` lock-in; `34.25 s` sequential 3-domain execution | Direct Peer Transfer (`0` Root bounce) + `ThreadPoolExecutor(3)` (**`13.47 s`**) | **`2.54x` Faster (`-60.7%` Latency)** + **`-82.1%` Tokens** |
| **`S4` · 5-Turn ADK `usage_metadata` & `90%` Cache** | Unbounded ADK (`Turn 5 = 51,376` prompt tok; `$0.3065/turn` w/ cache) | `before_model_callback` 3-Turn Cap + Slim 20-Row + `90%` Cache (`Turn 5 = 3,807` ADK tok; **`$0.0406/turn`**) | **`-92.6%` ADK Prompt Tokens** (`O(1)` ceiling) + **`-86.7%` Effective Cost** |
| **`S5` · 4-Scope State & Memory Recall** | `+ New Session` amnesia -> `110K+` BQCA re-scan | `temp:*` evicted + `MemoryService` Turn-1 recall (`6,753` ADK tok, **`0` BQCA tok**) | **`0` BQCA Tokens / `0` BQ Bytes Scanned** (`6.05 s`, `$0.0039/turn`) |

---

## 3. Repository Structure & Quickstart

- **[`agents/bq_caa_3domain_multi_agent/agent.py`](./agents/bq_caa_3domain_multi_agent/agent.py)**: Production reference with `App(context_cache_config=ContextCacheConfig(...))`, 3 Domain-Scoped Sub-Agents, `before_model_callback` 3-turn compaction, `after_model_callback` `usage_metadata` telemetry, `[-6:]` sliding window, `ThreadPoolExecutor` parallel fan-out, and 4-Scope `Session.state` + `MemoryService`.
- **[`agents/bq_caa_streaming_agent/agent.py`](./agents/bq_caa_streaming_agent/agent.py)** & **[`agents/bq_caa_toolset_agent/agent.py`](./agents/bq_caa_toolset_agent/agent.py)**: Companion `SequentialAgent` custom `:chat` streamer and built-in `DataAgentToolset` baseline packages.
- **[`docs/ARCHITECTURE_AND_CONFIGURATION_GUIDE.md`](./docs/ARCHITECTURE_AND_CONFIGURATION_GUIDE.md)** & **[`docs/SCENARIO_WALKTHROUGH_AND_BENCHMARKS.md`](./docs/SCENARIO_WALKTHROUGH_AND_BENCHMARKS.md)**: Full architectural specification and A/B SQL/telemetry walkthrough.
- **[`docs/index.html`](./docs/index.html)** (`EN`) & **[`docs/index_ko.html`](./docs/index_ko.html)** (`KO`): Self-contained Outcome Verification Portals with interactive `90%` Cached Input FinOps simulator.

```bash
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform"
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"

git clone https://github.com/rhkim77/agentic_bi_showcase.git
cd agentic_bi_showcase
uv sync
uv run python scripts/refresh_demo_seed.py
uv run python scripts/provision_cymbal_caa_agents.py
uv run python scripts/04_run_scenario_benchmarks.py
uv run python scripts/build_outcome_portal.py
```

---

## 4. Official Public References

1. **Google Cloud — Integration Patterns for Data Agents**: [Integration patterns for data agents](https://cloud.google.com/gemini/docs/conversational-analytics-api/integration-patterns)
2. **Google Cloud — State Management for Data Agents**: [State management for data agents](https://cloud.google.com/gemini/docs/conversational-analytics-api/state-management)
3. **Google Cloud — Data Agents Pricing (`90%` Cached Input Rate)**: [Data Cloud Agents pricing](https://cloud.google.com/products/data-agents/pricing)
4. **Google ADK — Multi-Agent Systems & Context Caching**: [Multi-Agent Systems in ADK](https://google.github.io/adk-docs/agents/multi-agents/)
5. **Google ADK — 4-Scope Sessions, State & Memory**: [Session, State, and Memory in ADK](https://google.github.io/adk-docs/sessions/)
