.PHONY: help seed provision benchmark diagrams local-portal deploy teardown

PYTHON ?= python3

help:
	@echo "Google ADK + BigQuery CAA Reference Architecture & Benchmark Suite"
	@echo "  make seed         - Refresh relative-timestamp demo seed data in BigQuery"
	@echo "  make provision    - Provision/update the 3 Domain-Scoped BigQuery CAA Data Agents"
	@echo "  make diagrams     - Render all 4 official GCP SVG & 3x PNG architecture diagrams"
	@echo "  make benchmark    - Execute live 5-Scenario GCP benchmark suite -> benchmarks/scenario_benchmark_results.json"
	@echo "  make local-portal - Serve Interactive Architecture & Outcome Portal locally on http://127.0.0.1:8080"
	@echo "  make deploy       - Build & deploy Interactive Portal + Live Verification API to Cloud Run"
	@echo "  make teardown     - Delete Cloud Run service cleanly"

seed:
	$(PYTHON) scripts/refresh_demo_seed.py

provision:
	$(PYTHON) scripts/provision_cymbal_caa_agents.py

diagrams:
	$(PYTHON) scripts/generate_architecture_diagrams.py

benchmark:
	$(PYTHON) scripts/04_run_scenario_benchmarks.py

local-portal:
	uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload

deploy:
	./scripts/deploy.sh

teardown:
	./scripts/teardown.sh
