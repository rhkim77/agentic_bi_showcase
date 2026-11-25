# Scenario Walkthrough & Empirical PoC A/B Benchmark Report (`S1` – `S5`)

All five PoC verification scenarios below contrast **As-Is Anti-Patterns** directly against **To-Be Best Practices** on live Google Cloud infrastructure (`ryan-sandbox-agent.thelook_ecommerce_agent`, Vertex AI `gemini-2.5-flash` instrumented via ADK `after_model_callback` `usage_metadata`, and `geminidataanalytics.googleapis.com/v1` `:chat`). Machine-readable telemetry is stored in [`benchmarks/scenario_benchmark_results.json`](../benchmarks/scenario_benchmark_results.json) and rendered interactively in [`docs/index.html`](./index.html) (`EN`) and [`docs/index_ko.html`](./index_ko.html) (`KO`).

---

## Executive PoC Verification Scorecard

| Scenario & Target PoC Problem | As-Is Anti-Pattern (Measured) | To-Be Best Practice (Measured) | Token & Latency Delta | Core Engineering Proof |
| :--- | :--- | :--- | :--- | :--- |
| **`S1` · Routing & Schema Diet**<br/>*(Track 1 + Track 2)* | Runtime Discovery + Monolithic CAA (`122,137` 2-tier tok; ADK `11,373` tok; `$0.251/turn`) | Static `enum transfer_to_agent` + 4-Table Customer CAA (`15,737` 2-tier tok; ADK `4,298` tok; `$0.041/turn`) | **`-87.1%` Total Tokens**<br/>(**`-62.2%` ADK Prompt**) | Eliminates discovery overhead and arbitrary `spend >= 100` SQL guesses via Hop-1 VIP formula. |
| **`S2` · Stateless Multi-Turn**<br/>*(Track 1: State vs Stateless)* | Default ADK `ask_data_agent` (`[1 UserMessage]` sent -> **Turn-2 Context Amnesia**) | Stateless `:chat` + ADK `Session.state` `[-6:]` Window (`[3 Messages]` sent, `18,701` 2-tier tok) | **`-85.8%` Total Tokens**<br/>(`+257` BQCA window tok) | Live SQL diff proves As-Is drops Turn-1 VIP cohort while To-Be generates full `FULL OUTER JOIN`. |
| **`S3` · Peer Switch & Parallel Fan-Out**<br/>*(Track 1: Breaking Lock-In)* | Stateful `ConversationReference` (`1 Conv = 1 Agent` lock-in; `34.25 s` sequential 3-domain sum) | Direct Peer `transfer_to_agent` (`0` Root bounce) + `ThreadPoolExecutor(3)` over `:chat` (**`13.47 s`**) | **`2.54x` Faster (`-60.7%`)**<br/>**`-82.1%` Total Tokens** | Resolves cross-domain `Nordic Luxe` `50.0%` return <-> `Memphis TN (DC #1)` `6.0d` delay in 1 turn. |
| **`S4` · 5-Turn ADK `usage_metadata` & `90%` Cache**<br/>*(Track 2 Core)* | Unbounded `Session.events` (`Turn 1: 5,807 -> Turn 5: 51,376` measured ADK prompt tok; `$0.507` no-cache / `$0.306` cached) | `before_model_callback` 3-Turn Cap + Slim 20-Row Tool + `90%` Cached Prefix (`Turn 4: 3,806 -> Turn 5: 3,807` ADK tok; **`$0.041/turn`**) | **`-92.6%` ADK Prompt**<br/>**`-86.7%` Effective Cost** | Live `usage_metadata` proves `O(1)` flat ceiling (`3,806 -> 3,807` tok on Turn 5, `8` stale items evicted). |
| **`S5` · 4-Scope State & Memory Short-Circuit**<br/>*(Track 1 + Track 2)* | `+ New Session` wipes context -> forces full `110K+` BQCA re-query | `temp:*` evicted + `user:*` & `ADK MemoryService` Turn-1 recall (`6,753` ADK tok, **`0` BQCA tok**) | **`-93.9%` Total Tokens**<br/>(`$0.0039/turn`, `6.05 s`) | Answers on Turn 1 of `session-B` with **`0` BigQuery CAA calls and `0` BigQuery bytes scanned**. |

---

## Scenario `S1`: Eliminating Discovery Overhead & Monolithic DDL Bloat (`As-Is` vs `To-Be`)

- **Measured `Vertex AI usage_metadata` (`gemini-2.5-flash`)**:
  - **As-Is (`asis_discovery_monolithic_agent`)**: `prompt_token_count = 11,373`, `output_and_thoughts = 1,127` (`3` LLM calls) + `110,764` BQCA monolithic tokens = **`122,137` combined input tokens** (`$0.385/turn` uncached, `$0.251/turn` with implicit cache). Guessed `WHEN user_total_spend >= 100`.
  - **To-Be (`cymbal_enterprise_root_router` -> `customer_marketing_subagent`)**: `prompt_token_count = 4,298` (**`-62.2%`**), `output_and_thoughts = 589` + `11,439` BQCA scoped tokens = **`15,737` combined input tokens (`-87.1%`, `$0.0405/turn` effective cost)**. Enforced `HAVING SUM(sale_price) >= 500 OR COUNT(DISTINCT order_id) >= 5`.

---

## Scenario `S2`: Solving One-Shot Stateless Amnesia (`[1 Msg]` Failure vs. `ADK [-6:]` Continuity)

