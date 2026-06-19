// Multi-hop: which concepts do a guest's episodes touch?
MATCH (g:Guest {name: $guest})-[:APPEARED_IN]->(:Episode)
      -[:CONTAINS]->(:Chunk)-[:MENTIONS]->(c:Concept)
RETURN DISTINCT c.name AS concept, c.category AS category
ORDER BY concept;