.PHONY: install run test lint cov seed docker

install: ## Install runtime and dev dependencies
	uv sync --group dev

run: ## Start the Flask app
	uv run python app.py

test: ## Run the test suite
	uv run pytest

lint: ## Static checks with ruff
	uv run ruff check .

cov: ## Tests with coverage report
	uv run pytest --cov=alexandria --cov-report=term-missing

seed: ## Load demo data (scripts/seed_demo.py)
	uv run python scripts/seed_demo.py

docker: ## Build and start the containers
	docker compose up -d --build
