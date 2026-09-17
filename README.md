# PodGraph 🎙️ — GraphRAG over podcasts

Ask questions across podcasts and get answers that cite the show and episode. Real example, real
transcripts (two YouTube episodes: *Beyond Coding* and *Silicon Valley Girl*):

```
POST /query {"question": "What do the two shows say about AI agents?"}

→ In "Beyond Coding," the speaker emphasizes that AI agents can serve as revolutionary tools, aiding
  programmers by generating code, while the individual still takes pride in the final proposals they
  contribute (Beyond Coding — Why World Class Engineers Get Jobs on Easy Mode). Conversely, "Silicon
  Valley Girl" highlights a gap in AI utilization within businesses: many use tools like ChatGPT but
  have not integrated them into core operations (Silicon Valley Girl — The Biggest AI Opportunities
  Are Hiding in Boring Businesses). ...
```

Transcripts are chunked, embedded locally, tagged with concepts by an LLM, and written into a
**Neo4j knowledge graph** linking podcasts, episodes, guests, passages and concepts. Retrieval is
*vector to find, graph to connect*: a semantic hit immediately knows which show, episode and guest.
A router agent picks the right graph tool for a question; a synthesis agent writes the cited answer.

## Run it

```bash
cp .env.example .env      # add OPENROUTER_API_KEY (needed for /query and for concept/metadata extraction)
make up                   # Neo4j in Docker
make install              # poetry install (PyTorch CPU, ~2 GB, one-time)
make init-db              # constraints + vector index
make ingest-sample        # the two saved real episodes: chunk → embed → LLM tags → graph (~2 min)
make api                  # http://localhost:8010/docs
```

Add any episode that has YouTube captions (no YouTube key needed; host/guest are inferred if omitted):

```bash
poetry run python -m src.ingestion.pipeline youtube VIDEO_ID --podcast "Show name" [--host ... --guest ...]
```
The transcript is saved to `data/transcripts/` so the graph can be rebuilt offline (`make ingest-sample`).

## What the graph buys you

| Endpoint | Question | Why plain search can't |
|---|---|---|
| `GET /insights/concept-reach` | Which topics span both shows? → AI, AI Agents, Entrepreneurship, Problem Solving… | aggregation over `MENTIONS` |
| `GET /insights/shared-guests` | Who appeared on more than one show? | join across shows via `APPEARED_IN` |
| `GET /insights/bridge-guests?concept_a=&concept_b=` | Whose episodes touch *both* topics? | multi-hop path |
| `GET /concepts/{name}` | What does *each* show say about a concept? | grouping by structure |
| `GET /insights/semantic-compare?q=` | Same, for *any phrasing* | vector finds, graph groups |
| `GET /search/semantic?q=` | Meaning-based passage search with show/episode/guest attached | one Cypher query: vector index + traversal |
| `POST /query` | Free-form question → cited answer | router agent + graph tools + synthesis |

Keyword vs meaning, on the real data: `GET /search?term=hiring` finds 1 passage;
`GET /search/semantic?q=how to get hired as an engineer` returns the Reddit-hiring anecdote (0.68),
the CPA-hiring passage from the other show (0.65), and more — none of which needed the word.

The agent picks tools by itself:

| Question | Tool chosen |
|---|---|
| Who are the guests and which show was each on? | `cypher` — writes and runs read-only Cypher |
| What advice does Bruno give about contributing to open source? | `semantic_compare` |
| Which topics come up on both shows? | `concept_reach` |
| How long is each episode? | `cypher` on `Episode.duration_seconds` |

## Who said what, when

Captions have no speaker labels, so the same LLM pass that tags concepts also splits every chunk into
speaker turns (it is told who is in the room) and each turn is aligned back to its caption segment for a
timestamp. That lands on the graph as `(Chunk)-[:MENTIONS {speaker, start, quote}]->(Concept)`, which
makes "when did *person* talk about *X*, on which show" a one-pattern query:

```
GET /people                                   → Bruno Schaatsbergen 232 · Alex Mashrab 105 · Marina Mogilko 70 · Patrick Akil 40
GET /people/bruno/mentions?concept=terraform  → Beyond Coding 1:21 "…it's pretty much shaped my career…"
                                                Beyond Coding 7:48 "Yeah. And Terraform ecosystem."  … (7 mentions)
POST /query "When did Bruno talk about Terraform, and on which podcast?"
  → tool person_mentions → "…on Beyond Coding, 'Why World Class Engineers Get Jobs on Easy Mode', starting at 1:21 …"
```

`GET /episodes/{id}` returns each chunk's turns (`speaker`, `text`, `start`, `concepts`). Attribution is
inferred from text — reliable for two-person interviews, "Unknown" when it can't tell.

## How it works

```
transcript (file | YouTube) → chunker → embedder (MiniLM, local) → LLM: metadata + concepts → graph writer → Neo4j
                                                 ▲ Kafka seam: today a function call
FastAPI ── repository (all Cypher) ── Neo4j                    POST /query: cache → router agent → tool → synthesis agent
```

- **Ingestion is idempotent and self-healing** — deterministic chunk ids + `MERGE`; stale chunks pruned; re-tagging replaces old tags; every run leaves an `IngestRun` audit node; the flaky steps (YouTube, LLM) retry with backoff.
- **Embeddings are local and free** — `all-MiniLM-L6-v2` (384-d) on `Chunk.embedding`, queried via Neo4j's native vector index. No separate vector DB.
- **Concepts converge across shows** — the extractor is shown the graph's most-used concept names so "AI Agents" from one episode lands on the same node as from another.
- **LLM via OpenRouter** — any model id in `LLM_MODEL` (default `openai/gpt-4o-mini`; the two episodes cost a few cents). Answers cached as `CachedAnswer` nodes, invalidated on ingest.
- **LLM-written Cypher is read-only by construction** — keyword check + Neo4j read transaction; empty or failing queries fall back to semantic retrieval.
- **Kafka is deliberately deferred** — see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

Docs: [ARCHITECTURE](docs/ARCHITECTURE.md) · [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) · [AGENTS](docs/AGENTS.md) · [API](docs/API.md) · [DEPLOYMENT](docs/DEPLOYMENT.md)

## Layout

```
src/
├── ingestion/   models · sources (file, YouTube) · chunker · embedder · graph_writer · pipeline (CLI)
├── agents/      llm (OpenRouter call, concept + metadata extractors) · qa (router → tool → synthesis, cache)
├── query/       api (FastAPI) · repository (all Cypher) · schemas · db (drivers)
├── setup/       init_neo4j (schema)
└── tests/       test_unit (no external deps) · test_live (needs Neo4j + ingested data; auto-skips otherwise)
config/neo4j_schema.cypher   constraints + vector index
data/transcripts/            real transcripts fetched from YouTube, kept for offline rebuilds
```

## Tests & CI

`make test` runs both layers (live tests need `make ingest-sample`, with or without `--no-llm`).
GitHub Actions ingests the saved transcripts into a Neo4j service container, runs the suite, and on
`main` pushes the API image to GHCR.

License: Apache 2.0
