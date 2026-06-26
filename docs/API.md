# API Reference & Tutorial

Base URL (local): `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`  
Raw OpenAPI schema: `http://localhost:8000/openapi.json`

---

## What this API is

The only way to read the graph without this API is the Neo4j Browser or `cypher-shell`. This service exposes the graph over HTTP as typed JSON — with validation, pagination, and interactive docs — so any client can query it without knowing Cypher.

It is built as a layered FastAPI service:

| Before | After |
|---|---|
| Single `api.py` file | Separate routers, repository, schemas, dependencies |
| Sync Neo4j driver inside `async def` (blocks the event loop) | Async Neo4j driver with `await` throughout |
| `@app.on_event("startup")` (deprecated) | `lifespan` context manager |
| No response validation | Pydantic response models on every endpoint |
| No tests | 10 unit tests (no DB) + 3 live integration tests |
| 3 endpoints | 8 endpoints with typed params, enums, pagination, 404/422 handling |

---

## Quick start

```bash
# Start the stack and seed the graph
make up
make setup-data

# Verify everything is healthy
curl http://localhost:8000/ready
# {"status":"ready","neo4j":"up"}

# Open interactive docs (try requests in the browser)
# http://localhost:8000/docs
```

---

## Endpoints

### System

#### `GET /health`
Liveness probe. Returns immediately without touching Neo4j — use this to check the process is up.

```bash
curl http://localhost:8000/health
```
```json
{"status": "ok", "service": "graphrag-api", "version": "0.1.0"}
```

#### `GET /ready`
Readiness probe. Verifies Neo4j is reachable. Returns `503` if the database is down — use this for load-balancer health checks.

```bash
curl http://localhost:8000/ready
```
```json
{"status": "ready", "neo4j": "up"}
```

---

### Podcasts

#### `GET /podcasts`
All podcasts in the graph with their episode counts.

```bash
curl http://localhost:8000/podcasts
```
```json
[
  {"name": "Huberman Lab", "host": "Andrew Huberman", "platform_url": "https://hubermanlab.com", "episode_count": 2},
  {"name": "The Peter Attia Drive", "host": "Peter Attia", "platform_url": "https://peterattiamd.com", "episode_count": 1}
]
```

---

### Episodes

#### `GET /episodes/{episode_id}`
Full episode detail: metadata, guests, and transcript chunks sorted by timestamp.

Returns `404` if the episode doesn't exist.

```bash
curl http://localhost:8000/episodes/huberman-31
```
```json
{
  "episode_id": "huberman-31",
  "title": "Using Sleep to Boost Performance",
  "number": 31,
  "publish_date": "2021-08-02",
  "podcast": "Huberman Lab",
  "guests": [
    {"name": "Matthew Walker", "title": "Professor", "institution": "UC Berkeley", "bio": "..."}
  ],
  "chunks": [
    {"chunk_id": "huberman-31-0001", "text": "Sleep is the foundation...", "timestamp_start": 0, "timestamp_end": 45}
  ]
}
```

---

### Concepts

#### `GET /concepts`
All concepts in the graph, sorted by how many chunks mention them. Supports optional category filtering and pagination.

| Query param | Type | Default | Constraint | Description |
|---|---|---|---|---|
| `category` | enum | none | see below | Filter by concept category |
| `limit` | int | 20 | 1–100 | Max items to return |
| `offset` | int | 0 | ≥0 | Items to skip |

Valid categories: `Supplement`, `Biomarker`, `Exercise`, `Diet`, `Disease`, `Physiology`

```bash
# All concepts
curl http://localhost:8000/concepts

# Filter to supplements only
curl "http://localhost:8000/concepts?category=Supplement"

# Paginate: second page of 5
curl "http://localhost:8000/concepts?limit=5&offset=5"
```

Invalid category returns `422` automatically — FastAPI validates the enum and explains the error without any code on your part:
```bash
curl "http://localhost:8000/concepts?category=NotReal"
# HTTP 422 — "Input should be 'Supplement', 'Biomarker', ..."
```

#### `GET /concepts/{name}`
The cross-podcast "graph power" view. Returns every quote mentioning this concept, grouped by podcast, so you can see what different shows say about the same topic.

Matching is case-insensitive. Names with spaces must be URL-encoded.

```bash
curl http://localhost:8000/concepts/Sleep
curl "http://localhost:8000/concepts/Circadian%20Rhythm"
```
```json
{
  "name": "Sleep",
  "category": "Physiology",
  "podcasts": [
    {
      "podcast": "Huberman Lab",
      "host": "Andrew Huberman",
      "quotes": [
        {"episode_id": "huberman-31", "episode_title": "Using Sleep...", "quote": "Sleep is the foundation...", "timestamp_start": 0}
      ]
    },
    {
      "podcast": "The Peter Attia Drive",
      "host": "Peter Attia",
      "quotes": [
        {"episode_id": "attia-walker-sleep", "episode_title": "...", "quote": "...", "timestamp_start": 120}
      ]
    }
  ]
}
```

