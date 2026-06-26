"""
Live integration tests. Require the stack to be up and seeded:
    make up && make setup-data
    RUN_LIVE_TESTS=1 poetry run pytest src/tests/test_api_integration.py -v
"""

import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1",
    reason="set RUN_LIVE_TESTS=1 and run `make up && make setup-data` first",
)

BASE = "http://localhost:8000"


def test_ready():
    assert httpx.get(f"{BASE}/ready", timeout=10).status_code == 200


def test_concept_is_cross_podcast():
    r = httpx.get(f"{BASE}/concepts/Sleep", timeout=10)
    assert r.status_code == 200
    shows = {p["podcast"] for p in r.json()["podcasts"]}
    assert len(shows) >= 2          # the whole point of the graph


def test_guest_links_two_shows():
    r = httpx.get(f"{BASE}/guests/Matthew Walker", timeout=10)
    assert r.status_code == 200
    assert len(r.json()["podcasts"]) == 2