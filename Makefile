.PHONY: install backend frontend test build serve

ENV_FILE := $(if $(wildcard .env),--env-file ../.env)

install:
	cd backend && uv sync
	cd frontend && npm ci

backend:
	cd backend && uv run uvicorn main:create_app --factory --reload --port 8000 $(ENV_FILE)

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

serve: build
	cd backend && uv run uvicorn main:create_app --factory --port 8000 $(ENV_FILE)
