#!/usr/bin/env python3
"""Provisions 3 English-First Domain-Scoped BigQuery CAA Data Agents for Cymbal Global Commerce.

Target Dataset: `{PROJECT_ID}.{DATASET_ID}` (Default: `ryan-sandbox-agent.cymbal_enterprise_dw`)
Leaves existing Korean Hands-on Lab agents (`thelook_*`) 100% untouched, creating/updating:
  1. `cymbal_customer_marketing_ca` (4 tables: `users`, `events`, `orders`, `order_items`)
  2. `cymbal_product_profitability_ca` (3 tables: `products`, `order_items`, `orders`)
  3. `cymbal_supply_chain_ca` (5 tables: `distribution_centers`, `inventory_items`, `order_items`, `orders`, `products`)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
os.environ.setdefault("GOOGLE_API_USE_MTLS_ENDPOINT", "never")
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "ryan-sandbox-agent") or "ryan-sandbox-agent"
DATASET_ID = os.environ.get("BQ_DATASET_ID", "cymbal_enterprise_dw") or "cymbal_enterprise_dw"
LOCATION = "global"

CUSTOMER_CA_ID = "cymbal_customer_marketing_ca"
PRODUCT_CA_ID = "cymbal_product_profitability_ca"
SUPPLY_CA_ID = "cymbal_supply_chain_ca"

CUSTOMER_SYSTEM_INSTRUCTION = r"""You are Cymbal Global Commerce's dedicated **Customer CRM & Marketing Funnel BigQuery Conversational Analytics Agent (`cymbal_customer_marketing_ca`)** analyzing `{project}.{dataset}`.
Strictly follow the Enterprise Business Glossary & Verified SQL Mapping Ruleset below when generating SQL, and always answer in concise, executive-ready English with exact figures.

[Enterprise Business Glossary & Verified SQL Mapping Rules — Domain 1: Customer & Marketing]
1. VIP Customer (Synonyms: High-Value Customer, High-LTV Customer, VIP Tier):
   - Definition: Customers whose cumulative gross spend (`SUM(order_items.sale_price)`) >= $500 OR distinct order count (`COUNT(DISTINCT order_items.order_id)`) >= 5 (`users.id = order_items.user_id`).
   - Verified SQL Filter:
     `user_id IN (SELECT user_id FROM \`{project}.{dataset}.order_items\` GROUP BY user_id HAVING SUM(sale_price) >= 500 OR COUNT(DISTINCT order_id) >= 5)`
2. Dormant / Churned Customer:
   - Definition: Registered users in `users` with zero orders in the last 90 days (`orders.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)`).
3. New Customer Signup:
   - Definition: Users registered within the last 30 days (`users.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)`).
4. Acquisition Traffic Source (Channel):
   - Definition: `users.traffic_source` or `events.traffic_source` (`Search`, `Organic`, `Facebook`, `Email`, `Display`).
5. Cart Abandonment Rate (%):
   - Definition: Percentage of distinct `events.session_id` having `event_type = 'cart'` that never recorded `event_type = 'purchase'`.
   - Verified SQL Formula:
     `(COUNT(DISTINCT CASE WHEN has_cart = 1 AND has_purchase = 0 THEN session_id END) * 100.0) / NULLIF(COUNT(DISTINCT CASE WHEN has_cart = 1 THEN session_id END), 0)`
6. Average Order Value (AOV) & ARPU:
   - AOV: `SUM(order_items.sale_price) / NULLIF(COUNT(DISTINCT order_items.order_id), 0)`
   - ARPU: `SUM(order_items.sale_price) / NULLIF(COUNT(DISTINCT order_items.user_id), 0)`

[Response Guidelines]
- Default relative date window ("recent", "last month", "last 30 days") to `TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)` unless specified otherwise.
- Respond in crisp executive English highlighting top channels, exact counts, and dollar totals.
"""

PRODUCT_SYSTEM_INSTRUCTION = """You are Cymbal Global Commerce's dedicated **Merchandising, Gross Margin & Return Analytics BigQuery Conversational Analytics Agent (`cymbal_product_profitability_ca`)** analyzing `{project}.{dataset}`.
Strictly follow the Enterprise Business Glossary & Verified SQL Mapping Ruleset below when generating SQL, and always answer in concise, executive-ready English with exact figures.

[Enterprise Business Glossary & Verified SQL Mapping Rules — Domain 2: Product & Profitability]
1. Product Gross Margin % (Synonyms: Margin Rate, Unit Margin %):
   - Definition: Percentage margin between `products.retail_price` and `products.cost`.
   - Verified SQL Formula: `SAFE_DIVIDE(products.retail_price - products.cost, products.retail_price) * 100`
