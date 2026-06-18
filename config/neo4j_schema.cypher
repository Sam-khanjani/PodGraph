// ============================================================
// GraphRAG Podcast AI — Neo4j Schema
// Neo4j 5.x syntax.
// NOTE: Neo4j 5 uses "FOR ... REQUIRE", NOT the old 4.x
// "ON ... ASSERT" you'll see in many tutorials. Don't copy those.
// ============================================================

// ---------- Uniqueness constraints ----------
// A uniqueness constraint also creates a backing index for free,
// so lookups on these keys are fast.

CREATE CONSTRAINT podcast_name_unique IF NOT EXISTS
FOR (p:Podcast) REQUIRE p.name IS UNIQUE;

CREATE CONSTRAINT episode_id_unique IF NOT EXISTS
FOR (e:Episode) REQUIRE e.episode_id IS UNIQUE;

CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
FOR (chk:Chunk) REQUIRE chk.chunk_id IS UNIQUE;

CREATE CONSTRAINT guest_name_unique IF NOT EXISTS
FOR (g:Guest) REQUIRE g.name IS UNIQUE;

CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS UNIQUE;

// ---------- Secondary indexes (speed up common filters) ----------

CREATE INDEX episode_number_idx IF NOT EXISTS
FOR (e:Episode) ON (e.number);

CREATE INDEX concept_category_idx IF NOT EXISTS
FOR (c:Concept) ON (c.category);