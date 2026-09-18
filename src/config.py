from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""  # empty = no auth (matches NEO4J_AUTH=none in docker-compose)

    kafka_bootstrap_servers: str = "kafka:9092"  # deferred; see docs/ARCHITECTURE.md

    # Groq free tier: limits are PER MODEL (1000 req/day, 8k tokens/min, 200k tokens/day each) -> tasks spread over three.
    groq_api_key: str = ""
    llm_model_reason: str = "openai/gpt-oss-120b"  # topic boundaries, recommendations, /query router + synthesis
    llm_model_bulk: str = "openai/gpt-oss-20b"     # per-chunk analysis (alternates with the fast model)
    llm_model_fast: str = "qwen/qwen3.8-27b"       # concept-bank confirms, episode metadata
    llm_parallel: int = 3  # concurrent LLM calls during ingestion (~one in flight per model)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
