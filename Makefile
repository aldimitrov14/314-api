.PHONY: install dev test lint typecheck run

install:
	uv pip install -r requirements-dev.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

lint:
	ruff check .

typecheck:
	mypy app
