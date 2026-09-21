# AgentForge Makefile helpers

.PHONY: test lint backend frontend seed compose

test:
	cd backend && .venv/bin/pytest -q

lint:
	cd backend && .venv/bin/ruff check app tests

backend:
	cd backend && APP_ENV=development USE_SQLITE=true LLM_MOCK_MODE=true USE_LOCAL_EMBEDDINGS=false \
	  .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

seed:
	./scripts/seed_demo.sh

compose:
	docker compose up --build
