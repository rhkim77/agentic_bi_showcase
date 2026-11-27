# Scenario Walkthrough & Measured Benchmarks (`S1`–`S5`)

Every figure below comes from [`benchmarks/scenario_benchmark_results.json`](../benchmarks/scenario_benchmark_results.json) (measured 2026-11-27; the run shown is one of three, see [`benchmarks/repeat_runs.json`](../benchmarks/repeat_runs.json) for all three), [`benchmarks/bqca_trace_token_calibration.json`](../benchmarks/bqca_trace_token_calibration.json) and [`benchmarks/answer_check_results.json`](../benchmarks/answer_check_results.json).

## 1. Measured Rows

| Scenario | ADK prompt As-Is | ADK prompt To-Be | BQCA input As-Is | BQCA input To-Be | Total input As-Is | Total input To-Be | Token delta | Cost As-Is | Cost To-Be | Cost delta | BQCA calls As-Is / To-Be | Latency As-Is / To-Be |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| `S1` online shop question (Customer) | 6,575 | 2,606 | 167,443 | 81,273 | 174,018 | 83,879 | **-51.8%** | $0.5489 | $0.2886 | **-47.4%** | 1 / 1 | 26.3s / 18.1s |
| `S1` retail store channel question | 5,429 | 2,589 | 110,080 | 108,883 | 115,509 | 111,472 | **-3.5%** | $0.3486 | $0.2077 | **-40.4%** | 1 / 1 | 19.5s / 46.0s |
| `S2` follow-up question | 14,267 | 1,863 | 229,120 | 55,977 | 243,387 | 57,840 | **-76.2%** | $0.5281 | $0.2280 | **-56.8%** | 1 / 1 | 30.7s / 21.7s |
| `S3` domain switch (Customer to Supply Chain) | 21,928 | 6,480 | 111,964 | 54,851 | 133,892 | 61,331 | **-54.2%** | $0.3785 | $0.1918 | **-49.3%** | 1 / 1 | 23.2s / 15.0s |
| `S3` separate questions on three online shop domains (fan-out) | 40,739 | 13,168 | 118,278 | 222,280 | 159,017 | 235,448 | **+48.1%** | $0.4583 | $0.7213 | **+57.4%** | 1 / 3 | 88.5s / 30.9s |
| `S3` three retail channels in one result (fallback) | 41,403 | 10,192 | 111,923 | 111,925 | 153,326 | 122,117 | **-20.4%** | $0.3769 | $0.3729 | **-1.1%** | 1 / 1 | 21.8s / 16.4s |
| `S4` turn 8 of the session | 34,500 | 6,365 | 291,352 | 117,471 | 325,852 | 123,836 | **-62.0%** | $0.5788 | $0.3158 | **-45.4%** | 1 / 1 | 36.9s / 18.5s |
| `S5` recall in a new session | 2,238 | 3,191 | 0 | 0 | 2,238 | 3,191 | **+42.6%** | $0.0013 | $0.0050 | **+296.8%** | 0 / 0 | 3.3s / 10.2s |

Token deltas of single rows mix cached and uncached BQCA turns (a cached pass has more input tokens and a lower cost), so read them with the cost column. Per data agent, the uncached medians are:

| Data agent | Domain | Tables | Uncached turns sampled | Median BQCA input per turn | vs warehouse-wide |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `cymbal_customer_marketing_ca` | Customer & Marketing (online shop) | 4 | 41 | 54,907 | -50.9% |
| `cymbal_product_profitability_ca` | Product & Profitability (online shop) | 3 | 12 | 50,461 | -54.9% |
| `cymbal_supply_chain_ca` | Supply Chain (online shop) | 5 | 23 | 55,180 | -50.7% |
| `cymbal_store_channel_ca` | Store Channel (retail) | 13 | 6 | 74,575 | -33.4% |
| `cymbal_catalog_channel_ca` | Catalog Channel (retail) | 11 | 7 | 74,345 | -33.6% |
| `cymbal_web_channel_ca` | Web Channel (retail) | 11 | 2 | 114,012 | +1.9% |
| `cymbal_enterprise_monolithic_ca` | Warehouse-wide (As-Is, and To-Be fallback) | 32 | 94 | 111,931 | baseline |

---

## 2. Scenario-by-Scenario Findings

### Scenario `S1` — Routing & Domain Schema Scoping
- **Online shop prompt**: `"Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days."` `cymbal_enterprise_root_router` delegates via `transfer_to_agent` to `customer_marketing_subagent` (4 tables), ending on the tool response (`skip_summarization = True`). Total input `83,879` vs `174,018` (`-51.8%`), cost `-47.4%`.
- **Retail store channel prompt**: `"For the retail store channel, show net sales and net profit by year."` The router delegates to `store_channel_subagent`, whose data agent holds 13 tables. Total input `111,472` vs `115,509` (`-3.5%`), cost `-40.4%`.

