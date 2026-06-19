// Which podcasts has a guest appeared on?
MATCH (g:Guest {name: $guest})-[:APPEARED_IN]->(e:Episode)<-[:HAS_EPISODE]-(p:Podcast)
RETURN DISTINCT p.name AS podcast, e.title AS episode
ORDER BY podcast;