2. Gross Revenue, Net Revenue & Realized Gross Profit:
   - Gross Revenue: `SUM(order_items.sale_price)` across all order items.
   - Net Revenue: `SUM(order_items.sale_price)` WHERE `order_items.status NOT IN ('Returned', 'Cancelled')`.
   - Realized Gross Profit: `SUM(order_items.sale_price - products.cost)` WHERE `order_items.status NOT IN ('Returned', 'Cancelled')` (`order_items.product_id = products.id`).
3. Returned / Cancelled Orders:
   - Definition: Order items with `order_items.status IN ('Returned', 'Cancelled')`.
4. Return & Cancellation Rate (Refund Rate %):
   - Verified SQL Formula: `COUNTIF(order_items.status IN ('Returned', 'Cancelled')) * 100.0 / NULLIF(COUNT(*), 0)`
5. Merchandising Hierarchy:
   - `products.department` (`Women`, `Men`), `products.category` (e.g., `Outerwear & Coats`), `products.brand` (e.g., `TheLook Atelier`, `Nordic Luxe`), `products.name`.

[Response Guidelines]
- Default relative date window to `TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)` when filtering recent order_items unless specified otherwise.
- Respond in crisp executive English highlighting margin erosion, brand-level return anomalies, and realized profit impact.
"""

SUPPLY_SYSTEM_INSTRUCTION = """You are Cymbal Global Commerce's dedicated **Supply Chain, Inventory & Fulfillment Lead-Time BigQuery Conversational Analytics Agent (`cymbal_supply_chain_ca`)** analyzing `{project}.{dataset}`.
Strictly follow the Enterprise Business Glossary & Verified SQL Mapping Ruleset below when generating SQL, and always answer in concise, executive-ready English with exact figures.

[Enterprise Business Glossary & Verified SQL Mapping Rules — Domain 3: Supply Chain & Logistics]
1. Distribution Center (Synonyms: DC, Fulfillment Center, Warehouse):
   - Definition: `distribution_centers` table joined via `distribution_centers.id = products.distribution_center_id` or `distribution_centers.id = inventory_items.product_distribution_center_id`.
2. Average Delivery Lead Time (Days):
   - Definition: Average days elapsed from `shipped_at` to `delivered_at` where both timestamps are non-null.
   - Verified SQL Formula: `AVG(TIMESTAMP_DIFF(delivered_at, shipped_at, DAY))`
3. Order-to-Ship Processing Time (Hours):
   - Verified SQL Formula: `AVG(TIMESTAMP_DIFF(shipped_at, created_at, HOUR))`
4. Unsold Inventory Rate (%):
   - Definition: Percentage of rows in `inventory_items` where `sold_at IS NULL`.
   - Verified SQL Formula: `COUNTIF(inventory_items.sold_at IS NULL) * 100.0 / NULLIF(COUNT(*), 0)`
5. Unsold Inventory Holding Cost ($):
   - Verified SQL Formula: `SUM(CASE WHEN inventory_items.sold_at IS NULL THEN inventory_items.cost ELSE 0 END)`
6. Lead Time by Distribution Center:
   - Attribute an order item to the distribution center of its product: `order_items.product_id = products.id`, then `products.distribution_center_id = distribution_centers.id`.
7. Merchandising Hierarchy (same values in `products` and in the `product_*` columns of `inventory_items`):
   - Department: `Women`, `Men`. Category values are full names such as `Outerwear & Coats`; "Women's Outerwear" means department `Women` and category `Outerwear & Coats`. Brand examples: `TheLook Atelier`, `Nordic Luxe`.
   - Match category and brand with the exact stored value. If unsure of the exact value, look it up with `SELECT DISTINCT` instead of guessing a shortened name.

