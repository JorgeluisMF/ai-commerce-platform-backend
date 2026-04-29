# AI Commerce Platform — Backend API

FastAPI backend with PostgreSQL, SQLAlchemy, Alembic, Redis, and RQ workers.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL
- Redis

## Setup

From this folder (`backend/`):

1. Create and sync the environment:
   - `uv venv`
   - `uv sync --extra dev`
2. Copy environment variables and fill required values:
   - `copy .env.example .env`

At minimum, configure:
- `JWT_SECRET_KEY`
- database settings
- Redis settings
- embeddings/LLM provider settings if RAG is enabled

## Infrastructure

If you use Docker for local services, run Postgres and Redis first:

- `docker compose up -d`

Or use your own managed/local instances and point `.env` to them.

## Database Migrations

- `uv run alembic upgrade head`

## Run the API

- `uv run uvicorn app.main:app --reload --app-dir src`

## Background Workers (RQ)

With Redis running, start the worker for `emails`, `embeddings`, and `post_checkout` queues:

- `uv run python scripts/rq_worker.py`

## Tests

- `uv run pytest`

## Project Structure

- `src/app/api/` — API routes (v1 endpoints)
- `src/app/services/` — business logic
- `src/app/repositories/` — data access layer
- `src/app/models/` — SQLAlchemy models
- `src/app/schemas/` — request/response models

## Features

- Auth (JWT access + refresh flow)
- Product catalog and search
- Cart and checkout
- Wishlist
- Orders
- Reviews
- Admin dashboard endpoints
- Semantic search + RAG support

For semantic search and RAG:
- set `EMBEDDINGS_ENABLED=true`
- provide the required provider keys in `.env`
