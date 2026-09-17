# Graph Schema

## Nodes
| Label | Key | Other properties |
|---|---|---|
| Podcast | name | host, platform_url |
| Episode | episode_id | title, number, publish_date (date), summary, audio_url, duration_seconds |
| Chunk | chunk_id | text, timestamp_start, timestamp_end, embedding (384 floats), turns (JSON: speaker turns) |
| Guest | name | title, institution, bio |
| Concept | name | category (one word chosen by the extractor: Skill, Technology, Tool, Company, Career, ...) |
| IngestRun | — (append-only) | run_at, status, episode_id, chunks, reason |
| CachedAnswer | key (lower-cased question) | question, answer, tool, args, sources (JSON), created_at |

## Relationships
- (Podcast)-[:HAS_EPISODE]->(Episode)
- (Episode)-[:CONTAINS]->(Chunk)
- (Guest)-[:APPEARED_IN]->(Episode)
- (Chunk)-[:MENTIONS {speaker, start, quote}]->(Concept) — one edge per (chunk, concept, speaker): who said it, when
- (IngestRun)-[:INGESTED]->(Episode)

## Constraints & indexes (`config/neo4j_schema.cypher`, applied by `make init-db`)
- Unique: Podcast.name, Episode.episode_id, Chunk.chunk_id, Guest.name, Concept.name
- Range: Episode.number, Concept.category, CachedAnswer.key
- Vector: `chunk_embedding_index` on Chunk.embedding — 384 dims, cosine (must match `src/ingestion/embedder.py`)

## Design notes
- Synthetic keys (`episode_id`, `chunk_id = episode_id-0001…`) are deterministic → re-ingestion is idempotent.
- `IngestRun` uses `CREATE`, not `MERGE`: state is idempotent, history is append-only.
- Concepts `MERGE` on name, so the same concept from different shows shares one node; category is only set on create.
- Re-ingesting an episode with the LLM on replaces its `MENTIONS` edges and deletes concepts nothing mentions any more.
