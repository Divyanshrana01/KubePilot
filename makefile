.PHONY : help install sync seed seed-data api streamlit eval eval-baseline eval-hybrid eval-rerank eval-

help: 
	@echo "ADV RAG - Available commands"
	@echo ""
	@echo "  make install        - create venv and install dependencies(one-time setup)"
	@echo "  make sync           - Sync dependencies with pyproject.toml"
	@echo "  make seed           - Seed the database + ingest docs into qdrant"
	@echo "  make seed-data      - download + generate the 95/5 noise corpus (~130-200 MB)"
	@echo "  make api            - Start the FastAPI backend (:8000)"
	@echo "  make streamlit      - Start the Streamlit UI (:8501)"
	@echo "  make eval           - Run baseline + all + diff"
	@echo "  make test           - Run pytest"
	@echo "  make lint           - Run ruff check"
	@echo "  make format         - Run ruff format"





install:
	uv python pip 3.12
	uv venv --python python3.12
	uv sync --extra dev

sync:
	uv sync --extra dev 


seed:
	uv run python -m adv_rag.seed


eval-baseline:

eval-hybrid:
	uv run python -m eval.run_ragas --profile hybrid

eval-rerank:
	uv run python -m eval.run_ragas --profile hybrid+rerank

eval-hyde:
	uv run python -m eval.run_ragas --profile hybrid+rerank+hyde --filter hyde

eval-crag:
	uv run python -m eval.run_ragas --profile hybrid+rerank+crag --filter crag

eval-all:
	uv run python -m eval.run_ragas --profile all

eval: eval-baseline eval-all 
	$(MAKE) eval-diff

eval-diff:
	@latest_naive=$$(ls -t eval/results/baseline_*.json | head -n 1); \




validate:
	uv run python scripts/validate_goldens.py

test:
	uv run pytest tests/ -v

lint:
	uv ruff check .

format:
	uv run ruff format .


eval-legacy:
	@eco "Use: make eval-baseline"