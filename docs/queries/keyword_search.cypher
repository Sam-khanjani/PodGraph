// Naive keyword search over chunk text.
// CONTAINS is a plain substring match (case-sensitive) — NOT semantic search.
// Real vector search arrives in Week 8; this is here to feel the difference.
MATCH (c:Chunk)
WHERE toLower(c.text) CONTAINS toLower($term)
MATCH (e:Episode)-[:CONTAINS]->(c)
RETURN e.title AS episode, c.text AS chunk
LIMIT 10;