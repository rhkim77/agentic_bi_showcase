"""Reference queries for the preset questions of the workbench.

Each entry is one hand-written reading of a preset question, built from the KPI definitions in the
data agents' glossary (`scripts/provision_cymbal_caa_agents.py`). The workbench runs the matching
entry next to a live run and shows the rows beside the two answers. Nothing is graded automatically:
a question can have more than one defensible reading, and each entry states the reading it uses.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import re
import time
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "ryan-sandbox-agent")
DATASET_ID = os.environ.get("CYMBAL_DATASET_ID", "cymbal_enterprise_dw")
MAX_ROWS = 20

_VIP = """vip AS (
  SELECT user_id
  FROM `{T}.order_items`
  GROUP BY user_id
  HAVING SUM(sale_price) >= 500 OR COUNT(DISTINCT order_id) >= 5
)"""

_VIP_BY_SOURCE = _VIP + """,
vip_30d AS (
  SELECT u.traffic_source,
         COUNT(DISTINCT oi.user_id) AS vip_customer_count,
         ROUND(SUM(oi.sale_price), 2) AS total_gross_revenue,
         ROUND(SAFE_DIVIDE(SUM(oi.sale_price), COUNT(DISTINCT oi.order_id)), 2) AS average_order_value
  FROM `{T}.order_items` AS oi
  JOIN vip USING (user_id)
  JOIN `{T}.users` AS u ON u.id = oi.user_id
  WHERE oi.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  GROUP BY u.traffic_source
)"""

_SQL_VIP_BY_SOURCE = "WITH " + _VIP_BY_SOURCE + """
SELECT * FROM vip_30d ORDER BY total_gross_revenue DESC"""

_SQL_VIP_PLUS_CART = "WITH " + _VIP_BY_SOURCE + """,
sessions AS (
  SELECT session_id, traffic_source,
         MAX(IF(event_type = 'cart', 1, 0)) AS has_cart,
         MAX(IF(event_type = 'purchase', 1, 0)) AS has_purchase
  FROM `{T}.events`
  WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
  GROUP BY session_id, traffic_source
),
cart_14d AS (
  SELECT traffic_source,
         COUNT(DISTINCT IF(has_cart = 1, session_id, NULL)) AS cart_sessions_14d,
         ROUND(SAFE_DIVIDE(COUNT(DISTINCT IF(has_cart = 1 AND has_purchase = 0, session_id, NULL)) * 100.0,
                           COUNT(DISTINCT IF(has_cart = 1, session_id, NULL))), 2) AS cart_abandonment_rate_pct
  FROM sessions
  GROUP BY traffic_source
)
SELECT v.traffic_source, v.vip_customer_count, v.total_gross_revenue, v.average_order_value,
       c.cart_sessions_14d, c.cart_abandonment_rate_pct
FROM vip_30d AS v
LEFT JOIN cart_14d AS c USING (traffic_source)
ORDER BY v.total_gross_revenue DESC"""

_SQL_DC_ALL = """WITH lead AS (
  SELECT p.distribution_center_id AS dc_id,
         ROUND(AVG(TIMESTAMP_DIFF(oi.delivered_at, oi.shipped_at, DAY)), 2) AS avg_delivery_lead_time_days,
         COUNT(*) AS delivered_items
  FROM `{T}.order_items` AS oi
  JOIN `{T}.products` AS p ON p.id = oi.product_id
  WHERE oi.shipped_at IS NOT NULL AND oi.delivered_at IS NOT NULL
  GROUP BY dc_id
),
unsold AS (
  SELECT product_distribution_center_id AS dc_id,
         ROUND(SUM(IF(sold_at IS NULL, cost, 0)), 2) AS unsold_inventory_holding_cost
  FROM `{T}.inventory_items`
  GROUP BY dc_id
)
SELECT dc.name AS distribution_center, l.avg_delivery_lead_time_days, l.delivered_items,
       u.unsold_inventory_holding_cost
