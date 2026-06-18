# Graph Schema

## Nodes
| Label | Key | Other properties |
|-------|-----|------------------|
| Podcast | name | host, platform_url |
| Episode | episode_id | title, number, publish_date, summary, audio_url |
| Chunk | chunk_id | text, timestamp_start, timestamp_end, (embedding — Week 8) |
| Guest | name | title, institution, bio  (Week 3) |
| Concept | name | category  (Week 3) |

## Relationships
- (Podcast)-[:HAS_EPISODE]->(Episode)
- (Episode)-[:CONTAINS]->(Chunk)
- (Guest)-[:APPEARED_IN]->(Episode)            # Week 3
- (Chunk)-[:MENTIONS]->(Concept)               # Week 3
- (Concept)-[:CONTRADICTS {reason}]->(Concept) # Week 3+
- (Concept)-[:RECOMMENDED_FOR {condition}]->(Concept)  # Week 3+

## Constraints & indexes
Defined in `config/neo4j_schema.cypher`, applied by `src/setup/init_neo4j.py`.
- Unique: Podcast.name, Episode.episode_id, Chunk.chunk_id, Guest.name, Concept.name
- Index:  Episode.number, Concept.category

## Design notes
- Synthetic keys (episode_id, chunk_id) instead of number/URL: globally unique, stable, idempotent.
- Dates stored as Neo4j `date` type (via `date(...)`), not strings — enables date comparisons.