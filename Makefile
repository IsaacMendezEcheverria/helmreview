PYTHON ?= python3
VENV   ?= .venv
BIN     = $(VENV)/bin

.PHONY: help dev test lint format build clean

help:  ## Muestra esta ayuda
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

dev:  ## Crea el venv con dependencias de desarrollo e instala pre-commit
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e ".[dev]"
	$(BIN)/pre-commit install

test:  ## Corre los tests con cobertura
	$(BIN)/pytest --cov --cov-report=term-missing

lint:  ## Lint y verificación de formato
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

format:  ## Aplica formato y correcciones automáticas
	$(BIN)/ruff check --fix src tests
	$(BIN)/ruff format src tests

build: clean  ## Construye wheel y sdist en dist/
	$(BIN)/python -m build

clean:  ## Borra artefactos de build y caches
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .ruff_cache .coverage coverage.xml htmlcov