FROM `{T}.distribution_centers` AS dc
LEFT JOIN lead AS l ON l.dc_id = dc.id
LEFT JOIN unsold AS u ON u.dc_id = dc.id
ORDER BY dc.id"""

_SQL_DC_OUTERWEAR_SEED = """WITH lead AS (
  SELECT p.distribution_center_id AS dc_id,
         ROUND(AVG(TIMESTAMP_DIFF(oi.delivered_at, oi.shipped_at, DAY)), 2) AS avg_delivery_lead_time_days,
         COUNT(*) AS delivered_items
  FROM `{T}.order_items` AS oi
  JOIN `{T}.products` AS p ON p.id = oi.product_id
  WHERE oi.order_id >= 9900000
    AND p.department = 'Women' AND p.category = 'Outerwear & Coats'
    AND oi.shipped_at IS NOT NULL AND oi.delivered_at IS NOT NULL
  GROUP BY dc_id
),
unsold AS (
  SELECT product_distribution_center_id AS dc_id,
         ROUND(SUM(IF(sold_at IS NULL, cost, 0)), 2) AS unsold_cost_all_womens_outerwear,
         ROUND(SUM(IF(sold_at IS NULL AND id >= 9900000, cost, 0)), 2) AS unsold_cost_seed_rows_only
  FROM `{T}.inventory_items`
  WHERE product_department = 'Women' AND product_category = 'Outerwear & Coats'
  GROUP BY dc_id
)
SELECT dc.name AS distribution_center, l.avg_delivery_lead_time_days, l.delivered_items,
       u.unsold_cost_all_womens_outerwear, u.unsold_cost_seed_rows_only
FROM `{T}.distribution_centers` AS dc
JOIN lead AS l ON l.dc_id = dc.id
LEFT JOIN unsold AS u ON u.dc_id = dc.id
ORDER BY dc.id"""

_SQL_DORMANT = """SELECT u.traffic_source, COUNT(*) AS dormant_customer_count
FROM `{T}.users` AS u
WHERE NOT EXISTS (
  SELECT 1 FROM `{T}.orders` AS o
  WHERE o.user_id = u.id
    AND o.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
)
GROUP BY u.traffic_source
ORDER BY dormant_customer_count DESC"""

_SQL_FAN_VIP = "WITH " + _VIP + """
SELECT COUNT(DISTINCT oi.order_id) AS vip_order_count,
       COUNT(DISTINCT oi.user_id) AS vip_customer_count,
       ROUND(SUM(oi.sale_price), 2) AS gross_demand
FROM `{T}.order_items` AS oi
JOIN vip USING (user_id)
WHERE oi.order_id >= 9900000
  AND oi.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)"""

_SQL_FAN_BRAND = """SELECT p.brand,
       ROUND(AVG(SAFE_DIVIDE(p.retail_price - p.cost, p.retail_price) * 100), 2) AS unit_gross_margin_pct,
       ROUND(COUNTIF(oi.status IN ('Returned', 'Cancelled')) * 100.0 / NULLIF(COUNT(*), 0), 2) AS return_and_cancellation_rate_pct,
       ROUND(SUM(IF(oi.status NOT IN ('Returned', 'Cancelled'), oi.sale_price - p.cost, 0)), 2) AS realized_gross_profit,
       COUNT(*) AS order_items
FROM `{T}.order_items` AS oi
JOIN `{T}.products` AS p ON p.id = oi.product_id
WHERE oi.order_id >= 9900000
  AND p.department = 'Women' AND p.category = 'Outerwear & Coats'
