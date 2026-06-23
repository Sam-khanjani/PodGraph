from neo4j import GraphDatabase, Driver
from src.config import settings
from typing import Optional
from neo4j import AsyncGraphDatabase, AsyncDriver   

class Neo4jConnection:
    """Manages Neo4j database connections"""
    
    _instance: Optional[Driver] = None
    
    @classmethod
    def get_driver(cls) -> Driver:
        """Get or create Neo4j driver instance"""
        if cls._instance is None:
            auth = None if not settings.neo4j_password else (settings.neo4j_username, settings.neo4j_password)
            cls._instance = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=auth,
            )
        return cls._instance
    
    @classmethod
    def close(cls):
        """Close the Neo4j driver"""
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None
    
    @classmethod
    def verify_connection(cls) -> bool:
        """Verify connection to Neo4j"""
        try:
            driver = cls.get_driver()
            with driver.session() as session:
                session.run("RETURN 1")
            return True
        except Exception as e:
            print(f"Neo4j connection failed: {e}")
            return False


def get_db() -> Driver:
    """Dependency injection for FastAPI"""
    return Neo4jConnection.get_driver()



class AsyncNeo4j:
    """Async Neo4j driver for the FastAPI app (one driver per process)."""
    
    _driver: "AsyncDriver | None" = None

    @classmethod
    def driver(cls) -> "AsyncDriver":
        if cls._driver is None:
            cls._driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
            )
        return cls._driver

    @classmethod
    async def verify(cls) -> bool:
        try:
            await cls.driver().verify_connectivity()
            return True
        except Exception as exc:  # noqa: BLE001 - we want to report any failure
            logging.getLogger("graphrag").error("Neo4j connectivity failed: %s", exc) # type: ignore
            return False

    @classmethod
    async def close(cls) -> None:
        if cls._driver is not None:
            await cls._driver.close()
            cls._driver = None