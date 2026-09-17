# Architecture

## Ingestion (batch, sync driver)

```
sources.from_file / from_youtube  →  Transcript
chunker.chunk                     →  list[Chunk]     ~1000 chars, breaks on caption boundaries, keeps timestamps
embedder.embed                    →  Chunk.embedding  all-MiniLM-L6-v2, 384-d, normalised, CPU
llm.extract_concepts (threaded)   →  Chunk.concepts   [{name, category}] per chunk
---------------------------------- KAFKA SEAM ----------------------------------
graph_writer.write                →  Neo4j            MERGE podcast/episode/guest/chunks/concepts, prune stale, IngestRun
```

Everything left of the seam produces plain Pydantic objects; everything right of it only consumes
them. Today `pipeline.ingest()` calls `write()` directly. With Kafka, the chunker side becomes a
producer on a `graph-updates` topic and `write()` runs in a consumer — neither side's logic changes.

**Why no Kafka now:** volume is a handful of episodes on demand, one ingest at a time, and a failed
run is simply re-run (the writer is idempotent). A broker would be over-engineering; the seam keeps
the option open. The Kafka service is still defined in `docker-compose.yml` but nothing uses it.

**Failure handling:** the only flaky step (YouTube fetch) gets 3 retries with backoff. Every run —
success or failure — appends an `IngestRun` node (`docs/queries/ingest_history.cypher`).

## Query (live, async driver)

```
FastAPI endpoint → GraphRepository (one per request, bound to an async session) → Neo4j
```

All Cypher lives in `src/query/repository.py`. CPU-bound work in async handlers (embedding a query,
calling the LLM) runs via `asyncio.to_thread` so the event loop never blocks.

Semantic search is one query: `db.index.vector.queryNodes` finds chunks, then a `MATCH` walks to
episode, podcast and guest. That's the GraphRAG core — no second lookup system.

## Agents

See [AGENTS.md](AGENTS.md). `POST /query` = cache check → router agent → one graph tool → synthesis agent → cache.

## Storage

Neo4j holds everything: the knowledge graph, the vectors (native vector index), the ingest audit
trail and the answer cache. One database, one backup, no extra services.
