# Architecture

## Ingestion — a LangGraph, one node per agent

```
segment ─▶ embed ─▶ analyse ─▶ resolve_concepts ─▶ recommend ─▶ write        (--no-llm: segment ─▶ embed ─▶ write)
```

| node | what | how |
|---|---|---|
| `segment` | semantic chunking | LLM marks topic changes in ~8k-char windows of numbered captions; over-long topics split at 2500 chars on caption boundaries |
| `embed` | vectors | `all-MiniLM-L6-v2`, 384-d, CPU, local |
| `analyse` | per chunk: topic, summary, speaker turns, concept candidates | one typed LLM call per chunk (`LLM_PARALLEL` at a time); turns aligned to captions for timestamps |
| `resolve_concepts` | concept bank | each candidate name is embedded and matched against `concept_embedding_index`: ≥0.92 reuse · 0.80–0.92 LLM "same concept?" · else add to bank |
| `recommend` | `RECOMMENDS` relations | per chunk, only between its resolved concepts, with a reason and the chunk as evidence |
| `write` | Neo4j | idempotent MERGE by deterministic ids; tags/relations replaced on re-ingest; `IngestRun` audit |

The state passed between nodes is a `Transcript` plus `list[Chunk]` (Pydantic) — the same objects a Kafka
message would carry, so the seam between `recommend` and `write` is where a broker would slot in.

**Why LangGraph:** the design is a small state machine with one agent per job; `StateGraph` expresses
exactly that and keeps each agent a plain typed function. Parallelism is inside a node
(`asyncio.gather`, semaphore of `LLM_PARALLEL`) rather than graph fan-out — same speed, far less state plumbing.
**Why no Kafka now:** a handful of episodes on demand, one at a time, failed runs simply re-run.

**Failure handling:** the LLM clients retry transient errors and rate limits (5×); YouTube fetch retries 3×. Every run —
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
