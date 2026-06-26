import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.query.db import AsyncNeo4j
from src.query.repository import NotFoundError
from src.query.routers import concepts, episodes, guests, podcasts, search, system

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("graphrag")

tags_metadata = [
    {"name": "system", "description": "Liveness and readiness probes."},
    {"name": "podcasts", "description": "Podcasts in the knowledge graph."},
    {"name": "episodes", "description": "Episode detail with guests and transcript chunks."},
    {"name": "concepts", "description": "Concepts and the cross-podcast graph-power view."},
    {"name": "guests", "description": "Guests and everything they connect to."},
    {"name": "search", "description": "Keyword search over chunk text."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    logger.info("Starting GraphRAG API...")
    if await AsyncNeo4j.verify():
        logger.info("Neo4j connectivity OK")
    else:
        logger.warning("Neo4j NOT reachable at startup (will retry per-request)")
    yield
    # --- shutdown ---
    logger.info("Shutting down; closing Neo4j driver")
    await AsyncNeo4j.close()


app = FastAPI(
    title="PodGraph Podcast AI",
    description="Cross-podcast synthesis over a Neo4j knowledge graph.",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    """Turn any domain NotFoundError into a clean HTTP 404."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "entity": exc.entity, "key": exc.key},
    )


app.include_router(system.router)
app.include_router(podcasts.router)
app.include_router(episodes.router)
app.include_router(concepts.router)
app.include_router(guests.router)
app.include_router(search.router)