> **Turn-2 Follow-Up Prompt**: `"Keep those exact columns from the previous result and join our 14-day cart session count and cart abandonment rate (%) for each traffic_source."`

- **As-Is SQL (`ask_data_agent` Default — `1` Message Sent -> Context Amnesia)**:
  ```sql
  -- Completely lost Turn-1 30-day VIP customer count, gross revenue, and AOV!
  SELECT traffic_source,
         COUNT(DISTINCT CASE WHEN has_cart = 1 THEN session_id END) AS cart_session_count,
         ROUND((COUNT(DISTINCT CASE WHEN has_cart = 1 AND has_purchase = 0 THEN session_id END) * 100.0)
               / NULLIF(COUNT(DISTINCT CASE WHEN has_cart = 1 THEN session_id END), 0), 2) AS cart_abandonment_rate_pct
  FROM session_events
  GROUP BY traffic_source;
  ```
- **To-Be SQL (`ADK [-6:] Sliding Window` — `3` Messages Sent -> Full Context Preserved)**:
  ```sql
  -- Preserved Turn-1 30-day VIP cohort + revenue + AOV and joined 14-day cart abandonment via FULL OUTER JOIN!
  SELECT COALESCE(o.traffic_source, c.traffic_source) AS traffic_source,
         COALESCE(o.vip_customer_count, 0) AS vip_customer_count,
         COALESCE(o.total_gross_revenue, 0.0) AS total_gross_revenue,
         COALESCE(o.average_order_value, 0.0) AS average_order_value,
         COALESCE(c.cart_session_count, 0) AS cart_session_count,
         c.cart_abandonment_rate_pct AS cart_abandonment_rate_percentage
  FROM last_30_days_orders AS o
  FULL OUTER JOIN last_14_days_cart_events AS c ON o.traffic_source = c.traffic_source
  ORDER BY total_gross_revenue DESC;
  ```

---

## Scenario `S3`: Peer-to-Peer Domain Switch (`Path B`) & Lock-Free Parallel Fan-Out (`Path C`)

1. **Part A — Direct Peer Transfer (`0` Root Router Bounce)**:
   - Active `customer_marketing_subagent` pivoted directly to `supply_chain_logistics_subagent` (`agents_hop_trace = ['customer_marketing_subagent', 'supply_chain_logistics_subagent', 'supply_chain_logistics_subagent']`, `10,369` measured ADK prompt tokens), overcoming `ConversationReference`'s `1 Conversation = 1 DataAgent` lock-in.
2. **Part B — 3-Domain Concurrent `:chat` Execution (`ThreadPoolExecutor`)**:
   - Completed all 3 domain queries in **`13,472 ms` parallel wall-clock vs. `34,251 ms` sequential sum (`2.54x` speedup / `-60.7%` latency)**, pinpointing `Nordic Luxe`'s `50.0%` return rate (`$7,200` vs `$11,520` profit) alongside `Memphis TN (DC #1)`'s `6.0-day` delivery bottleneck (vs `2.0 days` at `Chicago IL`).

---

## Scenario `S4`: Live 5-Turn `Vertex AI usage_metadata` & `90%` Cached Input Cost Proof

Directly measured `prompt_token_count` captured by ADK `after_model_callback` on `gemini-2.5-flash` across 5 consecutive turns:

| Turn | As-Is Unbounded ADK (`usage_metadata`) | To-Be 3-Turn Compacted ADK (`usage_metadata`) | `before_model_callback` Evicted Items | ADK Tier Savings |
| :---: | ---: | ---: | :---: | ---: |
| **Turn 1** | `5,807 tok` | **`882 tok`** | `0` | `-84.8%` |
| **Turn 2** | `17,180 tok` | **`2,300 tok`** | `0` | `-86.6%` |
| **Turn 3** | `28,589 tok` | **`3,769 tok`** | `0` | `-86.8%` |
| **Turn 4** | `39,990 tok` | **`3,806 tok`** *(O(1) Ceiling)* | `4 items dropped` | `-90.5%` |
| **Turn 5** | `51,376 tok` | **`3,807 tok`** *(+1 tok!)* | `8 items dropped` | **`-92.6%`** |

- **Effective Per-Turn Cost on Turn 5** (combining Vertex AI `gemini-2.5-flash` + Data Cloud Agent PAYG `$3.00/1M` Non-Cached vs. **`$0.30/1M` `90%` Cached Input**):
  - As-Is Monolithic (`0%` Cache): `$0.5068 / turn`
  - As-Is Monolithic (`50%` Implicit Cache): `$0.3065 / turn`
  - **Proposed To-Be (`2-Tier Token Diet` + `65%` Cached Prefix @ `$0.30/1M`)**: **`$0.0406 / turn` (`-86.7%` net cost reduction even after applying cache discounts to both!)**

---

## Scenario `S5`: 4-Scope `Session.state` Isolation & `0-Token BQCA` Cross-Session Recall

- **`session-A` Post-Turn Verification**: `temp_scope_keys_after_turn = []` (100% of temporary row buffers evicted) while `user:profile` and `user:pinned_insights` persisted to `ADK MemoryService`.
- **`session-B` Turn-1 Recall**: Answered in **`6,050 ms`** using **`6,753` measured ADK prompt tokens**, **`0` BQCA calls (`0` BQCA tokens)**, and **`0` BigQuery bytes scanned (`$0.0039` effective turn cost)**.
