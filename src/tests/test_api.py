"""
FastAPI endpoint tests — NO database required.

We override the `get_repository` dependency with a fake, so routing,
validation, serialization, and error handling are tested in isolation.
"""

from fastapi.testclient import TestClient

from src.query.api import app
from src.query.dependencies import get_repository
from src.query.repository import NotFoundError


class FakeRepository:
    async def list_podcasts(self):
        return [{"name": "Huberman Lab", "host": "Andrew Huberman",
                 "platform_url": "https://hubermanlab.com", "episode_count": 2}]

    async def get_episode(self, episode_id: str):
        if episode_id != "huberman-31":
            raise NotFoundError("Episode", episode_id)
        return {"episode_id": "huberman-31", "title": "Using Sleep to Learn",
                "number": 31, "publish_date": "2021-08-02", "summary": "s",
                "audio_url": "https://x", "podcast": "Huberman Lab", "guests": [],
                "chunks": [{"chunk_id": "huberman-31-0001", "text": "Sleep...",
                            "timestamp_start": 0, "timestamp_end": 45}]}

    async def list_concepts(self, category, limit, offset):
        data = [{"name": "Sleep", "category": "Physiology", "mentions": 6},
                {"name": "Magnesium", "category": "Supplement", "mentions": 2}]
        if category:
            data = [d for d in data if d["category"] == category]
        return data[offset: offset + limit]

    async def get_concept(self, name: str):
        if name.lower() != "sleep":
            raise NotFoundError("Concept", name)
        return {"name": "Sleep", "category": "Physiology", "podcasts": [
            {"podcast": "Huberman Lab", "host": "Andrew Huberman",
             "quotes": [{"episode_id": "huberman-31", "episode_title": "t",
                         "quote": "q", "timestamp_start": 0}]},
            {"podcast": "The Peter Attia Drive", "host": "Peter Attia",
             "quotes": [{"episode_id": "attia-walker-sleep", "episode_title": "t",
                         "quote": "q", "timestamp_start": 0}]},
        ]}

    async def get_guest(self, name: str):
        if name.lower() != "matthew walker":
            raise NotFoundError("Guest", name)
        return {"name": "Matthew Walker", "title": "Professor",
                "institution": "UC Berkeley", "bio": "b",
                "podcasts": ["Huberman Lab", "The Peter Attia Drive"],
                "episodes": [], "concepts": ["Magnesium", "Sleep"]}

    async def search_chunks(self, term, limit, offset):
        return [{"episode_id": "huberman-31", "episode_title": "t",
                 "chunk_id": "huberman-31-0001", "text": "Sleep is...",
                 "timestamp_start": 0}]


# Override the dependency BEFORE creating the client.
app.dependency_overrides[get_repository] = lambda: FakeRepository()

# No `with` block -> lifespan is NOT triggered -> the real driver is never created.
client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_list_podcasts_shape():
    body = client.get("/podcasts").json()
    assert body[0]["name"] == "Huberman Lab"
    assert body[0]["episode_count"] == 2


def test_get_episode_found():
    r = client.get("/episodes/huberman-31")
    assert r.status_code == 200
    assert r.json()["episode_id"] == "huberman-31"


def test_get_episode_404():
    r = client.get("/episodes/nope")
    assert r.status_code == 404
    assert r.json()["entity"] == "Episode"


def test_concept_grouped_by_podcast():
    r = client.get("/concepts/sleep")          # case-insensitive
    assert r.status_code == 200
    shows = {p["podcast"] for p in r.json()["podcasts"]}
    assert {"Huberman Lab", "The Peter Attia Drive"} <= shows


def test_concept_404():
    assert client.get("/concepts/unobtanium").status_code == 404


def test_concepts_category_filter():
    r = client.get("/concepts", params={"category": "Supplement"})
    assert r.status_code == 200
    assert all(c["category"] == "Supplement" for c in r.json())


def test_concepts_bad_category_is_422():
    assert client.get("/concepts", params={"category": "NotReal"}).status_code == 422


def test_search_min_length():
    assert client.get("/search", params={"term": "a"}).status_code == 422
    assert client.get("/search", params={"term": "sleep"}).status_code == 200


def test_pagination_bounds():
    assert client.get("/concepts", params={"limit": 0}).status_code == 422
    assert client.get("/concepts", params={"limit": 999}).status_code == 422