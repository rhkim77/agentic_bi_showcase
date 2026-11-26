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
2. **Challenge 2 — Token use in two tiers (`ADK` and `BQCA`)**:
   - BQCA re-reads the schema and glossary bound to a data agent on each of its internal LLM calls, so one data agent bound to a whole documented warehouse costs about twice the BQCA input of a domain-scoped one in the measurements below.
   - The default ADK agent replays the full session, including each raw `ask_data_agent` response, on every LLM call, so its prompt grows with the number of turns.

---

## 2. `As-Is` vs. `To-Be` Scorecard (Measured 2026-11-26)

Both pipelines ran on Google Cloud through the same engine as the portal's live workbench ([`scripts/04_run_scenario_benchmarks.py`](./scripts/04_run_scenario_benchmarks.py), results in [`benchmarks/scenario_benchmark_results.json`](./benchmarks/scenario_benchmark_results.json)). Nothing in this table is modeled.

- **`As-Is`**: a plain ADK agent using the built-in data agent tools (`ask_data_agent`) on one data agent bound to all 32 tables and the glossary of every domain.
- **`To-Be`**: the Root Router with three Sub-Agents, each calling a data agent bound to 3 to 5 tables and its own glossary.
- **ADK tokens**: `Vertex AI usage_metadata` prompt tokens of every LLM call in the turn.
- **BQCA tokens**: `gen_ai.usage.*` of the `generate_content` spans that BQCA wrote to Cloud Trace for the chat calls of the turn.
- **Cost**: measured tokens at list prices (BQCA `$3.00` input, `$0.30` cached input, `$20.00` output per 1M; `gemini-2.5-flash` `$0.30`, `$0.03`, `$2.50`). BigQuery query cost is not included.

| Scenario | ADK prompt As-Is | ADK prompt To-Be | BQCA input As-Is | BQCA input To-Be | Total input As-Is | Total input To-Be | Total delta | Cost As-Is | Cost To-Be | BQCA calls As-Is / To-Be | Latency As-Is / To-Be |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| `S1` schema scoping | 5,909 | 1,607 | 107,752 | 53,350 | 113,661 | 54,957 | **-51.6%** | $0.3493 | $0.1824 | 1 / 1 | 19.8s / 18.2s |
| `S2` follow-up question | 10,250 | 1,334 | 109,093 | 54,786 | 119,343 | 56,120 | **-53.0%** | $0.3726 | $0.2104 | 1 / 1 | 22.0s / 16.5s |
| `S3` domain switch | 15,076 | 2,638 | 108,215 | 53,996 | 123,291 | 56,634 | **-54.1%** | $0.3567 | $0.1896 | 1 / 1 | 22.5s / 15.5s |
| `S3` three-domain fan-out | 20,943 | 5,487 | 109,694 | 189,578 | 130,637 | 195,065 | **+49.3%** | $0.3839 | $0.5852 | 1 / 3 | 31.5s / 29.9s |
| `S4` turn 8 of the session | 34,202 | 2,675 | 161,574 | 55,711 | 195,776 | 58,386 | **-70.2%** | $0.2346 | $0.2199 | 1 / 1 | 22.6s / 19.1s |
| `S5` recall in a new session | 2,238 | 2,513 | 0 | 0 | 2,238 | 2,513 | **+12.3%** | $0.0011 | $0.0035 | 0 / 0 | 3.0s / 8.8s |

`S4` over 8 turns with 8 different questions: average total input per turn 164,027 (`As-Is`) vs 85,299 (`To-Be`), **-48.0%**; average cost per turn $0.3286 vs $0.2597, **-21.0%**. The `To-Be` ADK prompt stayed between 1,202 and 3,393 tokens per turn; the `As-Is` ADK prompt went from 6,502 to a maximum of 34,202.

How to read it:

