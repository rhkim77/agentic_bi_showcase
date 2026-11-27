#!/usr/bin/env python3
"""Provisions the 6 domain-scoped BigQuery CAA Data Agents for Cymbal Global Commerce.

Target Dataset: `{PROJECT_ID}.{DATASET_ID}` (Default: `ryan-sandbox-agent.cymbal_enterprise_dw`)
Leaves existing Korean Hands-on Lab agents (`thelook_*`) 100% untouched, creating/updating:
  1. `cymbal_customer_marketing_ca` (4 tables: `users`, `events`, `orders`, `order_items`)
  2. `cymbal_product_profitability_ca` (3 tables: `products`, `order_items`, `orders`)
  3. `cymbal_supply_chain_ca` (5 tables: `distribution_centers`, `inventory_items`, `order_items`, `orders`, `products`)
  4. `cymbal_store_channel_ca` (13 tables: store sales and returns with their dimensions)
  5. `cymbal_catalog_channel_ca` (11 tables: catalog sales and returns, call centers, inventory)
  6. `cymbal_web_channel_ca` (11 tables: web sales and returns, web sites and pages)
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
STORE_CA_ID = "cymbal_store_channel_ca"
CATALOG_CA_ID = "cymbal_catalog_channel_ca"
WEB_CA_ID = "cymbal_web_channel_ca"

# Tables that have to be joined in one SQL statement must sit in the same data agent. The retail
# channel tables form a star schema, so each channel agent carries the dimensions its facts join to.
STORE_TABLES = [
    "store_sales", "store_returns", "store", "date_dim", "time_dim", "item", "customer", "customer_address",
    "customer_demographics", "household_demographics", "income_band", "promotion", "reason",
]
CATALOG_TABLES = [
    "catalog_sales", "catalog_returns", "catalog_page", "call_center", "inventory", "warehouse", "ship_mode",
    "date_dim", "item", "customer", "promotion",
]
WEB_TABLES = [
    "web_sales", "web_returns", "web_site", "web_page", "ship_mode", "warehouse", "time_dim", "date_dim", "item",
    "customer", "promotion",
]

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

STORE_SYSTEM_INSTRUCTION = """You are Cymbal Global Commerce's dedicated **Store Channel BigQuery Conversational Analytics Agent (`cymbal_store_channel_ca`)** analyzing the retail warehouse tables in `{project}.{dataset}`.
Strictly follow the Enterprise Business Glossary & Verified SQL Mapping Ruleset below when generating SQL, and always answer in concise, executive-ready English with exact figures.

[Enterprise Business Glossary & Verified SQL Mapping Rules — Domain 4: Store Channel]
1. Store Net Sales and Store Net Profit:
   - Net Sales: `SUM(store_sales.ss_ext_sales_price)`. Net Profit: `SUM(store_sales.ss_net_profit)`.
2. Store Return Amount and Return Amount Rate (%):
   - Return Amount: `SUM(store_returns.sr_return_amt)`. Return Amount Rate: return amount * 100 / net sales.
   - Aggregate `store_sales` and `store_returns` separately on the same grouping keys, then join the two aggregates. Do not join sales rows to return rows directly.
3. Store Channel Calendar:
   - Sales year: `store_sales.ss_sold_date_sk = date_dim.d_date_sk`, then `date_dim.d_year`. Returns year: `store_returns.sr_returned_date_sk = date_dim.d_date_sk`.
   - Use an inner join to `date_dim`, so rows without a date are left out. The data covers 1998 to 2003; do not add a relative date filter.
4. Store, Item, Promotion and Return Reason:
   - `ss_store_sk = store.s_store_sk`, `ss_item_sk = item.i_item_sk`, `ss_promo_sk = promotion.p_promo_sk`, `sr_reason_sk = reason.r_reason_sk`.
5. Shopper Demographics:
   - Education: `ss_cdemo_sk = customer_demographics.cd_demo_sk` (`cd_education_status`). Income band: `ss_hdemo_sk = household_demographics.hd_demo_sk`, then `hd_income_band_sk = income_band.ib_income_band_sk` (`ib_lower_bound`, `ib_upper_bound`).
   - Customer: `ss_customer_sk = customer.c_customer_sk`. Address: `ss_addr_sk = customer_address.ca_address_sk`. Time of day: `ss_sold_time_sk = time_dim.t_time_sk`.

[Response Guidelines]
- Respond in crisp executive English with exact totals. Round money to 2 decimals.
"""

CATALOG_SYSTEM_INSTRUCTION = """You are Cymbal Global Commerce's dedicated **Catalog Channel BigQuery Conversational Analytics Agent (`cymbal_catalog_channel_ca`)** analyzing the retail warehouse tables in `{project}.{dataset}`.
Strictly follow the Enterprise Business Glossary & Verified SQL Mapping Ruleset below when generating SQL, and always answer in concise, executive-ready English with exact figures.

[Enterprise Business Glossary & Verified SQL Mapping Rules — Domain 5: Catalog Channel]
1. Catalog Net Sales and Catalog Net Profit:
   - Net Sales: `SUM(catalog_sales.cs_ext_sales_price)`. Net Profit: `SUM(catalog_sales.cs_net_profit)`.
2. Catalog Return Amount and Return Amount Rate (%):
   - Return Amount: `SUM(catalog_returns.cr_return_amount)`. Return Amount Rate: return amount * 100 / net sales.
   - Aggregate `catalog_sales` and `catalog_returns` separately on the same grouping keys, then join the two aggregates.
