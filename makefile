.PHONY: help install sync up down restart build rebuild logs ps seed health test lint format

help:
	@echo "Enterprise RAG - Available commands"
	@echo ""
	@echo "  make install    - Create venv and install dependencies (one-time setup)"
	@echo "  make sync       - Sync dependencies with pyproject.toml"
	@echo "  make up         - Start all Docker services"
	@echo "  make down       - Stop all Docker services"
	@echo "  make restart    - Restart the app container"
	@echo "  make build      - Build Docker images"
	@echo "  make rebuild    - Force rebuild Docker images and start"
	@echo "  make logs       - Tail app container logs"
	@echo "  make ps         - Show container status"
	@echo "  make seed       - Run DB migrations + seed demo data"
	@echo "  make health     - Check /admin/health endpoint"
	@echo "  make test       - Run pytest"
	@echo "  make lint       - Run ruff check"
	@echo "  make format     - Run ruff format"

# ── Local dev ────────────────────────────────────────────────────────────────

install:
	uv venv --python python3.12
	uv sync

sync:
	uv sync

# ── Docker ───────────────────────────────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart app

build:
	docker compose build

rebuild:
	docker compose build --no-cache
	docker compose up -d

logs:
	docker compose logs app -f

ps:
	docker compose ps

seed:
	docker compose --profile seed run --rm db-seed

health:
	curl -s http://localhost:8000/admin/health | python -m json.tool

# ── Quality ──────────────────────────────────────────────────────────────────

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check .

format:
	uv run ruff format .
