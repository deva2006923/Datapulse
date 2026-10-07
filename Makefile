.PHONY: install run export test smoke tunnel help

PYTHON ?= python

help:
	@echo "DataPulse Backend Commands:"
	@echo "  make install  - Install project dependencies"
	@echo "  make run      - Run development server on http://localhost:8000"
	@echo "  make export   - Export OpenAPI JSON and API Contract documentation"
	@echo "  make test     - Run pytest test suite"
	@echo "  make smoke    - Run end-to-end smoke test"
	@echo "  make tunnel   - Expose local server using Cloudflare Tunnel"

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

export:
	$(PYTHON) -m app.export_openapi

test:
	$(PYTHON) -m pytest tests/ -v

smoke:
	$(PYTHON) scripts/smoke_test.py

tunnel:
	@echo "=================================================================================="
	@echo " [REMINDER] Copy the resulting https://*.trycloudflare.com URL from below"
	@echo " and set it in your Lovable frontend configuration (e.g., API Base URL / VITE_API_URL)."
	@echo " Verify the connection with: curl https://<your-tunnel-url>/health"
	@echo "=================================================================================="
	cloudflared tunnel --url http://localhost:8000
