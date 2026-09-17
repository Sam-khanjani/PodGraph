"""Neo4j drivers. Sync for batch/CLI work, async for the API — one of each per process."""

from neo4j import AsyncGraphDatabase, GraphDatabase

from src.config import settings

_auth = (settings.neo4j_username, settings.neo4j_password) if settings.neo4j_password else None
_sync = None
_async = None


def driver():
    global _sync
    if _sync is None:
        _sync = GraphDatabase.driver(settings.neo4j_uri, auth=_auth, connection_timeout=5)
    return _sync


def async_driver():
    global _async
    if _async is None:
        _async = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=_auth)
    return _async


def run(query: str, **params) -> list[dict]:
    """Run one query on the sync driver, return rows as dicts."""
    with driver().session() as s:
        return s.run(query, **params).data()


def close() -> None:
    global _sync
    if _sync is not None:
        _sync.close()
        _sync = None
