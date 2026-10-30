.PHONY: install backend frontend test build serve prototype

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

# Prototype Testing page assets (local only, git-ignored): needs the POC clip at
# ../poc-luxury-empty-apartment.mp4 and its broker-approved listing in the local DB.
prototype:
	cd backend && uv run $(ENV_FILE) --with "numpy>=2.3,<3" --with "meta-sam-parser==0.1.0" python -m prototype.assets
