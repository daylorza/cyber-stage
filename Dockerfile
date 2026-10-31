# Cyber Stage — single-container deploy for Fly.io
# Frontend (Vite) + FastAPI backend served together from :8000.
# Backend mounts frontend/dist when index.html exists (backend/main.py),
# and data (SQLite + media) lives in VRE_DATA_DIR, set to /data in fly.toml
# so it survives deploys on a Fly volume. Do NOT commit a real .env.

# Stage 1: build the frontend
FROM node:22 AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: backend
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
WORKDIR /app/backend
# uv is the project's package manager (see Makefile: uv sync)
RUN pip install --no-cache-dir uv \
    && uv sync
ENV VRE_DATA_DIR=/data
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
