# Graph Schema

## Nodes
| Label | Key | Other properties |
|---|---|---|
| Podcast | name | host, platform_url |
| Episode | episode_id | title, number, publish_date (date), summary, audio_url, duration_seconds |
| Chunk | chunk_id | text, topic, summary, timestamp_start, timestamp_end, embedding (384 floats), turns (JSON: speaker turns) |
| Guest | name | title, institution, bio |
| Concept | name | category (one word), embedding of the name (the concept bank's vector index) |
| IngestRun | — (append-only) | run_at, status, episode_id, chunks, reason |
| CachedAnswer | key (lower-cased question) | question, answer, tool, args, sources (JSON), created_at |

## Relationships
- (Podcast)-[:HAS_EPISODE]->(Episode)
- (Episode)-[:CONTAINS]->(Chunk)
- (Guest)-[:APPEARED_IN]->(Episode)
- (Chunk)-[:MENTIONS {speaker, start, quote}]->(Concept) — one edge per (chunk, concept, speaker): who said it, when
- (Concept)-[:RECOMMENDS {reason, chunk_id, episode_id}]->(Concept) — 'source helps target', one edge per passage that says so
- (IngestRun)-[:INGESTED]->(Episode)

## Constraints & indexes (`config/neo4j_schema.cypher`, applied by `make init-db`)
- Unique: Podcast.name, Episode.episode_id, Chunk.chunk_id, Guest.name, Concept.name
- Range: Episode.number, Concept.category, CachedAnswer.key
- Vector: `chunk_embedding_index` on Chunk.embedding and `concept_embedding_index` on Concept.embedding — 384 dims, cosine

## Design notes
- Chunks are topic-sized (LLM boundary detection), ids positional (`episode_id-0001…`) → re-ingestion replaces an episode's chunks wholesale.
- `IngestRun` uses `CREATE`, not `MERGE`: state is idempotent, history is append-only.
- Concepts `MERGE` on name, so the same concept from different shows shares one node; category is only set on create.
- Re-ingesting an episode with the LLM on replaces its `MENTIONS` edges and deletes concepts nothing mentions any more.
