from neo4j import GraphDatabase, Driver
from src.config import settings
from typing import Optional


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