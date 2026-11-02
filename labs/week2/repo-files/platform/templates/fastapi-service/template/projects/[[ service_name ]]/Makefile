# projects/<service>/Makefile — the CI contract: the reusable workflow only ever runs `make ci`.
# Recipe lines start with ">" instead of a TAB (copy-paste from a PDF turns TABs into spaces).
.RECIPEPREFIX = >
.PHONY: install lint fmt typecheck test ci run

install:
> uv sync --frozen

lint:
> uv run ruff check .
> uv run ruff format --check .

fmt:
> uv run ruff format .
> uv run ruff check --fix .

typecheck:
> uv run mypy

test:
> uv run pytest

ci: install lint typecheck test

run:
> APP_ENVIRONMENT=local uv run uvicorn app.main:app --reload --port 8000
