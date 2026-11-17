.PHONY: all format lint type test tests integration_test integration_tests check_imports build help

all: help

.EXPORT_ALL_VARIABLES:
UV_FROZEN = true

TEST_FILE ?= tests/unit_tests/
PYTEST_EXTRA ?=

integration_test integration_tests: TEST_FILE = tests/integration_tests/

# Unit tests never touch the network: pytest-socket allows Unix sockets only.
test tests:
	uv run --group test pytest $(PYTEST_EXTRA) --disable-socket --allow-unix-socket $(TEST_FILE)

# The real engine: offline with a Vericto CLI on PATH or in VERICTO_CLI, online
# with VERICTO_API_KEY and VERICTO_DATABASE_ID (each skipped otherwise).
integration_test integration_tests:
	uv run --group test --group test_integration pytest -v --tb=short $(PYTEST_EXTRA) $(TEST_FILE)

lint:
	./scripts/lint_imports.sh
	uv run --group lint ruff check .
	uv run --group lint ruff format --check .
	uv run --group typing mypy

type:
	uv run --group typing mypy

format:
	uv run --group lint ruff format .
	uv run --group lint ruff check --fix .

check_imports: $(shell find llama_index -name '*.py')
	uv run python ./scripts/check_imports.py $^

build:
	rm -rf dist
	uv build
	uvx --from 'twine>=7.0,<8' twine check --strict dist/*

help:
	@echo 'format             - run code formatters'
	@echo 'lint               - lint, format check, type check'
	@echo 'type               - type check'
	@echo 'test               - unit tests (no network)'
	@echo 'integration_test   - integration tests against the real Vericto engine'
	@echo 'check_imports      - import every module'
	@echo 'build              - sdist and wheel, then twine check'
