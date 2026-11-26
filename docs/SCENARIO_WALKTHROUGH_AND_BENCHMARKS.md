# Scenario Walkthrough & Empirical Dual A/B Benchmark Report (`S1` – `S5`)

All five scenarios below run both pipelines (`As-Is` and `To-Be`) against `ryan-sandbox-agent.cymbal_enterprise_dw` (32 documented tables, 504 columns) through [`backend/workbench_engine.py`](../backend/workbench_engine.py) and [`scripts/04_run_scenario_benchmarks.py`](../scripts/04_run_scenario_benchmarks.py).

- **ADK tokens**: `Vertex AI usage_metadata` (`gemini-2.5-flash`) captured in `after_model_callback`.
- **BQCA tokens**: `gen_ai.usage.*` attributes summed from the OpenTelemetry `generate_content` spans written to Cloud Trace for each `:chat` call in the run.
- **Machine-readable results**: [`benchmarks/scenario_benchmark_results.json`](../benchmarks/scenario_benchmark_results.json), [`benchmarks/bqca_trace_token_calibration.json`](../benchmarks/bqca_trace_token_calibration.json), and [`benchmarks/reference_answers.json`](../benchmarks/reference_answers.json).

---

## 1. Measured Scorecard (2026-11-26, One Run per Scenario)

| Scenario | ADK prompt As-Is | ADK prompt To-Be | BQCA input As-Is | BQCA input To-Be | Total input As-Is | Total input To-Be | Total delta | Cost As-Is | Cost To-Be | BQCA calls As-Is / To-Be | Latency As-Is / To-Be |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| `S1` schema scoping | 6,593 | 1,712 | 162,669 | 81,090 | 169,262 | 82,802 | **-51.1%** | $0.2529 | $0.1645 | 1 / 1 | 24.0s / 23.3s |
| `S2` follow-up question | 11,925 | 1,493 | 109,243 | 54,887 | 121,168 | 56,380 | **-53.5%** | $0.3779 | $0.2078 | 1 / 1 | 26.2s / 16.6s |
| `S3` domain switch | 18,283 | 2,962 | 163,520 | 54,480 | 181,803 | 57,442 | **-68.4%** | $0.2617 | $0.1915 | 1 / 1 | 24.2s / 17.0s |
| `S3` three-domain fan-out | 53,407 | 5,659 | 323,986 | 191,527 | 377,393 | 197,186 | **-47.8%** | $1.0603 | $0.6710 | 3 / 3 | 62.0s / 34.2s |
| `S4` turn 8 of the session | 33,099 | 2,494 | 161,541 | 55,513 | 194,640 | 58,007 | **-70.2%** | $0.2381 | $0.2175 | 1 / 1 | 21.5s / 19.1s |
| `S5` recall in a new session | 2,238 | 2,476 | 0 | 0 | 2,238 | 2,476 | **+10.6%** | $0.0019 | $0.0028 | 0 / 0 | 4.9s / 6.8s |

---

## 2. Scenario-by-Scenario Findings

### Scenario `S1` — Routing & Domain Schema Scoping
- **Prompt**: `"Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days."`
- **Mechanism & Telemetry**: `cymbal_enterprise_root_router` delegates via `transfer_to_agent` to `customer_marketing_subagent` (`4` tables), ending on the tool response (`skip_summarization = True`). Total input: `82,802` vs `169,262` (`-51.1%`). Across 442 Cloud Trace turns collected on 2026-11-26, uncached single-pass medians are `54,718` (`cymbal_customer_marketing_ca`) vs `108,438` (`cymbal_enterprise_monolithic_ca`).
- **Reference SQL Check**: `To-Be` matched all 15 reference cells (`Search`: 203–204 VIPs, ~$88.3K VIP gross revenue, ~$248 AOV) in 5 of 5 spot-check runs; `As-Is` matched VIP counts in 5 of 5 runs but often computed channel revenue across all customers (~$608.5K).

### Scenario `S2` — Multi-Turn Follow-Up over Stateless `:chat`
- **Prompt**: `"Keep those exact columns from the previous result and join our 14-day cart session count and cart abandonment rate (%) for each traffic_source."`
- **Mechanism & Telemetry**: `As-Is` sends `[1 UserMessage]` to BQCA after replaying its full ADK session (`11,925` ADK prompt tokens), whereas `To-Be` stays in `customer_marketing_subagent` (`1,493` ADK prompt tokens, `-87.5%`) and attaches the domain's `[-6:]` message window (`3` messages sent to `:chat`). Total input: `56,380` vs `121,168` (`-53.5%`).
- **Nuance on Follow-Up Wording**: Both pipelines preserve the 30-day VIP customer counts and join 14-day cart abandonment accurately, but both usually compute 30-day revenue and AOV over all customers in each channel rather than VIP-only customers when combining the two CTEs. [`backend/reference_answers.py`](../backend/reference_answers.py) documents both readings explicitly.

### Scenario `S3` — Direct Peer Handoff & 3-Domain Parallel Fan-Out
- **Part A (Peer Switch)**: From active `customer_marketing_subagent`, `"Now pivot to Supply Chain: compare average delivery lead time in days and unsold inventory holding cost ($) across all distribution centers."` transfers directly to `supply_chain_logistics_subagent` with zero Root Router hop (`57,442` vs `181,803` total input, `-68.4%`; matched all 20 reference cells in 5 of 5 runs).
- **Part B (3-Domain Fan-Out)**: Dispatches three domain `:chat` calls concurrently via `ThreadPoolExecutor` (`34.2s` vs `62.0s` sequential 3-call `As-Is` run). Token delta depends on how many calls `As-Is` chooses to make: `-47.8%` when `As-Is` made 3 calls (`197,186` vs `377,393`), versus `+49.3%` in an earlier run where `As-Is` answered in 1 call (`195,065` vs `130,637`).

### Scenario `S4` — 8-Turn Session Scaling (`Vertex AI usage_metadata` + Cloud Trace)
- Across 8 distinct analytical questions in one session:
  - **`As-Is` ADK prompt tokens**: `5,760` → `9,851` → `14,710` → `20,442` → `25,223` → `27,590` → `30,184` → `33,099`.
  - **`To-Be` ADK prompt tokens**: `2,104`, `3,524`, `3,630`, `2,520`, `1,560`, `3,024`, `1,282`, `2,494` (`before_model_callback` evicted up to `29` older content items by Turn 8).
  - **8-Turn Average Total Input (ADK + BQCA)**: `75,406` (`To-Be`) vs `163,656` (`As-Is`), **`-53.9%`**; list-price average cost `$0.2316` vs `$0.3302` (**`-29.8%`**).

### Scenario `S5` — New-Session Recall via `user:*` State & `MemoryService`
- In a brand-new session (`tobe-s5-*` vs `asis-s5-*`), `To-Be` answers from rehydrated `user:*` state and `MemoryService` in `6.8s` with **`0` BQCA calls** (`2,476` ADK prompt tokens, `$0.0028`), whereas `As-Is` has no cross-session memory (`2,238` ADK prompt tokens, `+10.6%` ADK delta).
