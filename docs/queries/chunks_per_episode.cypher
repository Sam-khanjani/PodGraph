// How many chunks each episode has
MATCH (e:Episode)
OPTIONAL MATCH (e)-[:CONTAINS]->(c:Chunk)
RETURN e.title AS episode, count(c) AS chunk_count
ORDER BY chunk_count DESC;