- **Where `To-Be` uses fewer tokens**: single-domain questions. The scoped data agent reads about half the BQCA input of the monolithic one, and the `To-Be` ADK prompt stays small while the `As-Is` prompt grows with the session.
- **Where it does not**: a question spanning three domains makes three BQCA calls instead of one. When a question repeats one asked earlier in the session, the `As-Is` agent can answer from its own session history without calling BQCA, while the `To-Be` agents query again; this was observed in an earlier run and is why `S4` uses different questions.
- **`S5`**: neither side calls BQCA. `To-Be` answers from memory; `As-Is` replies that it has no memory of earlier sessions.
- **Limits**: one run per scenario on one day, and the answers of the two designs were not checked for correctness. BQCA input per turn varies between runs, partly because some turns report a second, mostly cache-read pass. The warehouse is a synthetic reproduction of an enterprise schema: 32 tables (thelook 7 and TPC-DS 25) with rule-generated table and column descriptions. On the original 7-table schema without descriptions the BQCA input of both designs was about the same.

---

## 3. Repository Structure & Quickstart

- **[`agents/bq_caa_3domain_multi_agent/agent.py`](./agents/bq_caa_3domain_multi_agent/agent.py)**: Production reference with `App(context_cache_config=ContextCacheConfig(...))`, 3 Domain-Scoped Sub-Agents, `before_model_callback` 3-turn compaction, `after_model_callback` `usage_metadata` telemetry, `[-6:]` sliding window, `ThreadPoolExecutor` parallel fan-out, and per-visitor isolated 4-Scope `Session.state` + `MemoryService`.
- **[`backend/main.py`](./backend/main.py)** & **[`backend/workbench_engine.py`](./backend/workbench_engine.py)**: FastAPI + real-time `SSE` (`POST /api/workbench/stream`) engine powering the **Interactive S1–S5 Progressive Dual A/B Workbench**, executing both `As-Is` (Monolithic / One-Shot / Unbounded) and `To-Be` (Scoped / Sliding Window / Compacted / Memory-Rehydrated) pipelines in parallel on Google Cloud for any custom evaluator prompt.
- **[`agents/bq_caa_streaming_agent/agent.py`](./agents/bq_caa_streaming_agent/agent.py)** & **[`agents/bq_caa_toolset_agent/agent.py`](./agents/bq_caa_toolset_agent/agent.py)**: Companion `SequentialAgent` custom `:chat` streamer and built-in `DataAgentToolset` baseline packages.
- **[`docs/ARCHITECTURE_AND_CONFIGURATION_GUIDE.md`](./docs/ARCHITECTURE_AND_CONFIGURATION_GUIDE.md)** & **[`docs/SCENARIO_WALKTHROUGH_AND_BENCHMARKS.md`](./docs/SCENARIO_WALKTHROUGH_AND_BENCHMARKS.md)**: Full architectural specification and A/B SQL/telemetry walkthrough.
- **[`docs/index.html`](./docs/index.html)** (`EN`) & **[`docs/index_ko.html`](./docs/index_ko.html)** (`KO`): Portals with the measured baseline, the live Dual A/B workbench and a list-price cost calculator.

```bash
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform"
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"

git clone https://github.com/rhkim77/agentic_bi_showcase.git
cd agentic_bi_showcase
uv sync
uv run python scripts/provision_enterprise_warehouse.py   # 32-table warehouse + monolithic As-Is data agent
uv run python scripts/refresh_demo_seed.py
uv run python scripts/provision_cymbal_caa_agents.py       # 3 domain-scoped To-Be data agents
uv run python scripts/04_run_scenario_benchmarks.py        # measured S1-S5 baseline
uv run python scripts/05_measure_bqca_tokens_from_trace.py # Cloud Trace medians used by the live workbench
uv run python scripts/build_outcome_portal.py
```

---

## 4. Official Public References

1. **Google Cloud — Integration Patterns for Data Agents**: [Integration patterns for data agents](https://cloud.google.com/gemini/docs/conversational-analytics-api/integration-patterns)
2. **Google Cloud — State Management for Data Agents**: [State management for data agents](https://cloud.google.com/gemini/docs/conversational-analytics-api/state-management)
3. **Google Cloud — Data Agents Pricing (`90%` Cached Input Rate)**: [Data Cloud Agents pricing](https://cloud.google.com/products/data-agents/pricing)
4. **Google ADK — Multi-Agent Systems & Context Caching**: [Multi-Agent Systems in ADK](https://google.github.io/adk-docs/agents/multi-agents/)
5. **Google ADK — 4-Scope Sessions, State & Memory**: [Session, State, and Memory in ADK](https://google.github.io/adk-docs/sessions/)
