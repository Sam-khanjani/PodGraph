// All chunks of an episode, in playback order
MATCH (e:Episode {episode_id: $episode_id})-[:CONTAINS]->(c:Chunk)
RETURN c.timestamp_start AS start, c.timestamp_end AS end, c.text AS text
ORDER BY c.timestamp_start;