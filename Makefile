.PHONY: install lint test bootstrap update backtest build serve validate ledger-check all

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check .
	mypy

test:
	pytest

bootstrap:
	APP_MODE=$${APP_MODE:-demo} python -m sol_reality_check bootstrap

update:
	APP_MODE=$${APP_MODE:-demo} python -m sol_reality_check update

backtest:
	APP_MODE=$${APP_MODE:-demo} python -m sol_reality_check backtest

build:
	python scripts/build_site.py

validate:
	python -m sol_reality_check validate

ledger-check:
	python -m sol_reality_check ledger-check

serve:
	python -m http.server --directory site 8000

all: bootstrap backtest build validate ledger-check test

