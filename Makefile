.PHONY: help warehouse seed provision diagrams benchmark calibrate references answer-check portal local-portal deploy teardown

PYTHON ?= python3

help:
	@echo "Google ADK + BigQuery CAA Reference Architecture & Benchmark Suite"
	@echo "  make warehouse    - Provision 32-table cymbal_enterprise_dw + monolithic As-Is data agent"
	@echo "  make seed         - Refresh relative-timestamp demo seed data in BigQuery"
	@echo "  make provision    - Provision/update the 6 domain-scoped BigQuery CAA data agents"
	@echo "  make benchmark    - Execute live S1-S5 Dual A/B GCP benchmark -> benchmarks/scenario_benchmark_results.json"
	@echo "  make calibrate    - Measure BQCA Cloud Trace medians -> benchmarks/bqca_trace_token_calibration.json"
	@echo "  make references   - Build preset reference SQL snapshot -> benchmarks/reference_answers.json"
	@echo "  make answer-check - Spot-check preset answers against reference SQL (set BASE_URL) -> benchmarks/answer_check_results.json"
	@echo "  make diagrams     - Render all 5 SVG & 3x PNG architecture diagrams -> docs/diagrams/"
	@echo "  make portal       - Compile EN (docs/index.html) & KO (docs/index_ko.html) verification portals"
	@echo "  make local-portal - Serve Interactive Portal + SSE Workbench locally on http://127.0.0.1:8080"
	@echo "  make deploy       - Build & deploy Interactive Portal + Live Workbench API to Cloud Run"
	@echo "  make teardown     - Delete Cloud Run service cleanly"

warehouse:
	$(PYTHON) scripts/provision_enterprise_warehouse.py

seed:
	$(PYTHON) scripts/refresh_demo_seed.py

provision:
	$(PYTHON) scripts/provision_cymbal_caa_agents.py

benchmark:
	$(PYTHON) scripts/04_run_scenario_benchmarks.py

calibrate:
	$(PYTHON) scripts/05_measure_bqca_tokens_from_trace.py

references:
	$(PYTHON) scripts/06_build_reference_answers.py

answer-check:
	$(PYTHON) scripts/07_answer_check.py --base-url $(BASE_URL)

diagrams:
	$(PYTHON) scripts/generate_architecture_diagrams.py

portal:
	$(PYTHON) scripts/build_outcome_portal.py

local-portal:
	uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload

deploy:
	./scripts/deploy.sh

teardown:
	./scripts/teardown.sh
