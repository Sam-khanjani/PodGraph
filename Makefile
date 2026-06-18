.PHONY: help up down logs test lint format clean install

help:
	@echo "Available commands:"
	@echo "  make install   - Install dependencies"
	@echo "  make up        - Start all services"
	@echo "  make down      - Stop all services"
	@echo "  make logs      - View logs (all services)"
	@echo "  make logs-api  - View API logs"
	@echo "  make logs-neo4j - View Neo4j logs"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run linting"
	@echo "  make format    - Format code with black"
	@echo "  make clean     - Clean up containers and volumes"
	@echo "  make init-db    - Apply Neo4j schema"
	@echo "  make seed       - Load sample data"
	@echo "  make setup-data - init-db + seed in one shot"

install:
	poetry install

up:
	docker compose up -d
	@echo "Services starting... check with 'docker compose ps'"

down:
	docker compose down

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

logs-neo4j:
	docker compose logs -f neo4j

test:
	python -m pytest src/tests -v --cov=src

lint:
	black --check src/
	flake8 src/

format:
	black src/

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

init-db:
	poetry run python -m src.setup.init_neo4j

seed:
	poetry run python -m src.setup.sample_data

setup-data: init-db seed
	@echo "Schema applied and sample data loaded.