#!/usr/bin/env python3
"""Grants the Cloud Run service account access to this demo's own resources only.

  * `roles/geminidataanalytics.dataAgentUser` on each data agent of this demo (the monolithic one and the six domain ones)
    (set on the data agent, not on the project).
  * Read access to the demo dataset (BigQuery dataset access entry `READER`, not a project role).

With these in place the service account needs no project-level `bigquery.dataViewer` or
`geminidataanalytics.dataAgentUser`, so the live workbench cannot reach other data agents or datasets
in the same project. Idempotent. Standard library only, so `scripts/deploy.sh` can call it.

Usage:
    python3 scripts/grant_runtime_access.py --service-account <email> [--project <id>] [--dataset <id>]

The access token is read from `GCP_ACCESS_TOKEN`, or taken from `gcloud auth print-access-token`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.request

DATA_AGENT_IDS = [
    os.environ.get("CYMBAL_BASELINE_CA_ID", "cymbal_enterprise_monolithic_ca"),
    os.environ.get("CYMBAL_CUSTOMER_CA_ID", "cymbal_customer_marketing_ca"),
    os.environ.get("CYMBAL_PRODUCT_CA_ID", "cymbal_product_profitability_ca"),
    os.environ.get("CYMBAL_SUPPLY_CA_ID", "cymbal_supply_chain_ca"),
    os.environ.get("CYMBAL_STORE_CA_ID", "cymbal_store_channel_ca"),
    os.environ.get("CYMBAL_CATALOG_CA_ID", "cymbal_catalog_channel_ca"),
    os.environ.get("CYMBAL_WEB_CA_ID", "cymbal_web_channel_ca"),
]
DATA_AGENT_ROLE = "roles/geminidataanalytics.dataAgentUser"


def access_token() -> str:
    token = os.environ.get("GCP_ACCESS_TOKEN", "").strip()
    if token:
        return token
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()


def call(method: str, url: str, token: str, project: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "x-goog-user-project": project},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url}: HTTP {exc.code} {exc.read().decode()[:400]}") from exc


def grant_data_agents(token: str, project: str, member: str) -> None:
    base = f"https://geminidataanalytics.googleapis.com/v1/projects/{project}/locations/global/dataAgents"
    for agent_id in DATA_AGENT_IDS:
        policy = call("POST", f"{base}/{agent_id}:getIamPolicy", token, project, {})
        bindings = policy.setdefault("bindings", [])
        binding = next((b for b in bindings if b.get("role") == DATA_AGENT_ROLE), None)
        if binding and member in binding.get("members", []):
            print(f"  [ok] {agent_id}: already granted")
            continue
        if binding is None:
            bindings.append({"role": DATA_AGENT_ROLE, "members": [member]})
        else:
            binding.setdefault("members", []).append(member)
        call("POST", f"{base}/{agent_id}:setIamPolicy", token, project, {"policy": policy})
        print(f"  [granted] {agent_id}: {DATA_AGENT_ROLE}")


def grant_dataset(token: str, project: str, dataset: str, email: str) -> None:
    url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/datasets/{dataset}"
    access = call("GET", url, token, project).get("access", [])
    if any(a.get("userByEmail") == email and a.get("role") in ("READER", "roles/bigquery.dataViewer") for a in access):
        print(f"  [ok] {project}.{dataset}: already readable")
        return
    call("PATCH", url, token, project, {"access": access + [{"role": "READER", "userByEmail": email}]})
    print(f"  [granted] {project}.{dataset}: READER")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service-account", required=True)
    ap.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    ap.add_argument("--dataset", default=os.environ.get("BQ_DATASET_ID", "cymbal_enterprise_dw"))
    args = ap.parse_args()
    if not args.project:
        raise SystemExit("Set --project or GOOGLE_CLOUD_PROJECT.")
    token = access_token()
    print(f"Granting {args.service_account} access to the demo resources in {args.project}")
    grant_data_agents(token, args.project, f"serviceAccount:{args.service_account}")
    grant_dataset(token, args.project, args.dataset, args.service_account)


if __name__ == "__main__":
    main()