### Scenario `S2` — Multi-Turn Follow-Up over Stateless `:chat`
- **Prompt**: `"Keep those exact columns from the previous result and join our 14-day cart session count and cart abandonment rate (%) for each traffic_source."`
- `As-Is` sends `[1 UserMessage]` to BQCA after replaying its ADK session (`14,267` ADK prompt tokens); its root LLM writes the earlier conditions back into the question. `To-Be` stays in `customer_marketing_subagent` (`1,863` ADK prompt tokens) and attaches the domain's `[-6:]` message window. Total input `57,840` vs `243,387` (`-76.2%`), cost `-56.8%`.
- What this scenario shows is the token difference. In the answer check both designs gave the same kind of result on this follow-up: both usually computed 30-day revenue and AOV over all customers in each channel rather than VIP-only customers. [`backend/reference_answers.py`](../backend/reference_answers.py) documents both readings.

### Scenario `S3` — Domain Switch, Fan-Out and Fallback
- **Peer switch**: from the active `customer_marketing_subagent`, `"Now pivot to Supply Chain: compare average delivery lead time in days and unsold inventory holding cost ($) across all distribution centers."` transfers directly to `supply_chain_logistics_subagent` without a Root Router call. Total input `61,331` vs `133,892` (`-54.2%`), cost `-49.3%`.
- **Fan-out over three online shop domains**: three `:chat` calls run concurrently via `ThreadPoolExecutor` (`30.9s` vs `88.5s`). `As-Is` made 1 call(s) and `To-Be` 3 in this run: total input `235,448` vs `159,017` (`+48.1%`), cost `+57.4%`. When `As-Is` answers in one call, `To-Be` uses more input tokens.
- **Three retail channels in one result**: `"Compare net profit by year across the retail store, catalog and web channels side by side in one table."` needs tables of three domains in one query, so `To-Be` routes it to the fallback (`To-Be` called ['cymbal_enterprise_monolithic_ca']). Total input `122,117` vs `153,326` (`-20.4%`), cost `-1.1%`.

### Scenario `S4` — 8-Turn Session (`Vertex AI usage_metadata` + Cloud Trace)
- Eight different questions in one session, moving from the online shop domains to the three retail channels:
  - **`As-Is` ADK prompt tokens**: `5,604` → `9,042` → `13,261` → `18,142` → `22,856` → `26,354` → `28,588` → `34,500`.
  - **`To-Be` ADK prompt tokens**: `2,586`, `1,772`, `2,257`, `5,645`, `6,718`, `3,245`, `5,738`, `6,365` (`before_model_callback` dropped up to `21` older content items).
  - **8-turn average total input (ADK + BQCA)**: `81,374` (`To-Be`) vs `175,625` (`As-Is`), **`-53.7%`**; list-price average cost `$0.2285` vs `$0.3545` (**`-35.6%`**).
  - **BQCA calls over the session**: 8 BQCA calls for `To-Be` and 8 for `As-Is`.

### Scenario `S5` — New-Session Recall via `user:*` State & `MemoryService`
- In a brand-new session, `To-Be` answers through `inspect_session_and_memory_status` from rehydrated `user:*` state and `MemoryService` in `10.2s` with **`0` BQCA calls** (`3,191` ADK prompt tokens), whereas `As-Is` has no cross-session memory (`2,238` ADK prompt tokens). The baseline run saved no profile, so the profile in the answer is the default in `agent.py`; the findings it lists were pinned during the earlier sessions of the run.

---

## 3. Answer Check (5 Runs per Question, 2026-11-27)

[`scripts/07_answer_check.py`](../scripts/07_answer_check.py) sends each preset question that has a reference query through both pipelines and counts the runs in which every numeric cell of the reference rows appears in a side's result table or answer text.

| Question | To-Be: runs with every reference figure | As-Is: runs with every reference figure |
| :--- | :---: | :---: |
| `S1` online shop question | 5 of 5 | 3 of 5 |
| `S2` follow-up question | 0 of 5 | 0 of 5 |
| `S3` domain switch | 5 of 5 | 5 of 5 |
| `S3` three online shop domains | 0 of 5 | 1 of 5 |
| `S3` three retail channels in one result | 5 of 5 | 5 of 5 |
| `S4` preset question | 5 of 5 | 5 of 5 |
| `S1` retail store channel question | 5 of 5 | 5 of 5 |

This is a spot check with a small sample. A question can have more than one defensible reading, and answers vary between runs. A first run of the check the same day had 10 `To-Be` and 8 `As-Is` runs in which no reference figure was found. That run kept no outputs, so the cause is unknown; its counts are in the same file under `earlier_run`. The run reported here records output size and errors per run and had no such case.
