.PHONY: help install dev fe-dev fe-build lint fmt type test test-int migrate docker docker-multi clean

IMAGE ?= techblog/mailsieve
TAG   ?= $(shell python -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'

install:  ## Install python deps with all backends + dev tools
	pip install -e ".[all,dev]"

dev:  ## Run the API with reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

fe-dev:  ## Run the vite dev server
	cd frontend && npm run dev

fe-build:  ## Build the SPA into app/static
	cd frontend && npm ci && npm run build

lint:  ## Ruff check
	ruff check app tests

fmt:  ## Ruff format + fix
	ruff format app tests && ruff check --fix app tests

type:  ## Mypy
	mypy app

test:  ## Unit tests
	pytest -m "not integration"

test-int:  ## Integration tests (needs live backends)
	pytest -m integration

migrate:  ## Apply migrations
	alembic upgrade head

docker:  ## Build image for the local arch
	docker build -t $(IMAGE):$(TAG) -t $(IMAGE):latest .

docker-multi:  ## Build and push amd64 + arm64
	docker buildx build --platform linux/amd64,linux/arm64 \
		-t $(IMAGE):$(TAG) -t $(IMAGE):latest --push .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
