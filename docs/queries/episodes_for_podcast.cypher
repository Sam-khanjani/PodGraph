// Episodes of a given podcast, newest first
MATCH (p:Podcast {name: $podcast_name})-[:HAS_EPISODE]->(e:Episode)
RETURN e.number AS number, e.title AS title, e.publish_date AS published
ORDER BY e.number DESC;