This is the core value of the graph: one query returns what multiple podcasts say about a concept, with exact quotes and timestamps. A flat database would require multiple queries and manual joining.

---

### Guests

#### `GET /guests/{name}`
Guest detail with every podcast they appeared on, every episode, and the concepts discussed in those episodes — a multi-hop graph traversal in one request.

Matching is case-insensitive. Spaces must be URL-encoded.

```bash
curl "http://localhost:8000/guests/Matthew%20Walker"
```
```json
{
  "name": "Matthew Walker",
  "title": "Professor",
  "institution": "UC Berkeley",
  "bio": "...",
  "podcasts": ["Huberman Lab", "The Peter Attia Drive"],
  "episodes": [
    {"podcast": "Huberman Lab", "episode_id": "huberman-31", "episode_title": "...", "concepts": ["Sleep", "Magnesium"]},
    {"podcast": "The Peter Attia Drive", "episode_id": "attia-walker-sleep", "episode_title": "...", "concepts": ["Sleep"]}
  ],
  "concepts": ["Magnesium", "Sleep"]
}
```

---

### Search

#### `GET /search`
Case-insensitive substring search over all transcript chunk text. This is a naive keyword search — semantic/vector search arrives in Week 8.

| Query param | Type | Required | Constraint | Description |
|---|---|---|---|---|
| `term` | string | yes | min length 2 | Substring to find |
| `limit` | int | no | 1–100 | Max results (default 20) |
| `offset` | int | no | ≥0 | Items to skip (default 0) |

```bash
curl "http://localhost:8000/search?term=magnesium"
curl "http://localhost:8000/search?term=sleep&limit=5"
```
```json
[
  {
    "episode_id": "huberman-31",
    "episode_title": "Using Sleep to Boost Performance",
    "chunk_id": "huberman-31-0001",
    "text": "Sleep is the foundation of mental and physical health...",
    "timestamp_start": 0
  }
]
```

Single-character searches return `422` — the `min_length=2` constraint is enforced by FastAPI automatically.

> Semantic/vector search is not yet implemented. This endpoint matches text substrings only.

---

## Error reference

| HTTP status | Meaning | Who produces it |
|---|---|---|
| `200` | OK | — |
| `404` | Entity not found | Custom `NotFoundError` handler in `api.py` |
| `422` | Invalid query/path parameter | FastAPI automatic validation (Pydantic) |
| `503` | Neo4j unreachable | `/ready` endpoint only |

404 responses include `entity` and `key` fields to tell you exactly what wasn't found:
```json
{"detail": "Episode 'xyz' not found", "entity": "Episode", "key": "xyz"}
```

422 responses name the offending parameter and rule:
```json
{"detail": [{"loc": ["query", "limit"], "msg": "Input should be less than or equal to 100", ...}]}
```

---

## Testing

The project has two separate test suites.

### Unit tests — no database needed

These test routing, validation, serialization, and error handling using a fake repository. FastAPI's dependency injection (`Depends`) makes this possible: `get_repository` is overridden with a `FakeRepository` object that returns canned data. The real Neo4j driver is never created.

```bash
# No `make up` needed — runs anywhere
make test-api
# or: poetry run pytest src/tests/test_api.py -v
```

What's covered (10 tests):
- `GET /health` returns 200
- `GET /podcasts` returns the right shape
- `GET /episodes/{id}` returns 200 for known IDs, 404 for unknown
- `GET /concepts/{name}` returns quotes grouped by podcast; 404 for unknown
- `GET /concepts?category=` filters correctly; `422` for invalid enum values
- `GET /search?term=` validates minimum length (422 for single char)
- `GET /concepts?limit=` enforces bounds (422 for 0 or >100)

### Live integration tests — requires the stack

These hit the real running API over HTTP and assert on real graph data. They're guarded by an environment variable so `make test` doesn't fail when Docker is down.

```bash
make up
make setup-data
make test-live
```

What's covered (3 tests):
- `/ready` returns 200 (Neo4j reachable)
- `/concepts/Sleep` returns quotes from at least 2 different podcasts
- `/guests/Matthew Walker` lists exactly 2 podcasts

### Run everything

```bash
make up && make setup-data
make test       # all tests: graph schema tests + 10 API unit tests; live ones skipped
make test-live  # the 3 live integration tests
```

---

## Architecture

```
HTTP request
    │
    ▼
routers/          — URL paths, parameter validation, status codes, response_model
    │ Depends(get_repository)
    ▼
dependencies.py   — session lifecycle (yield), repository wiring, Pagination class
    │
    ▼
repository.py     — all Cypher queries; raises NotFoundError; returns plain dicts
    │
    ▼
db.py (AsyncNeo4j) — one async driver per process; created at startup, closed at shutdown

schemas.py        — Pydantic response models; used by routers as response_model
```

