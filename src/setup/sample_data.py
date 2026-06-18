"""
Seed the graph with one podcast, one episode, and a few transcript chunks,
plus the Podcast->Episode->Chunk relationships.

Run from the repo root:
    poetry run python -m src.setup.sample_data

Idempotent: uses MERGE, so running it repeatedly will not create duplicates.
In later weeks these chunks come from real transcripts via Kafka; for now
we hand-write a handful so we have something to query.
"""

import logging

from src.query.db import Neo4jConnection

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

PODCAST = {
    "name": "Huberman Lab",
    "host": "Andrew Huberman",
    "platform_url": "https://hubermanlab.com",
}

EPISODE = {
    "episode_id": "huberman-31",
    "title": "Using Sleep to Learn, Remember, and Recover",
    "number": 31,
    "publish_date": "2021-08-02",   # ISO format -> stored as a real Neo4j date
    "summary": "How sleep stages support learning, memory, and physical recovery.",
    "audio_url": "https://hubermanlab.com/episode-31",
}

# Hand-written chunks. Note the stable chunk_id keys: "<episode>-<index>".
CHUNKS = [
    {
        "chunk_id": "huberman-31-0001",
        "text": "Sleep is the foundation of mental and physical health. Each night "
                "we cycle through stages that each serve a different purpose.",
        "timestamp_start": 0,
        "timestamp_end": 45,
    },
    {
        "chunk_id": "huberman-31-0002",
        "text": "REM sleep is strongly associated with emotional processing and the "
                "consolidation of certain kinds of memory.",
        "timestamp_start": 45,
        "timestamp_end": 95,
    },
    {
        "chunk_id": "huberman-31-0003",
        "text": "Slow-wave deep sleep is when much of the body's physical restoration "
                "happens and metabolic byproducts are cleared from the brain.",
        "timestamp_start": 95,
        "timestamp_end": 150,
    },
    {
        "chunk_id": "huberman-31-0004",
        "text": "Getting sunlight in your eyes early in the day anchors your circadian "
                "rhythm, which improves the quality of sleep that night.",
        "timestamp_start": 150,
        "timestamp_end": 210,
    },
    {
        "chunk_id": "huberman-31-0005",
        "text": "Avoiding bright artificial light late at night protects melatonin "
                "release and makes it easier to fall asleep.",
        "timestamp_start": 210,
        "timestamp_end": 260,
    },
]


def seed() -> None:
    driver = Neo4jConnection.get_driver()

    with driver.session() as session:
        # 1) Podcast
        session.run(
            """
            MERGE (p:Podcast {name: $name})
            SET p.host = $host,
                p.platform_url = $platform_url
            """,
            **PODCAST, # type: ignore
        )
        logger.info("podcast ready: %s", PODCAST["name"])

        # 2) Episode + HAS_EPISODE relationship
        session.run(
            """
            MATCH (p:Podcast {name: $podcast_name})
            MERGE (e:Episode {episode_id: $episode_id})
            SET e.title        = $title,
                e.number       = $number,
                e.publish_date = date($publish_date),
                e.summary      = $summary,
                e.audio_url    = $audio_url
            MERGE (p)-[:HAS_EPISODE]->(e)
            """,
            podcast_name=PODCAST["name"],
            **EPISODE,
        )
        logger.info("episode ready: #%s %s", EPISODE["number"], EPISODE["title"])

        # 3) Chunks + CONTAINS relationships (UNWIND = loop over a list in one query)
        session.run(
            """
            MATCH (e:Episode {episode_id: $episode_id})
            UNWIND $chunks AS chunk
            MERGE (c:Chunk {chunk_id: chunk.chunk_id})
            SET c.text            = chunk.text,
                c.timestamp_start = chunk.timestamp_start,
                c.timestamp_end   = chunk.timestamp_end
            MERGE (e)-[:CONTAINS]->(c)
            """,
            episode_id=EPISODE["episode_id"],
            chunks=CHUNKS,
        )
        logger.info("linked %d chunks to episode", len(CHUNKS))

        # 4) Verify counts (WITH chaining demonstrates how Cypher pipelines work)
        counts = session.run(
            """
            MATCH (p:Podcast) WITH count(p) AS podcasts
            MATCH (e:Episode) WITH podcasts, count(e) AS episodes
            MATCH (c:Chunk)   WITH podcasts, episodes, count(c) AS chunks
            RETURN podcasts, episodes, chunks
            """
        ).single()

    logger.info(
        "graph now holds: %d podcast(s), %d episode(s), %d chunk(s)",
        counts["podcasts"], counts["episodes"], counts["chunks"], # type: ignore
    )


if __name__ == "__main__":
    seed()
    Neo4jConnection.close()