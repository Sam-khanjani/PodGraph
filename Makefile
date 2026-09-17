.PHONY: install up down logs test lint format clean init-db reset-db ingest-sample ingest-file ingest-youtube backfill api

install:
	poetry install

up:
	docker compose up -d neo4j

down:
	docker compose down

logs:
	docker compose logs -f

api:            ## run the API locally with reload (port 8010; 8000 is often taken)
	poetry run uvicorn src.query.api:app --reload --port 8010

test:
	poetry run pytest src/tests -q --cov=src

lint:
	poetry run flake8 src/

format:
	poetry run black src/

clean:
	docker compose down -v

init-db:
	poetry run python -m src.setup.init_neo4j

ingest-sample:  ## the real episodes saved in data/transcripts (needs OPENROUTER_API_KEY; add --no-llm to skip)
	poetry run python -m src.ingestion.pipeline file data/transcripts/*.json

ingest-youtube: ## make ingest-youtube ID=VIDEO_ID PODCAST="Show name"
	poetry run python -m src.ingestion.pipeline youtube $(ID) --podcast "$(PODCAST)"

reset-db:       ## wipe every node, keep the schema
	poetry run python -c "from src.query.db import run, close; run('MATCH (n) DETACH DELETE n'); close()"

ingest-file:    ## make ingest-file FILE=path/to/transcript.json
	poetry run python -m src.ingestion.pipeline file $(FILE)

backfill:       ## embed chunks that predate embeddings
	poetry run python -m src.ingestion.pipeline backfill