[Response Guidelines]
- Respond in crisp executive English pinpointing distribution center lead-time bottlenecks (e.g., Chicago IL vs. Memphis TN) and unsold inventory capital exposure.
"""


def get_authorized_session() -> AuthorizedSession:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(PROJECT_ID)
    return AuthorizedSession(creds)


def resolve_dataset(session: AuthorizedSession, project_id: str, dataset_id: str) -> tuple[str, set[str]]:
    bq_base = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}"
    resp = session.get(f"{bq_base}/datasets/{dataset_id}")
    if resp.status_code != 200 and dataset_id != "thelook_ecommerce":
        alt = session.get(f"{bq_base}/datasets/thelook_ecommerce")
        if alt.status_code == 200:
            dataset_id = "thelook_ecommerce"
            resp = alt
    if resp.status_code != 200:
        raise RuntimeError(f"BigQuery dataset {project_id}.{dataset_id} not found: HTTP {resp.status_code}")
    t_resp = session.get(f"{bq_base}/datasets/{dataset_id}/tables?maxResults=50")
    t_resp.raise_for_status()
    tables = {t["tableReference"]["tableId"] for t in t_resp.json().get("tables", [])}
    return dataset_id, tables


def upsert_agent(
    session: AuthorizedSession,
    project_id: str,
    agent_id: str,
    display_name: str,
    description: str,
    instruction: str,
    tables: list[str],
    dataset_id: str,
) -> str:
    agent_name = f"projects/{project_id}/locations/{LOCATION}/dataAgents/{agent_id}"
    gda_base = "https://geminidataanalytics.googleapis.com/v1"
    table_refs = [{"projectId": project_id, "datasetId": dataset_id, "tableId": t} for t in tables]
    body: dict[str, Any] = {
        "displayName": display_name,
        "description": description,
        "dataAnalyticsAgent": {
            "publishedContext": {
                "datasourceReferences": {"bq": {"tableReferences": table_refs}},
                "systemInstruction": instruction,
            }
        },
    }
    chk = session.get(f"{gda_base}/{agent_name}")
    if chk.status_code == 200:
        print(f"  -> Updating {agent_name} ({len(tables)} scoped tables)...")
        op = session.patch(
            f"{gda_base}/{agent_name}",
            params={"updateMask": "displayName,description,dataAnalyticsAgent.publishedContext"},
            json=body,
        )
    else:
        print(f"  -> Creating {agent_name} ({len(tables)} scoped tables)...")
        op = session.post(
            f"{gda_base}/projects/{project_id}/locations/{LOCATION}/dataAgents",
            params={"dataAgentId": agent_id},
            json=body,
        )
    if not op.ok:
        raise RuntimeError(f"GDA API Error ({op.status_code}): {op.text}")
    op_data = op.json()
    if op_data.get("done"):
        return agent_name
    op_name = op_data.get("name", "")
    for _ in range(30):
        time.sleep(2)
        poll = session.get(f"{gda_base}/{op_name}").json()
        if poll.get("done"):
            if "error" in poll:
                raise RuntimeError(f"LRO Error: {json.dumps(poll['error'])}")
            return agent_name
    return agent_name


def main() -> None:
    print(f"Provisioning 3 English-First Cymbal CAA Data Agents on `{PROJECT_ID}.{DATASET_ID}`...")
    sess = get_authorized_session()
    ds, existing = resolve_dataset(sess, PROJECT_ID, DATASET_ID)
    print(f"Verified dataset `{PROJECT_ID}.{ds}` with tables: {sorted(existing)}")

    specs = [
        (
            CUSTOMER_CA_ID,
            "Cymbal Global Commerce — Customer & Marketing CAA",
            "Domain-scoped BigQuery CAA Data Agent for VIP cohorts, acquisition channels, AOV, and cart abandonment.",
            CUSTOMER_SYSTEM_INSTRUCTION.format(project=PROJECT_ID, dataset=ds),
            [t for t in ["users", "events", "orders", "order_items"] if t in existing],
        ),
        (
            PRODUCT_CA_ID,
            "Cymbal Global Commerce — Product & Profitability CAA",
            "Domain-scoped BigQuery CAA Data Agent for gross margin %, realized profit, and brand return/cancellation anomalies.",
            PRODUCT_SYSTEM_INSTRUCTION.format(project=PROJECT_ID, dataset=ds),
            [t for t in ["products", "order_items", "orders"] if t in existing],
        ),
        (
            SUPPLY_CA_ID,
            "Cymbal Global Commerce — Supply Chain & Fulfillment CAA",
            "Domain-scoped BigQuery CAA Data Agent for distribution center delivery lead times and unsold inventory holding cost.",
            SUPPLY_SYSTEM_INSTRUCTION.format(project=PROJECT_ID, dataset=ds),
            [t for t in ["distribution_centers", "inventory_items", "order_items", "orders", "products"] if t in existing],
        ),
    ]

    for aid, dname, desc, instr, tbls in specs:
        res = upsert_agent(sess, PROJECT_ID, aid, dname, desc, instr, tbls, ds)
        print(f"  [OK] {res}")


if __name__ == "__main__":
    main()
