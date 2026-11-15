.PHONY: install run test lint cov seed docker css css-watch

install: ## Install runtime and dev dependencies (Python and the CSS toolchain)
	uv sync --group dev
	npm ci

css: ## Build static/dist/app.css from static/src (Tailwind CLI)
	npm run build

css-watch: ## Rebuild the CSS on every template or stylesheet change
	npm run watch

run: css ## Build the CSS and start the Flask app
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
