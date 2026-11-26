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
| `S1` schema scoping | 6,593 | 1,712 | 162,669 | 81,090 | 169,262 | 82,802 | **-51.1%** | $0.2529 | $0.1645 | 1 / 1 | 24.0s / 23.3s |
| `S2` follow-up question | 11,925 | 1,493 | 109,243 | 54,887 | 121,168 | 56,380 | **-53.5%** | $0.3779 | $0.2078 | 1 / 1 | 26.2s / 16.6s |
| `S3` domain switch | 18,283 | 2,962 | 163,520 | 54,480 | 181,803 | 57,442 | **-68.4%** | $0.2617 | $0.1915 | 1 / 1 | 24.2s / 17.0s |
| `S3` three-domain fan-out | 53,407 | 5,659 | 323,986 | 191,527 | 377,393 | 197,186 | **-47.8%** | $1.0603 | $0.6710 | 3 / 3 | 62.0s / 34.2s |
| `S4` turn 8 of the session | 33,099 | 2,494 | 161,541 | 55,513 | 194,640 | 58,007 | **-70.2%** | $0.2381 | $0.2175 | 1 / 1 | 21.5s / 19.1s |
| `S5` recall in a new session | 2,238 | 2,476 | 0 | 0 | 2,238 | 2,476 | **+10.6%** | $0.0019 | $0.0028 | 0 / 0 | 4.9s / 6.8s |

`S4` over 8 turns with 8 different questions: average total input per turn 163,656 (`As-Is`) vs 75,406 (`To-Be`), **-53.9%**; average cost per turn $0.3302 vs $0.2316, **-29.8%**. The `To-Be` ADK prompt stayed between 1,282 and 3,630 tokens per turn; the `As-Is` ADK prompt went from 5,760 to a maximum of 33,099.

How to read it:

- **Where `To-Be` uses fewer tokens**: single-domain questions. The scoped data agent reads about half the BQCA input of the monolithic one, and the `To-Be` ADK prompt stays small while the `As-Is` prompt grows with the session.
- **Where the result depends on the run**: for a question spanning three domains `To-Be` always makes one BQCA call per domain. The `As-Is` agent made 3 call(s) in this run (-47.8% for `To-Be`); in an earlier run it answered with a single call and `To-Be` used 49% more input tokens. When a question repeats one asked earlier in the session, the `As-Is` agent can answer from its own session history without calling BQCA, while the `To-Be` agents query again; this was observed in an earlier run and is why `S4` uses different questions.
- **`S5`**: neither side calls BQCA. `To-Be` answers from memory; `As-Is` replies that it has no memory of earlier sessions.
- **Answer check**: five preset questions have a hand-written reference query ([`backend/reference_answers.py`](./backend/reference_answers.py)); the portal shows its rows next to both answers. In 5 runs per question on 2026-11-26, a script checked whether every reference figure appeared in the answer. `To-Be`: `S1` 5 of 5, `S3` domain switch 5 of 5, three-domain question 4 of 5, `S4` preset 4 of 5, `S2` follow-up 0 of 5. `As-Is`: 0, 4, 1, 4 and 0 of 5. On the `S2` follow-up both designs usually computed revenue and AOV over all customers where the reference reads them as VIP-only, so that row is a difference in reading rather than a clear error. This is a spot check on five questions, not an accuracy evaluation, and the same question can give different answers on different runs.
- **Limits**: one run per scenario on one day for the token figures. BQCA input per turn varies between runs, partly because some turns report a second, mostly cache-read pass. The warehouse is a synthetic reproduction of an enterprise schema: 32 tables (thelook 7 and TPC-DS 25) with rule-generated table and column descriptions. On the original 7-table schema without descriptions the BQCA input of both designs was about the same.

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
uv run python scripts/06_build_reference_answers.py        # reference query snapshot for the preset questions (shown next to both answers)
uv run python scripts/build_outcome_portal.py
```

---

## 4. Official Public References

1. **Google Cloud — Integration Patterns for Data Agents**: [Integration patterns for data agents](https://cloud.google.com/gemini/docs/conversational-analytics-api/integration-patterns)
2. **Google Cloud — State Management for Data Agents**: [State management for data agents](https://cloud.google.com/gemini/docs/conversational-analytics-api/state-management)
3. **Google Cloud — Data Agents Pricing (`90%` Cached Input Rate)**: [Data Cloud Agents pricing](https://cloud.google.com/products/data-agents/pricing)
4. **Google ADK — Multi-Agent Systems & Context Caching**: [Multi-Agent Systems in ADK](https://google.github.io/adk-docs/agents/multi-agents/)
5. **Google ADK — 4-Scope Sessions, State & Memory**: [Session, State, and Memory in ADK](https://google.github.io/adk-docs/sessions/)
