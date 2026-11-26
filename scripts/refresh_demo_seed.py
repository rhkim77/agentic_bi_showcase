#!/usr/bin/env python3
"""Refreshes relative timestamp demo seed records (`ID >= 9900000`) in BigQuery
so 14-day and 30-day Executive BI queries always return deterministic live data."""

from __future__ import annotations

import os
from pathlib import Path
import time
import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "ryan-sandbox-agent") or "ryan-sandbox-agent"
DATASET_ID = os.environ.get("BQ_DATASET_ID", "cymbal_enterprise_dw") or "cymbal_enterprise_dw"
SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "seed_cymbal_scenarios.sql"


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8").replace("__PROJECT_ID__", PROJECT_ID).replace("__DATASET_ID__", DATASET_ID)
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(PROJECT_ID)
    sess = AuthorizedSession(creds)
    resp = sess.post(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT_ID}/queries",
        json={"query": sql, "useLegacySql": False, "timeoutMs": 60000},
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    job_id = data["jobReference"]["jobId"]
    loc = data["jobReference"].get("location", "US")
    while not data.get("jobComplete"):
        time.sleep(2)
        data = sess.get(f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT_ID}/queries/{job_id}?location={loc}").json()
    print(f"[OK] Refreshed relative demo seed data in {PROJECT_ID}.{DATASET_ID} (Job: {job_id})")


if __name__ == "__main__":
    main()
