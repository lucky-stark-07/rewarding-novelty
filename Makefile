.PHONY: setup gen-corpus test eval smoke load dev
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	cp -n .env.example .env
	npm --prefix frontend install

gen-corpus:
	.venv/bin/python -m backend.data_gen

test:
	.venv/bin/python -m pytest -q

eval:
	.venv/bin/python -m scripts.evaluate

smoke:
	.venv/bin/python -m scripts.smoke_live

# Requires a running API (make dev). Cached fixtures by default: no model spend after the first pass.
load:
	.venv/bin/python -m scripts.load_test --url http://localhost:$(BACKEND_PORT)

dev:
	FRONTEND_ORIGIN=http://localhost:$(FRONTEND_PORT) .venv/bin/uvicorn backend.main:app --reload --port $(BACKEND_PORT) & backend_pid=$$!; FRONTEND_ORIGIN=http://localhost:$(FRONTEND_PORT) NEXT_PUBLIC_API_URL=http://localhost:$(BACKEND_PORT) npm --prefix frontend run dev -- --port $(FRONTEND_PORT) & frontend_pid=$$!; trap 'kill $$backend_pid $$frontend_pid 2>/dev/null || true' EXIT INT TERM; wait $$frontend_pid
