"""
Seed the graph with podcasts, episodes, chunks, guests, and concepts,
plus all the relationships between them.

Run from the repo root:
    poetry run python -m src.setup.sample_data

Idempotent: every write uses MERGE, so re-running never creates duplicates.
This is hand-labeled sample data.

NOTE: episode numbers/dates/URLs are ILLUSTRATIVE sample values, not real metadata.
"""

import logging

from src.query.db import Neo4jConnection

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# DATA  (plain Python — easy to read, edit, and later generate)
# --------------------------------------------------------------------------

PODCASTS = [
    {"name": "Huberman Lab", "host": "Andrew Huberman",
     "platform_url": "https://hubermanlab.com"},
    {"name": "The Peter Attia Drive", "host": "Peter Attia",
     "platform_url": "https://peterattiamd.com"},
]

GUESTS = [
    {"name": "Matthew Walker",
     "title": "Professor of Neuroscience and Psychology",
     "institution": "UC Berkeley",
     "bio": "Sleep scientist studying the role of sleep in brain and body health."},
]

# Controlled vocabulary for `category` (extends the doc's five — see notes).
CONCEPTS = [
    {"name": "Sleep",            "category": "Physiology"},
    {"name": "Memory",           "category": "Physiology"},
    {"name": "Circadian Rhythm", "category": "Physiology"},
    {"name": "Melatonin",        "category": "Supplement"},
    {"name": "Magnesium",        "category": "Supplement"},
]

# `episode_id` is the key; `podcast_name` links it; `guest` is optional (None = solo).
EPISODES = [
    {"episode_id": "huberman-31", "podcast_name": "Huberman Lab",
     "title": "Using Sleep to Learn, Remember, and Recover",
     "number": 31, "publish_date": "2021-08-02",
     "summary": "How sleep stages support learning, memory, and physical recovery.",
     "audio_url": "https://hubermanlab.com/episode-31",
     "guest": None},

    {"episode_id": "huberman-walker-sleep", "podcast_name": "Huberman Lab",
     "title": "Dr. Matthew Walker: The Biology of Sleep",
     "number": 720, "publish_date": "2024-01-15",  # illustrative sample value
     "summary": "A conversation on the science of sleep and its effects on the brain.",
     "audio_url": "https://hubermanlab.com/matthew-walker-sleep",
     "guest": "Matthew Walker"},

    {"episode_id": "attia-walker-sleep", "podcast_name": "The Peter Attia Drive",
     "title": "Sleep, Longevity, and the Brain with Matthew Walker",
     "number": 261, "publish_date": "2023-05-08",  # illustrative sample value
     "summary": "Linking sleep quality to long-term metabolic and cognitive health.",
     "audio_url": "https://peterattiamd.com/matthew-walker-sleep",
     "guest": "Matthew Walker"},
]

# Each chunk carries the list of concepts it mentions (hand-labeled for now).
CHUNKS = [
    # --- huberman-31: the ORIGINAL five from Week 2 (keep exactly five) ---
    {"chunk_id": "huberman-31-0001", "episode_id": "huberman-31",
     "text": "Sleep is the foundation of mental and physical health. Each night we "
             "cycle through stages that each serve a different purpose.",
     "timestamp_start": 0, "timestamp_end": 45, "concepts": ["Sleep"]},
    {"chunk_id": "huberman-31-0002", "episode_id": "huberman-31",
     "text": "REM sleep is strongly associated with emotional processing and the "
             "consolidation of certain kinds of memory.",
     "timestamp_start": 45, "timestamp_end": 95, "concepts": ["Sleep", "Memory"]},
    {"chunk_id": "huberman-31-0003", "episode_id": "huberman-31",
     "text": "Slow-wave deep sleep is when much of the body's physical restoration "
             "happens and metabolic byproducts are cleared from the brain.",
     "timestamp_start": 95, "timestamp_end": 150, "concepts": ["Sleep"]},
    {"chunk_id": "huberman-31-0004", "episode_id": "huberman-31",
     "text": "Getting sunlight in your eyes early in the day anchors your circadian "
             "rhythm, which improves the quality of sleep that night.",
     "timestamp_start": 150, "timestamp_end": 210, "concepts": ["Circadian Rhythm", "Sleep"]},
    {"chunk_id": "huberman-31-0005", "episode_id": "huberman-31",
     "text": "Avoiding bright artificial light late at night protects melatonin "
             "release and makes it easier to fall asleep.",
     "timestamp_start": 210, "timestamp_end": 260, "concepts": ["Melatonin", "Sleep"]},

    # --- huberman-walker-sleep ---
    {"chunk_id": "huberman-walker-0001", "episode_id": "huberman-walker-sleep",
     "text": "Matthew Walker explains that deep non-REM sleep plays a central role in "
             "consolidating memories and restoring the brain.",
     "timestamp_start": 0, "timestamp_end": 70, "concepts": ["Sleep", "Memory"]},
    {"chunk_id": "huberman-walker-0002", "episode_id": "huberman-walker-sleep",
     "text": "Walker and Huberman discuss how magnesium is sometimes used to support "
             "sleep onset, while noting that responses vary between individuals.",
     "timestamp_start": 70, "timestamp_end": 130, "concepts": ["Magnesium", "Sleep"]},

    # --- attia-walker-sleep ---
    {"chunk_id": "attia-walker-0001", "episode_id": "attia-walker-sleep",
     "text": "Peter Attia and Matthew Walker connect chronic short sleep to long-term "
             "risks for metabolic and cognitive health.",
     "timestamp_start": 0, "timestamp_end": 80, "concepts": ["Sleep"]},
    {"chunk_id": "attia-walker-0002", "episode_id": "attia-walker-sleep",
     "text": "They note that magnesium supplementation is sometimes used to improve "
             "sleep quality, though the evidence is mixed.",
     "timestamp_start": 80, "timestamp_end": 140, "concepts": ["Magnesium", "Sleep"]},
]


