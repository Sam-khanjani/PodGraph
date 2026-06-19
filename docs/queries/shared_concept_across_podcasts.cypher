// "What do different shows say about the same concept?"
// The core GraphRAG query — one Concept node, chunks from many podcasts.
MATCH (c:Concept {name: $concept})<-[:MENTIONS]-(chunk:Chunk)
      <-[:CONTAINS]-(e:Episode)<-[:HAS_EPISODE]-(p:Podcast)
RETURN p.name AS podcast, p.host AS host, e.title AS episode,
       chunk.text AS quote, chunk.timestamp_start AS ts
ORDER BY p.name, ts;