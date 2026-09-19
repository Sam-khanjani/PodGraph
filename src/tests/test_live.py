"""Integration tests against a running Neo4j with the real episodes in data/transcripts ingested:

    make up && make init-db && make ingest-sample     (or `--no-llm` — these tests need no concepts)

Skipped automatically when Neo4j is unreachable. No LLM calls.
"""

import pytest
from fastapi.testclient import TestClient

from src.ingestion import sources
from src.ingestion.pipeline import backfill, ingest
from src.query import db
from src.query.api import app

try:
    db.driver().verify_connectivity()
except Exception:
    pytestmark = pytest.mark.skip("Neo4j not reachable")

SAMPLE = "data/transcripts/yt-cVGHg4Vd9uM.json"  # Silicon Valley Girl, ~25k chars


def _chunks(episode_id):
    return db.run("MATCH (:Episode {episode_id: $id})-[:CONTAINS]->(c) RETURN count(c) AS n", id=episode_id)[0]["n"]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_ingest_is_idempotent_and_self_healing():
    t = sources.from_file(SAMPLE)
    t.episode_id, t.podcast_name = "test-episode", "Test Podcast"  # a throwaway copy: never touch the real episode
    try:
        ingest(t, llm=False)
        first = _chunks(t.episode_id)
        assert first >= 20
        ingest(t, llm=False)  # re-run: same count, no duplicates
        assert _chunks(t.episode_id) == first
        t.segments = t.segments[:10]  # shorter transcript: stale chunks are pruned
        ingest(t, llm=False)
        assert _chunks(t.episode_id) == 1
        assert db.run("MATCH (r:IngestRun {episode_id: $id}) RETURN count(r) AS n", id=t.episode_id)[0]["n"] == 3
    finally:
        db.run("MATCH (n) WHERE n.episode_id = $id OR n:Podcast AND n.name = 'Test Podcast' "
               "OPTIONAL MATCH (n)-[:CONTAINS]->(c) DETACH DELETE n, c", id=t.episode_id)


def test_backfill_is_idempotent():
    backfill()
    assert backfill() == 0
    assert db.run("MATCH (c:Chunk) WHERE c.embedding IS NULL RETURN count(c) AS n")[0]["n"] == 0


def test_entity_endpoints(client):
    shows = {p["name"] for p in client.get("/podcasts").json()}
    assert {"Beyond Coding", "Silicon Valley Girl"} <= shows
    ep = client.get("/episodes/yt-cVGHg4Vd9uM").json()
    assert ep["podcast"] == "Silicon Valley Girl" and len(ep["chunks"]) >= 20
    assert ep["chunks"] == sorted(ep["chunks"], key=lambda c: c["timestamp_start"])
    assert client.get("/episodes/nope").status_code == 404


def test_semantic_search_finds_meaning_not_substrings(client):
    assert client.get("/search", params={"term": "xyzzy-not-a-word"}).json() == []
    hits = client.get("/search/semantic", params={"q": "how to get hired as a software engineer", "k": 5}).json()
    assert len(hits) == 5 and hits[0]["score"] >= hits[-1]["score"]
    assert hits[0]["podcast"] == "Beyond Coding"  # that episode is about engineering careers
    compare = client.get("/insights/semantic-compare", params={"q": "advice for growing your career", "k": 40}).json()
    assert {p["podcast"] for p in compare} == {"Beyond Coding", "Silicon Valley Girl"}
    assert all(1 <= len(p["quotes"]) <= 3 for p in compare)  # top 3 per show, not a dump
