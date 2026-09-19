import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from src.agents import qa
from src.ingestion.embedder import embed
from src.query import schemas as s
from src.query.db import async_driver
from src.query.repository import GraphRepository, NotFoundError

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await async_driver().close()


app = FastAPI(title="PodGraph", description="Cross-podcast synthesis over a Neo4j knowledge graph.",
              version="0.2.0", lifespan=lifespan)


@app.exception_handler(NotFoundError)
async def not_found(_: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def get_repo():
    async with async_driver().session() as session:
        yield GraphRepository(session)


Repo = Annotated[GraphRepository, Depends(get_repo)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


async def embed_query(text: str) -> list[float]:
    return (await asyncio.to_thread(embed, [text]))[0]  # CPU-bound: keep it off the event loop


# ---- system ----------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
async def ready():
    try:
        await async_driver().verify_connectivity()
    except Exception as exc:
        raise HTTPException(503, f"Neo4j not reachable: {exc}")
    return {"status": "ready"}


# ---- entities --------------------------------------------------------------------

@app.get("/podcasts", response_model=list[s.PodcastOut], tags=["entities"])
async def list_podcasts(repo: Repo):
    return await repo.list_podcasts()


@app.get("/episodes/{episode_id}", response_model=s.EpisodeOut, tags=["entities"])
async def get_episode(episode_id: str, repo: Repo):
    return await repo.get_episode(episode_id)


@app.get("/guests/{name}", response_model=s.GuestOut, tags=["entities"])
async def get_guest(name: str, repo: Repo):
    return await repo.get_guest(name)


@app.get("/concepts", response_model=list[s.ConceptSummary], tags=["entities"])
async def list_concepts(repo: Repo, category: str | None = None, limit: Limit = 20, offset: Offset = 0):
    return await repo.list_concepts(category, limit, offset)


@app.get("/concepts/{name}", response_model=s.ConceptOut, tags=["entities"],
         summary="What each show says about a concept (case-insensitive)")
async def get_concept(name: str, repo: Repo):
    return await repo.get_concept(name)


@app.get("/concepts/{name}/recommendations", response_model=list[s.RecommendationOut], tags=["entities"],
         summary="What this concept is recommended for / by, with the passage that said so")
async def concept_recommendations(name: str, repo: Repo):
    return await repo.concept_recommendations(name)


# ---- people: who said what, when, on which show -----------------------------------

@app.get("/people", response_model=list[s.PersonOut], tags=["people"], summary="Everyone attributed as a speaker")
async def list_people(repo: Repo):
    return await repo.list_people()


@app.get("/people/{name}", response_model=list[s.PersonTopic], tags=["people"], summary="What a person talks about")
async def person_topics(name: str, repo: Repo):
    return await repo.person_topics(name)


@app.get("/people/{name}/mentions", response_model=list[s.Mention], tags=["people"],
         summary="When and on which show a person talked about a concept")
async def person_mentions(name: str, repo: Repo, concept: str | None = None):
    return await repo.person_mentions(name, concept)


# ---- search ----------------------------------------------------------------------

@app.get("/search", response_model=list[s.SearchHit], tags=["search"], summary="Keyword (substring) search")
async def search(repo: Repo, term: Annotated[str, Query(min_length=2)], limit: Limit = 20, offset: Offset = 0):
    return await repo.search_chunks(term, limit, offset)


@app.get("/search/semantic", response_model=list[s.SearchHit], tags=["search"],
         summary="Semantic search: meaning, not substrings, with podcast/episode/guest context")
async def semantic_search(repo: Repo, q: Annotated[str, Query(min_length=2)], k: Annotated[int, Query(ge=1, le=50)] = 8):
    return await repo.semantic_search(await embed_query(q), k)


# ---- insights: the queries that justify the graph --------------------------------

@app.get("/insights/shared-guests", response_model=list[s.SharedGuest], tags=["insights"])
async def shared_guests(repo: Repo):
    return await repo.shared_guests()


@app.get("/insights/concept-reach", response_model=list[s.ConceptReach], tags=["insights"])
async def concept_reach(repo: Repo, min_podcasts: Annotated[int, Query(ge=1)] = 2, limit: Limit = 20):
    return await repo.concept_reach(min_podcasts, limit)


@app.get("/insights/bridge-guests", response_model=list[s.BridgeGuest], tags=["insights"],
         summary="Guests whose episodes touch BOTH concepts")
async def bridge_guests(repo: Repo, concept_a: Annotated[str, Query(min_length=2)],
                        concept_b: Annotated[str, Query(min_length=2)]):
    return await repo.bridge_guests(concept_a, concept_b)


@app.get("/insights/semantic-compare", response_model=list[s.PodcastQuotes], tags=["insights"],
         summary="What does EACH show say about this? Any phrasing — vector finds, graph groups")
async def semantic_compare(repo: Repo, q: Annotated[str, Query(min_length=2)], k: Annotated[int, Query(ge=2, le=50)] = 12):
    return await repo.semantic_compare(await embed_query(q), k)


# ---- agentic Q&A -----------------------------------------------------------------

@app.post("/query", response_model=s.Answer, tags=["agents"],
          summary="Ask a cross-podcast question; router agent -> graph -> synthesis agent")
async def query(body: s.Question, repo: Repo):
    try:
        return await qa.answer(body.question, repo)
    except Exception as exc:
        logging.exception("query failed")
        raise HTTPException(502, f"LLM/graph step failed: {exc}")
