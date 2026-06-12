.PHONY: help install sync seed api eval eval-baseline eval-hybrid eval-rerank eval-hyde eval-crag eval-all test lint format

help:
	@echo "Enterprise RAG — Available commands"
	@echo ""
	@echo "  make install       — create venv & install all deps (one-time)"
	@echo "  make sync          — sync deps with pyproject.toml"
	@echo "  make seed          — run DB migrations + seed demo data"
	@echo "  make api           — start FastAPI backend (:8000)"
	@echo "  make eval          — run baseline (naive) + full (all) profiles"
	@echo "  make eval-baseline — run naive profile only"
	@echo "  make eval-hybrid   — run hybrid profile only"
	@echo "  make eval-rerank   — run hybrid+rerank profile only"
	@echo "  make eval-hyde     — run hybrid+rerank+hyde profile (hyde goldens only)"
	@echo "  make eval-crag     — run hybrid+rerank+crag profile (crag goldens only)"
	@echo "  make eval-all      — run all-features profile"
	@echo "  make test          — run pytest"
	@echo "  make lint          — run ruff check"
	@echo "  make format        — run ruff format"


# ── Local dev ────────────────────────────────────────────────────────────────

install:
	uv python pin 3.12
	uv venv --python 3.12
	uv sync

sync:
	uv sync

# ── Data & DB ────────────────────────────────────────────────────────────────

seed:
	PYTHONPATH=. uv run python scripts/seed_db.py

# ── App ──────────────────────────────────────────────────────────────────────

api:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# ── Evaluation ───────────────────────────────────────────────────────────────

eval-baseline:
	uv run python -m eval.run_RAGAS --profile naive

eval-hybrid:
	uv run python -m eval.run_RAGAS --profile hybrid

eval-rerank:
	uv run python -m eval.run_RAGAS --profile hybrid+rerank

eval-hyde:
	uv run python -m eval.run_RAGAS --profile hybrid+rerank+hyde --filter hyde

eval-crag:
	uv run python -m eval.run_RAGAS --profile hybrid+rerank+crag --filter crag

eval-all:
	uv run python -m eval.run_RAGAS --profile all

eval: eval-baseline eval-all

# ── Quality ──────────────────────────────────────────────────────────────────

test:
	uv run pytest -v

lint:
	uv run ruff check .

format:
	uv run ruff format .
