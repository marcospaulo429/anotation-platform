.PHONY: install install-engine install-api test lint format check

# Core + dev tooling (contracts, tests). Fast: no torch/ultralytics.
install:
	uv sync --extra dev

# Engine adds fly-det (editable) + ultralytics/torch — heavy, CPU wheels here.
install-engine:
	uv sync --extra engine --extra dev

install-api:
	uv sync --extra api --extra dev

# PYTEST_DISABLE_PLUGIN_AUTOLOAD=1: global ROS pytest plugin lacks lark (repo rule).
test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

check: lint test
