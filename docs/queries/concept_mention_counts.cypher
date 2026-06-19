// How often is each concept mentioned, and across how many podcasts?
MATCH (c:Concept)<-[:MENTIONS]-(:Chunk)<-[:CONTAINS]-(:Episode)<-[:HAS_EPISODE]-(p:Podcast)
RETURN c.name AS concept,
       count(*) AS mentions,
       count(DISTINCT p.name) AS podcasts
ORDER BY mentions DESC;