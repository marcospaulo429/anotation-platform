.PHONY: install install-engine install-api test lint format check

# API + dev tooling; no model dependencies.
install:
	uv sync --locked --extra api --extra dev

# Full local platform, including CPU inference.
install-engine:
	uv sync --locked --extra api --extra engine --extra dev

install-api:
	uv sync --locked --extra api --extra dev

# PYTEST_DISABLE_PLUGIN_AUTOLOAD=1: global ROS pytest plugin lacks lark (repo rule).
test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --no-sync pytest

lint:
	uv run --no-sync ruff check src tests
	uv run --no-sync ruff format --check src tests

format:
	uv run --no-sync ruff check --fix src tests
	uv run --no-sync ruff format src tests

check: lint test
