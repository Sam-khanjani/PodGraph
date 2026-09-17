from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""  # empty = no auth (matches NEO4J_AUTH=none in docker-compose)

    kafka_bootstrap_servers: str = "kafka:9092"  # deferred; see docs/ARCHITECTURE.md

    openrouter_api_key: str = ""
    llm_model: str = "nex-agi/nex-n2.5-pro:free"  # any OpenRouter id; free tier by default (paid: openai/gpt-4o-mini)
    llm_parallel: int = 2  # concurrent LLM calls during ingestion; free tier is rate-limited (~20 req/min)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
