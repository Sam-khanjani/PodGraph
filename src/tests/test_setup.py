from src.query.db import Neo4jConnection


def test_neo4j_is_reachable():
    assert Neo4jConnection.verify_connection() is True


def test_sample_podcast_exists():
    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        record = session.run(
            "MATCH (p:Podcast {name: $name}) RETURN p.name AS name",
            name="Huberman Lab",
        ).single()
    assert record is not None
    assert record["name"] == "Huberman Lab"


def test_episode_has_chunks():
    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        count = session.run(
            """
            MATCH (:Episode {episode_id: $eid})-[:CONTAINS]->(c:Chunk)
            RETURN count(c) AS n
            """,
            eid="huberman-31",
        ).single()["n"] # type: ignore
    assert count == 5