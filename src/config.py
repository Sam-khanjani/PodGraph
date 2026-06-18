from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):

    #neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "testpasssword123"

    #kafka
    kafka_bootstrap_servers: str = "kafka:9092"

    #API 
    api_host: str = "0.0.0.0"
    api_port: int = 8000


    # Groq 
    groq_api_key: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()