GROUP BY p.brand
ORDER BY p.brand"""

_NOTE_VIP = {
    "en": "Reading used: a VIP is a customer whose lifetime spend is at least $500 or who has at least 5 orders (glossary definition). Count, revenue and AOV cover those customers' order items created in the last 30 days, grouped by the customer's traffic source.",
    "ko": "적용한 해석: VIP는 누적 구매액이 $500 이상이거나 주문이 5건 이상인 고객입니다(Glossary 정의). 고객 수, 매출, AOV는 이 고객들의 최근 30일 Order Item을 고객의 Traffic Source별로 집계했습니다.",
}

REFERENCES: list[dict[str, Any]] = [
    {
        "id": "vip_revenue_aov_by_source_30d",
        "questions": [
            "Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days.",
        ],
        "note": _NOTE_VIP,
        "queries": [{"label": {"en": "VIP customers by traffic source, last 30 days", "ko": "Traffic Source별 VIP 고객, 최근 30일"}, "sql": _SQL_VIP_BY_SOURCE}],
    },
    {
        "id": "vip_plus_cart_abandonment_14d",
        "questions": [
            "Keep those exact columns from the previous result and join our 14-day cart session count and cart abandonment rate (%) for each traffic_source.",
        ],
        "note": {
            "en": "Assumes the previous turn was the default S1 question. Reading used: the three S1 columns, plus sessions of the last 14 days that have a cart event, and the share of those with no purchase event (glossary formula). Cart figures use the traffic source recorded on the events, joined to the customer traffic source by name.",
            "ko": "직전 Turn이 S1 기본 질문이었다고 가정합니다. 적용한 해석: S1의 세 Column에, 최근 14일 동안 cart Event가 있는 Session 수와 그중 purchase Event가 없는 비율(Glossary 계산식)을 더했습니다. Cart 수치는 Event에 기록된 Traffic Source 기준이며, 고객의 Traffic Source와 이름으로 Join했습니다.",
        },
        "queries": [{"label": {"en": "VIP columns plus 14-day cart sessions and abandonment", "ko": "VIP Column + 14일 Cart Session 및 이탈률"}, "sql": _SQL_VIP_PLUS_CART}],
    },
    {
        "id": "dc_lead_time_unsold_all",
        "questions": [
            "Now pivot to Supply Chain: compare average delivery lead time in days and unsold inventory holding cost ($) across all distribution centers.",
        ],
        "note": {
            "en": "Reading used: no date or product filter. Lead time is the average whole days from shipped to delivered over all delivered order items, by the distribution center of the product. Holding cost is the summed cost of inventory rows that have no sold date.",
            "ko": "적용한 해석: 기간과 상품 조건 없이 전체 데이터를 대상으로 했습니다. Lead Time은 배송 완료된 모든 Order Item의 출고~배송 일수 평균이며 상품의 Distribution Center 기준입니다. Holding Cost는 판매일이 없는 Inventory 행의 원가 합계입니다.",
        },
        "queries": [{"label": {"en": "Lead time and unsold inventory cost by distribution center", "ko": "Distribution Center별 Lead Time 및 미판매 재고 원가"}, "sql": _SQL_DC_ALL}],
    },
    {
        "id": "dc_lead_time_unsold_outerwear_seed",
        "questions": [
            "Compare average delivery lead time in days and unsold inventory holding cost ($) by distribution center for Women's Outerwear (order_id >= 9900000).",
        ],
        "note": {
            "en": "Reading used: lead time over order items with order_id >= 9900000 for Women / Outerwear & Coats products. The question does not say whether the order_id filter also limits inventory, so holding cost is shown both ways: all Women's Outerwear inventory, and seeded inventory rows only.",
            "ko": "적용한 해석: Lead Time은 order_id >= 9900000이면서 Women / Outerwear & Coats 상품인 Order Item 기준입니다. order_id 조건이 Inventory에도 적용되는지 질문에 명시되지 않아 Holding Cost는 두 가지로 표시합니다: Women's Outerwear 전체 Inventory, 그리고 Seed 행만.",
        },
        "queries": [{"label": {"en": "Women's Outerwear: lead time and unsold cost by distribution center", "ko": "Women's Outerwear: Distribution Center별 Lead Time 및 미판매 원가"}, "sql": _SQL_DC_OUTERWEAR_SEED}],
    },
    {
        "id": "dormant_customers_by_source_90d",
        "questions": [
            "Count dormant customers with zero orders in the last 90 days by traffic source.",
        ],
        "note": {
            "en": "Reading used: every registered user with no order created in the last 90 days (glossary definition), including users who never ordered, grouped by the user's traffic source.",
            "ko": "적용한 해석: 최근 90일 동안 생성된 주문이 없는 모든 등록 사용자(Glossary 정의)이며 주문 이력이 전혀 없는 사용자도 포함합니다. 사용자의 Traffic Source별로 집계했습니다.",
        },
        "queries": [{"label": {"en": "Dormant customers by traffic source", "ko": "Traffic Source별 휴면 고객"}, "sql": _SQL_DORMANT}],
    },
    {
        "id": "outerwear_profit_three_domains",
        "questions": [
            "Why is Women's Outerwear & Coats realized profit dropping despite strong VIP sales? Run a parallel cross-domain analysis across: (1) last 30-day VIP orders and gross demand where order_id >= 9900000, (2) Women's 'Outerwear & Coats' unit margin %, return rate %, and realized profit by brand (order_id >= 9900000), and (3) recent Women's Outerwear average delivery lead time in days and unsold holding cost by distribution center (order_id >= 9900000).",
            "Why is Women's Outerwear & Coats realized profit dropping despite strong VIP sales? Run a parallel cross-domain analysis across: (1) last 30-day VIP orders & gross demand where order_id >= 9900000, (2) Women's 'Outerwear & Coats' unit margin %, return rate %, and realized profit by brand (order_id >= 9900000), and (3) recent Women's Outerwear average delivery lead time in days and unsold holding cost by distribution center (order_id >= 9900000).",
        ],
        "note": {
            "en": "Three queries, one per part of the question, each using the glossary formulas on rows with order_id >= 9900000. These give the figures only; the explanation of why profit is dropping is the agents' own synthesis and has no reference here.",
            "ko": "질문의 세 부분에 각각 대응하는 Query 3개이며, 모두 order_id >= 9900000 행에 Glossary 계산식을 적용했습니다. 여기서는 수치만 제공합니다. 이익이 왜 줄었는지에 대한 설명은 Agent가 직접 종합한 내용이라 기준 값이 없습니다.",
        },
        "queries": [
            {"label": {"en": "(1) VIP orders and gross demand, last 30 days", "ko": "(1) VIP 주문 및 Gross Demand, 최근 30일"}, "sql": _SQL_FAN_VIP},
            {"label": {"en": "(2) Margin, return rate and realized profit by brand", "ko": "(2) Brand별 Margin, 반품률, 실현 이익"}, "sql": _SQL_FAN_BRAND},
            {"label": {"en": "(3) Lead time and unsold cost by distribution center", "ko": "(3) Distribution Center별 Lead Time 및 미판매 원가"}, "sql": _SQL_DC_OUTERWEAR_SEED},
        ],
    },
]


def normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


_INDEX = {normalize_question(q): ref for ref in REFERENCES for q in ref["questions"]}


def find_reference(prompt: str) -> dict[str, Any] | None:
    """Returns the reference entry whose preset question equals `prompt` (case and spacing ignored)."""
    return _INDEX.get(normalize_question(prompt))


def _run_query(sess: AuthorizedSession, sql: str) -> dict[str, Any]:
    base = f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT_ID}/queries"
    resp = sess.post(base, json={"query": sql, "useLegacySql": False, "timeoutMs": 30000, "maxResults": MAX_ROWS}, timeout=60)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "BigQuery error"))
    job = data["jobReference"]
    deadline = time.monotonic() + 60
    while not data.get("jobComplete"):
        if time.monotonic() > deadline:
            raise TimeoutError("reference query did not finish in 60s")
        time.sleep(1)
        data = sess.get(f"{base}/{job['jobId']}", params={"location": job.get("location", "US"), "maxResults": MAX_ROWS}, timeout=60).json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", "BigQuery error"))
    columns = [f["name"] for f in data.get("schema", {}).get("fields", [])]
    rows = [[cell.get("v") for cell in row["f"]] for row in data.get("rows", [])[:MAX_ROWS]]
    return {"columns": columns, "rows": rows, "total_rows": int(data.get("totalRows", len(rows)))}


def run_reference(ref: dict[str, Any]) -> dict[str, Any]:
    """Runs the queries of one reference entry on BigQuery now. Blocking; call it from a thread."""
    out: dict[str, Any] = {
        "id": ref["id"],
        "note": ref["note"],
        "executed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": f"{PROJECT_ID}.{DATASET_ID}",
        "queries": [],
    }
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    sess = AuthorizedSession(creds)
    for q in ref["queries"]:
        sql = q["sql"].replace("{T}", f"{PROJECT_ID}.{DATASET_ID}")
        item: dict[str, Any] = {"label": q["label"], "sql": sql}
        try:
            item.update(_run_query(sess, sql))
        except Exception as exc:  # pylint: disable=broad-except
            item["error"] = f"{type(exc).__name__}: {exc}"[:300]
        out["queries"].append(item)
    return out
