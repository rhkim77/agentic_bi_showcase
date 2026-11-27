#!/usr/bin/env python3
"""Builds the enterprise-scale demo warehouse and the monolithic As-Is data agent.

Why: on a 7-table schema the BigQuery CAA token footprint is dominated by a fixed per-call overhead,
so scoping a data agent to a few tables changes little. Enterprise warehouses carry dozens of
documented tables. This script reproduces that shape so the effect of schema scoping can be measured:

  1. Creates dataset `{PROJECT}.{DATASET}` (default `cymbal_enterprise_dw`, US).
  2. Copies the 7 thelook tables and the 25 TPC-DS tables from BigQuery public datasets (about 2 GB).
  3. Adds a description to every table and column. The descriptions are generated from naming rules;
     they are synthetic documentation, not text from a real company.
  4. Creates the monolithic data agent `cymbal_enterprise_monolithic_ca` bound to all 32 tables with
     the business glossary of all six domains.

Run `scripts/refresh_demo_seed.py` and `scripts/provision_cymbal_caa_agents.py` afterwards to seed the
scenario rows and to bind the six domain-scoped data agents to the same dataset.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import time

import google.auth
from google.auth.transport.requests import AuthorizedSession

import provision_cymbal_caa_agents as prov

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "ryan-sandbox-agent") or "ryan-sandbox-agent"
DATASET_ID = os.environ.get("BQ_DATASET_ID", "cymbal_enterprise_dw") or "cymbal_enterprise_dw"
MONOLITHIC_CA_ID = os.environ.get("CYMBAL_BASELINE_CA_ID", "cymbal_enterprise_monolithic_ca")
BQ = f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT_ID}"

THELOOK_TABLES = ["users", "events", "orders", "order_items", "products", "inventory_items", "distribution_centers"]

TPCDS_ENTITY = {
    "call_center": ("cc", "call center that takes catalog orders"),
    "catalog_page": ("cp", "page of a printed sales catalog"),
    "catalog_returns": ("cr", "returned line item of a catalog order"),
    "catalog_sales": ("cs", "sold line item of a catalog order"),
    "customer": ("c", "registered customer"),
    "customer_address": ("ca", "customer postal address"),
    "customer_demographics": ("cd", "customer demographic profile"),
    "date_dim": ("d", "calendar date"),
    "household_demographics": ("hd", "household demographic profile"),
    "income_band": ("ib", "household income band"),
    "inventory": ("inv", "weekly on-hand inventory snapshot"),
    "item": ("i", "sellable product item"),
    "promotion": ("p", "marketing promotion"),
    "reason": ("r", "return reason code"),
    "ship_mode": ("sm", "shipping mode and carrier"),
    "store": ("s", "physical retail store"),
    "store_returns": ("sr", "returned line item of a store ticket"),
    "store_sales": ("ss", "sold line item of a store ticket"),
    "time_dim": ("t", "time of day"),
    "warehouse": ("w", "fulfillment warehouse"),
    "web_page": ("wp", "page of the e-commerce web site"),
    "web_returns": ("wr", "returned line item of a web order"),
    "web_sales": ("ws", "sold line item of a web order"),
    "web_site": ("web", "e-commerce web site"),
}
THELOOK_ENTITY = {
    "users": "registered shopper account",
    "events": "web session clickstream event",
    "orders": "customer order header",
    "order_items": "order line item",
    "products": "product catalog entry",
    "inventory_items": "individual inventory unit",
    "distribution_centers": "distribution center",
}
WORDS = {
    "sk": "surrogate key", "id": "business identifier", "qty": "quantity", "amt": "amount", "ext": "extended",
    "inc": "including", "desc": "description", "addr": "address", "cdemo": "customer demographics",
    "hdemo": "household demographics", "gmt": "GMT", "mkt": "market", "rec": "record", "dom": "day of month",
    "dow": "day of week", "moy": "month of year", "qoy": "quarter of year", "fy": "fiscal year", "pct": "percent",
    "num": "number", "sq": "square", "ft": "feet", "cnt": "count", "dep": "dependents", "est": "estimated",
    "lp": "list price", "dmail": "direct mail", "tv": "television", "eq": "equivalent",
}


def get_session() -> AuthorizedSession:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(PROJECT_ID)
    return AuthorizedSession(creds)


def run_query(sql: str) -> None:
    sess = get_session()
    resp = sess.post(f"{BQ}/queries", json={"useLegacySql": False, "query": sql, "timeoutMs": 10000}, timeout=60).json()
    if "error" in resp:
        raise RuntimeError(resp["error"]["message"])
    job = resp["jobReference"]
    while not resp.get("jobComplete"):
        time.sleep(3)
        resp = sess.get(f"{BQ}/queries/{job['jobId']}", params={"location": job.get("location", "US"), "maxResults": 0}, timeout=60).json()
        if "error" in resp:
            raise RuntimeError(resp["error"]["message"])


def humanize(col: str, prefix: str | None) -> str:
    parts = col.split("_")
    if prefix and parts[0] == prefix:
        parts = parts[1:]
    return " ".join(WORDS.get(p, p) for p in parts).strip().capitalize()


def column_description(table: str, col: str, typ: str) -> str:
    if table in TPCDS_ENTITY:
        prefix, entity = TPCDS_ENTITY[table]
    else:
        prefix, entity = None, THELOOK_ENTITY.get(table, table.replace("_", " "))
    text = f"{humanize(col, prefix)} of the {entity}."
    if col.endswith("_date_sk"):
        text += " Surrogate key that joins to date_dim.d_date_sk."
    elif col.endswith("_sk"):
        text += " Surrogate key; join to the matching dimension table on its _sk column."
    elif col.endswith("_id") or col == "id":
        text += " Natural business identifier assigned by the source system."
    elif typ in ("NUMERIC", "FLOAT", "FLOAT64", "BIGNUMERIC") or any(k in col for k in ("price", "cost", "amt", "paid", "profit", "tax")):
        text += " Monetary or numeric measure in USD unless stated otherwise; safe to SUM."
    elif typ in ("TIMESTAMP", "DATE", "DATETIME"):
        text += " Stored in UTC; use for time filters and period comparisons."
    else:
        text += " Descriptive attribute maintained by the nightly warehouse load."
    return text


def glossary_section(instruction: str) -> str:
    """Returns the glossary rules of a domain instruction, without its persona header."""
    marker = "[Enterprise Business Glossary"
    idx = instruction.find(marker)
    return instruction[idx:].strip() if idx >= 0 else instruction.strip()


def main() -> None:
    sess = get_session()
    resp = sess.post(
        f"{BQ}/datasets",
        json={
            "datasetReference": {"projectId": PROJECT_ID, "datasetId": DATASET_ID},
            "location": "US",
            "description": "Cymbal enterprise demo warehouse: thelook (7 tables) + TPC-DS 1G (25 tables) with generated table and column descriptions.",
        },
        timeout=60,
    )
    if resp.status_code not in (200, 409):
        raise RuntimeError(f"Dataset create failed: HTTP {resp.status_code} {resp.text[:300]}")
    print(f"Dataset `{PROJECT_ID}.{DATASET_ID}`: {'created' if resp.status_code == 200 else 'already exists'}")

    listing = sess.get(
        "https://bigquery.googleapis.com/bigquery/v2/projects/bigquery-public-data/datasets/tpc_ds_1g/tables",
        params={"maxResults": 100},
        timeout=60,
    ).json()
    tpcds_tables = sorted(t["tableReference"]["tableId"] for t in listing["tables"])
    existing = {
        t["tableReference"]["tableId"]
        for t in sess.get(f"{BQ}/datasets/{DATASET_ID}/tables", params={"maxResults": 200}, timeout=60).json().get("tables", [])
    }
    copies = [
        (t, f"CREATE TABLE `{PROJECT_ID}.{DATASET_ID}.{t}` AS SELECT * FROM `bigquery-public-data.tpc_ds_1g.{t}`")
        for t in tpcds_tables if t not in existing
    ] + [
        (t, f"CREATE TABLE `{PROJECT_ID}.{DATASET_ID}.{t}` AS SELECT * FROM `bigquery-public-data.thelook_ecommerce.{t}`")
        for t in THELOOK_TABLES if t not in existing
    ]
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda c: run_query(c[1]), copies))
    print(f"Copied {len(copies)} table(s); {len(existing)} already present.")

    all_tables = THELOOK_TABLES + tpcds_tables
    n_cols = n_chars = 0
    for table in all_tables:
        meta = sess.get(f"{BQ}/datasets/{DATASET_ID}/tables/{table}", timeout=60).json()
        fields = meta["schema"]["fields"]
        for f in fields:
            f["description"] = column_description(table, f["name"], f["type"])
            n_cols += 1
            n_chars += len(f["name"]) + len(f["type"]) + len(f["description"])
        entity = TPCDS_ENTITY.get(table, (None, THELOOK_ENTITY.get(table, table)))[1]
        table_desc = f"One row per {entity}. Part of the Cymbal enterprise data warehouse; loaded nightly from the operational source systems."
        sess.patch(f"{BQ}/datasets/{DATASET_ID}/tables/{table}", json={"description": table_desc, "schema": {"fields": fields}}, timeout=60).raise_for_status()
        n_chars += len(table_desc)
    print(f"Described {len(all_tables)} tables and {n_cols} columns ({n_chars:,} schema + description characters).")

    fmt = lambda text: text.format(project=PROJECT_ID, dataset=DATASET_ID)
    instruction = (
        f"You are Cymbal Global Commerce's enterprise-wide BigQuery Conversational Analytics Agent (`{MONOLITHIC_CA_ID}`) "
        f"analyzing the whole warehouse `{PROJECT_ID}.{DATASET_ID}`. Follow the business glossary below when generating SQL "
        "and answer in concise English with exact figures.\n\n"
        + "\n\n".join(glossary_section(fmt(t)) for t in prov.ALL_DOMAIN_INSTRUCTIONS)
    )
    name = prov.upsert_agent(
        sess,
        PROJECT_ID,
        MONOLITHIC_CA_ID,
        "Cymbal Global Commerce — Enterprise Monolithic CAA (As-Is)",
        "As-Is baseline: one data agent bound to all 32 warehouse tables with the glossary of every domain.",
        instruction,
        all_tables,
        DATASET_ID,
    )
    print(f"[OK] {name}: {len(all_tables)} tables, instruction {len(instruction):,} characters")


if __name__ == "__main__":
    main()
