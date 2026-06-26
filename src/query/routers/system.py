from fastapi import APIRouter, HTTPException, status

from src.query.db import AsyncNeo4j

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness probe")
async def health():
    """Returns ok if the API process is up. Does NOT check Neo4j."""
    return {"status": "ok", "service": "graphrag-api", "version": "0.1.0"}


@router.get("/ready", summary="Readiness probe")
async def ready():
    """Returns ok only if Neo4j is reachable. Use this for load-balancer readiness."""
    if await AsyncNeo4j.verify():
        return {"status": "ready", "neo4j": "up"}
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Neo4j is not reachable",
    )