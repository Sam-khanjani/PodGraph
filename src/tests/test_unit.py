"""Fast tests: no Neo4j, no model, no LLM. Everything external is faked."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from src.agents import qa
from src.agents.llm import Claim
from src.ingestion.chunker import chunk, chunks_from_ranges, timestamp_turns
from src.ingestion.models import Segment, Transcript
from src.query.api import app, get_repo
from src.query.repository import NotFoundError

# ---- chunker ---------------------------------------------------------------------


def _transcript(n=10, text="x" * 100):
    return Transcript(podcast_name="P", episode_id="ep", episode_title="T",
                      segments=[Segment(text=text, start=i * 10.0, duration=10.0) for i in range(n)])


def test_chunker_groups_on_segment_boundaries_and_keeps_time():
    chunks = chunk(_transcript(), target=250)
    assert [c.chunk_id for c in chunks] == ["ep-0001", "ep-0002", "ep-0003", "ep-0004"]
    assert (chunks[0].timestamp_start, chunks[0].timestamp_end) == (0, 30)
    assert chunks[-1].timestamp_end == 100  # remainder flushed
    assert chunk(_transcript(), target=250) == chunks  # deterministic


def test_turn_timestamps_come_from_caption_segments():
    t = Transcript(podcast_name="P", episode_id="ep", episode_title="T", segments=[
        Segment(text="hello there\nhow are you", start=5, duration=3), Segment(text="I am fine thanks", start=8, duration=2),
        Segment(text="great to hear", start=10, duration=2)])
    c = chunk(t)[0]
    turns = timestamp_turns([{"text": "hello there how are you"}, {"text": "I am fine thanks great to hear"},
                             {"text": "not in the chunk at all"}], c)
    assert [x["start"] for x in turns] == [5, 8, 5]  # unmatched turn falls back to the chunk start


def test_semantic_ranges_become_chunks_and_long_topics_split():
    t = _transcript(n=10, text="x" * 600)
    segs = t.segments
    chunks = chunks_from_ranges(t, segs, [0, 3, 10])  # two topics: captions 0-2 and 3-9
    assert [c.chunk_id for c in chunks] == ["ep-0001", "ep-0002", "ep-0003"]  # 2nd topic is 4200 chars -> split
    assert (chunks[0].timestamp_start, chunks[0].timestamp_end) == (0, 30)
    assert chunks[1].timestamp_start == 30 and chunks[-1].timestamp_end == 100


def test_chunker_skips_blank_segments():
    t = _transcript(3, text="   ")
    t.segments.append(Segment(text="hi", start=30, duration=1))
    assert [c.text for c in chunk(t)] == ["hi"]


# ---- API (fake repository) --------------------------------------------------------


class FakeRepo:
    async def list_podcasts(self):
        return [{"name": "Huberman Lab", "host": "A", "episode_count": 2}]

    async def get_episode(self, episode_id):
        raise NotFoundError("Episode", episode_id)

    async def get_concept(self, name):
        return {"name": "Sleep", "category": "Physiology", "podcasts": [
            {"podcast": "A", "quotes": [{"episode_id": "e", "episode_title": "t", "quote": "q", "timestamp_start": 0}]},
            {"podcast": "B", "quotes": []}]}

    async def shared_guests(self):
        return [{"guest": "Matthew Walker", "podcasts": ["A", "B"], "episode_count": 2}]

    async def get_cached(self, q):
        return None

    async def cache(self, result):
        self.cached = result

    async def bridge_guests(self, a, b):
        return [{"guest": "G", "episodes": ["E"]}]

    async def person_mentions(self, person, concept):
        return [{"podcast": "A", "episode_id": "e", "episode_title": "t", "speaker": person, "concept": concept,
                 "timestamp": 61, "quote": "q"}]

    async def read_cypher(self, query):
        return [{"n": 3}]

    async def semantic_compare(self, vec, k):
        return [{"podcast": "A", "quotes": []}]


@pytest.fixture
def client():
    app.dependency_overrides[get_repo] = lambda: FakeRepo()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoints_shape_and_validation(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/podcasts").json()[0]["episode_count"] == 2
    assert client.get("/episodes/nope").status_code == 404
    assert {p["podcast"] for p in client.get("/concepts/sleep").json()["podcasts"]} == {"A", "B"}
    assert client.get("/insights/shared-guests").json()[0]["guest"] == "Matthew Walker"
    assert client.get("/search", params={"term": "a"}).status_code == 422
    assert client.get("/concepts", params={"limit": 999}).status_code == 422


# ---- agents (fake LLM) -----------------------------------------------------------


def _fake_llm(monkeypatch, plan, answer, claims=None):
    """Router, synthesis and verifier agents faked; verifier passes every sentence unless `claims` says otherwise."""
    monkeypatch.setattr(qa, "chat_json", lambda *a: plan)
    monkeypatch.setattr(qa, "chat", lambda *a: answer)

    async def verify_claims(question, answer, *a):
        return claims if claims is not None else [Claim(text=answer, supported=True)]
    monkeypatch.setattr(qa, "verify_claims", verify_claims)


def test_router_dispatches_tool_and_caches_verified_answer(monkeypatch):
    _fake_llm(monkeypatch, {"tool": "bridge_guests", "args": {"a": "Sleep", "b": "Magnesium"}}, "Answer.")
    repo = FakeRepo()
    out = asyncio.run(qa.answer("who bridges?", repo))
    assert out["tool"] == "bridge_guests" and out["sources"] == [{"guest": "G", "episodes": ["E"]}]
    assert out["answer"] == "Answer." and out["verified"] and repo.cached["question"] == "who bridges?"


def test_write_cypher_is_rejected_and_falls_back(monkeypatch):
    _fake_llm(monkeypatch, {"tool": "cypher", "args": {"query": "MATCH (n) DETACH DELETE n"}}, "Answer.")
    monkeypatch.setattr(qa, "embed", lambda texts: [[0.0] * 384])
    out = asyncio.run(qa.answer("drop everything", FakeRepo()))
    assert out["tool"] == "semantic_compare" and out["sources"] == [{"podcast": "A", "quotes": []}]


def test_verifier_reports_unsupported_sentences_and_leaves_the_answer_alone(monkeypatch):
    ok = "Bruno talked about it (A — t, 01:01)."                # evidence timestamp 61s = 01:01
    bad_time = "He returned to it later (A — t, 05:00)."       # 05:00 is nowhere in the evidence
    unsupported = "He also said it changed his career (A — t, 01:01)."
    draft = f"{ok} {bad_time} {unsupported}"
    _fake_llm(monkeypatch, {"tool": "person_mentions", "args": {"person": "Bruno", "concept": "x"}}, draft,
              claims=[Claim(text=ok, supported=True), Claim(text=bad_time, supported=True),
                      Claim(text=unsupported, supported=False, reason="career change not in evidence")])
    repo = FakeRepo()
    out = asyncio.run(qa.answer("when did Bruno talk about x?", repo))
    assert out["answer"] == draft and not out["verified"] and repo.cached["verified"] is False
    v = out["verification"]
    assert v["bad_timestamps"] == ["05:00"] and (v["claims"], v["supported"]) == (3, 1)
    assert [u["reason"] for u in v["unsupported"]] == ["cited timestamp is not in the evidence",
                                                        "career change not in evidence"]