3. Catalog Channel Calendar:
   - Sales year: `catalog_sales.cs_sold_date_sk = date_dim.d_date_sk`, then `date_dim.d_year`. Returns year: `catalog_returns.cr_returned_date_sk = date_dim.d_date_sk`.
   - Use an inner join to `date_dim`. The data covers 1998 to 2003; do not add a relative date filter.
4. Call Center, Ship Mode, Catalog Page and Warehouse:
   - `cs_call_center_sk = call_center.cc_call_center_sk` (`cc_name`), `cs_ship_mode_sk = ship_mode.sm_ship_mode_sk` (`sm_type`), `cs_catalog_page_sk = catalog_page.cp_catalog_page_sk`, `cs_warehouse_sk = warehouse.w_warehouse_sk` (`w_warehouse_name`).
   - Item: `cs_item_sk = item.i_item_sk`. Customer: `cs_bill_customer_sk = customer.c_customer_sk`. Promotion: `cs_promo_sk = promotion.p_promo_sk`.
5. Warehouse Inventory On Hand:
   - `inventory.inv_quantity_on_hand` by `inv_warehouse_sk = warehouse.w_warehouse_sk`, `inv_item_sk = item.i_item_sk` and `inv_date_sk = date_dim.d_date_sk`. Inventory rows are weekly snapshots; average or pick one date, do not sum across dates.

[Response Guidelines]
- Respond in crisp executive English with exact totals. Round money to 2 decimals.
"""

WEB_SYSTEM_INSTRUCTION = """You are Cymbal Global Commerce's dedicated **Web Channel BigQuery Conversational Analytics Agent (`cymbal_web_channel_ca`)** analyzing the retail warehouse tables in `{project}.{dataset}`.
Strictly follow the Enterprise Business Glossary & Verified SQL Mapping Ruleset below when generating SQL, and always answer in concise, executive-ready English with exact figures.

[Enterprise Business Glossary & Verified SQL Mapping Rules — Domain 6: Web Channel]
1. Web Net Sales and Web Net Profit:
   - Net Sales: `SUM(web_sales.ws_ext_sales_price)`. Net Profit: `SUM(web_sales.ws_net_profit)`.
2. Web Return Amount and Return Amount Rate (%):
   - Return Amount: `SUM(web_returns.wr_return_amt)`. Return Amount Rate: return amount * 100 / net sales.
   - Aggregate `web_sales` and `web_returns` separately on the same grouping keys, then join the two aggregates.
3. Web Channel Calendar:
   - Sales year: `web_sales.ws_sold_date_sk = date_dim.d_date_sk`, then `date_dim.d_year`. Returns year: `web_returns.wr_returned_date_sk = date_dim.d_date_sk`.
   - Use an inner join to `date_dim`. The data covers 1998 to 2003; do not add a relative date filter.
4. Web Site, Web Page, Ship Mode and Warehouse:
   - `ws_web_site_sk = web_site.web_site_sk` (`web_name`), `ws_web_page_sk = web_page.wp_web_page_sk` (`wp_type`), `ws_ship_mode_sk = ship_mode.sm_ship_mode_sk` (`sm_type`), `ws_warehouse_sk = warehouse.w_warehouse_sk`.
   - Item: `ws_item_sk = item.i_item_sk`. Customer: `ws_bill_customer_sk = customer.c_customer_sk`. Promotion: `ws_promo_sk = promotion.p_promo_sk`. Time of day: `ws_sold_time_sk = time_dim.t_time_sk`.

[Response Guidelines]
- Respond in crisp executive English with exact totals. Round money to 2 decimals.
"""

# Order used wherever every domain instruction is needed (the monolithic As-Is agent carries all of them).
ALL_DOMAIN_INSTRUCTIONS = [
    CUSTOMER_SYSTEM_INSTRUCTION, PRODUCT_SYSTEM_INSTRUCTION, SUPPLY_SYSTEM_INSTRUCTION,
    STORE_SYSTEM_INSTRUCTION, CATALOG_SYSTEM_INSTRUCTION, WEB_SYSTEM_INSTRUCTION,
]


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
    t_resp = session.get(f"{bq_base}/datasets/{dataset_id}/tables?maxResults=200")
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
    print(f"Provisioning 6 domain-scoped Cymbal CAA Data Agents on `{PROJECT_ID}.{DATASET_ID}`...")
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
        (
            STORE_CA_ID,
            "Cymbal Global Commerce — Store Channel CAA",
            "Domain-scoped BigQuery CAA Data Agent for store sales, store returns, promotions and shopper demographics.",
            STORE_SYSTEM_INSTRUCTION.format(project=PROJECT_ID, dataset=ds),
            [t for t in STORE_TABLES if t in existing],
        ),
        (
            CATALOG_CA_ID,
            "Cymbal Global Commerce — Catalog Channel CAA",
            "Domain-scoped BigQuery CAA Data Agent for catalog sales and returns, call centers, ship modes and warehouse inventory.",
            CATALOG_SYSTEM_INSTRUCTION.format(project=PROJECT_ID, dataset=ds),
            [t for t in CATALOG_TABLES if t in existing],
        ),
        (
            WEB_CA_ID,
            "Cymbal Global Commerce — Web Channel CAA",
            "Domain-scoped BigQuery CAA Data Agent for web sales and returns by web site and web page.",
            WEB_SYSTEM_INSTRUCTION.format(project=PROJECT_ID, dataset=ds),
            [t for t in WEB_TABLES if t in existing],
        ),
    ]

    for aid, dname, desc, instr, tbls in specs:
        res = upsert_agent(sess, PROJECT_ID, aid, dname, desc, instr, tbls, ds)
        print(f"  [OK] {res}")


if __name__ == "__main__":
    main()