# --------------------------------------------------------------------------
# LOADING LOGIC  (a few UNWIND queries — data goes in, logic stays generic)
# --------------------------------------------------------------------------

def seed() -> None:
    driver = Neo4jConnection.get_driver()

    with driver.session() as session:
        # Podcasts
        session.run(
            """
            UNWIND $rows AS row
            MERGE (p:Podcast {name: row.name})
            SET p.host = row.host, p.platform_url = row.platform_url
            """,
            rows=PODCASTS,
        )
        logger.info("podcasts: %d", len(PODCASTS))

        # Guests
        session.run(
            """
            UNWIND $rows AS row
            MERGE (g:Guest {name: row.name})
            SET g.title = row.title, g.institution = row.institution, g.bio = row.bio
            """,
            rows=GUESTS,
        )
        logger.info("guests: %d", len(GUESTS))

        # Concepts
        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Concept {name: row.name})
            SET c.category = row.category
            """,
            rows=CONCEPTS,
        )
        logger.info("concepts: %d", len(CONCEPTS))

        # Episodes + HAS_EPISODE
        session.run(
            """
            UNWIND $rows AS row
            MATCH (p:Podcast {name: row.podcast_name})
            MERGE (e:Episode {episode_id: row.episode_id})
            SET e.title        = row.title,
                e.number       = row.number,
                e.publish_date = date(row.publish_date),
                e.summary      = row.summary,
                e.audio_url    = row.audio_url
            MERGE (p)-[:HAS_EPISODE]->(e)
            """,
            rows=EPISODES,
        )
        logger.info("episodes + HAS_EPISODE: %d", len(EPISODES))

        # APPEARED_IN (only episodes that actually have a guest)
        session.run(
            """
            UNWIND $rows AS row
            WITH row WHERE row.guest IS NOT NULL
            MATCH (e:Episode {episode_id: row.episode_id})
            MATCH (g:Guest {name: row.guest})
            MERGE (g)-[:APPEARED_IN]->(e)
            """,
            rows=EPISODES,
        )
        logger.info("APPEARED_IN relationships created")

        # Chunks + CONTAINS
        session.run(
            """
            UNWIND $rows AS row
            MATCH (e:Episode {episode_id: row.episode_id})
            MERGE (c:Chunk {chunk_id: row.chunk_id})
            SET c.text            = row.text,
                c.timestamp_start = row.timestamp_start,
                c.timestamp_end   = row.timestamp_end
            MERGE (e)-[:CONTAINS]->(c)
            """,
            rows=CHUNKS,
        )
        logger.info("chunks + CONTAINS: %d", len(CHUNKS))

        # MENTIONS — nested UNWIND over each chunk's concept list
        session.run(
            """
            UNWIND $rows AS row
            UNWIND row.concepts AS concept_name
            MATCH (c:Chunk {chunk_id: row.chunk_id})
            MATCH (concept:Concept {name: concept_name})
            MERGE (c)-[:MENTIONS]->(concept)
            """,
            rows=CHUNKS,
        )
        logger.info("MENTIONS relationships created")

        # Verify
        counts = session.run(
            """
            MATCH (p:Podcast)   WITH count(p) AS podcasts
            MATCH (e:Episode)   WITH podcasts, count(e) AS episodes
            MATCH (c:Chunk)     WITH podcasts, episodes, count(c) AS chunks
            MATCH (g:Guest)     WITH podcasts, episodes, chunks, count(g) AS guests
            MATCH (con:Concept) WITH podcasts, episodes, chunks, guests, count(con) AS concepts
            RETURN podcasts, episodes, chunks, guests, concepts
            """
        ).single()

    logger.info(
        "graph now holds: %d podcasts, %d episodes, %d chunks, %d guests, %d concepts",
        counts["podcasts"], counts["episodes"], counts["chunks"], # type: ignore
        counts["guests"], counts["concepts"], # type: ignore
    )


if __name__ == "__main__":
    seed()
    Neo4jConnection.close()