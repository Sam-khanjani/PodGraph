from src.query.db import Neo4jConnection


def _run(query: str, **params):
    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        return list(session.run(query, **params)) # type: ignore


def test_expected_constraints_exist():
    rows = _run("SHOW CONSTRAINTS")
    # We declared 5 uniqueness constraints in config/neo4j_schema.cypher.
    assert len(rows) >= 5


def test_guest_appears_on_two_podcasts():
    rows = _run(
        """
        MATCH (g:Guest {name: $guest})-[:APPEARED_IN]->(:Episode)
              <-[:HAS_EPISODE]-(p:Podcast)
        RETURN count(DISTINCT p.name) AS podcasts
        """,
        guest="Matthew Walker",
    )
    assert rows[0]["podcasts"] == 2


def test_concept_shared_across_podcasts():
    # "Sleep" must be mentioned by chunks belonging to >= 2 different podcasts.
    rows = _run(
        """
        MATCH (c:Concept {name: $concept})<-[:MENTIONS]-(:Chunk)
              <-[:CONTAINS]-(:Episode)<-[:HAS_EPISODE]-(p:Podcast)
        RETURN count(DISTINCT p.name) AS podcasts
        """,
        concept="Sleep",
    )
    assert rows[0]["podcasts"] >= 2


def test_multihop_guest_to_concepts():
    rows = _run(
        """
        MATCH (g:Guest {name: $guest})-[:APPEARED_IN]->(:Episode)
              -[:CONTAINS]->(:Chunk)-[:MENTIONS]->(c:Concept)
        RETURN collect(DISTINCT c.name) AS concepts
        """,
        guest="Matthew Walker",
    )
    concepts = rows[0]["concepts"]
    assert "Magnesium" in concepts
    assert "Sleep" in concepts


def test_no_orphan_chunks():
    # Every chunk should belong to an episode (catches broken CONTAINS links).
    rows = _run(
        """
        MATCH (c:Chunk)
        WHERE NOT (:Episode)-[:CONTAINS]->(c)
        RETURN count(c) AS orphans
        """
    )
    assert rows[0]["orphans"] == 0