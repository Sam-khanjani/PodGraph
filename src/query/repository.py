from neo4j import AsyncSession


class NotFoundError(Exception):
    """Raised when a requested entity doesn't exist. Mapped to HTTP 404 by api.py."""

    def __init__(self, entity: str, key: str) -> None:
        self.entity = entity
        self.key = key
        super().__init__(f"{entity} '{key}' not found")


class GraphRepository:
    """All Neo4j reads for the API. One instance per request (bound to a session)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_podcasts(self) -> list[dict]:
        result = await self.session.run(
            """
            MATCH (p:Podcast)
            OPTIONAL MATCH (p)-[:HAS_EPISODE]->(e:Episode)
            RETURN p.name AS name, p.host AS host,
                   p.platform_url AS platform_url,
                   count(e) AS episode_count
            ORDER BY name
            """
        )
        return await result.data()

    async def get_episode(self, episode_id: str) -> dict:
        result = await self.session.run(
            """
            MATCH (p:Podcast)-[:HAS_EPISODE]->(e:Episode {episode_id: $episode_id})
            OPTIONAL MATCH (g:Guest)-[:APPEARED_IN]->(e)
            OPTIONAL MATCH (e)-[:CONTAINS]->(c:Chunk)
            WITH e, p, collect(DISTINCT g) AS guests, collect(DISTINCT c) AS chunks
            RETURN e.episode_id AS episode_id, e.title AS title, e.number AS number,
                   toString(e.publish_date) AS publish_date,
                   e.summary AS summary, e.audio_url AS audio_url,
                   p.name AS podcast,
                   [g IN guests | {name: g.name, title: g.title,
                                   institution: g.institution, bio: g.bio}] AS guests,
                   [c IN chunks | {chunk_id: c.chunk_id, text: c.text,
                                   timestamp_start: c.timestamp_start,
                                   timestamp_end: c.timestamp_end}] AS chunks
            """,
            episode_id=episode_id,
        )
        record = await result.single()
        if record is None:
            raise NotFoundError("Episode", episode_id)
        data = record.data()
        data["chunks"].sort(key=lambda c: c["timestamp_start"])
        return data

    async def list_concepts(self, category: str | None, limit: int, offset: int) -> list[dict]:
        result = await self.session.run(
            """
            MATCH (c:Concept)
            WHERE $category IS NULL OR c.category = $category
            OPTIONAL MATCH (c)<-[:MENTIONS]-(chunk:Chunk)
            WITH c, count(chunk) AS mentions
            RETURN c.name AS name, c.category AS category, mentions
            ORDER BY mentions DESC, name
            SKIP $offset LIMIT $limit
            """,
            category=category, offset=offset, limit=limit,
        )
        return await result.data()

    async def get_concept(self, name: str) -> dict:
        # 1) Resolve the concept (case-insensitive) — 404 if it doesn't exist.
        result = await self.session.run(
            "MATCH (c:Concept) WHERE toLower(c.name) = toLower($name) "
            "RETURN c.name AS name, c.category AS category",
            name=name,
        )
        meta = await result.single()
        if meta is None:
            raise NotFoundError("Concept", name)

        # 2) Flat mentions across all podcasts.
        result = await self.session.run(
            """
            MATCH (c:Concept {name: $canonical})<-[:MENTIONS]-(chunk:Chunk)
                  <-[:CONTAINS]-(e:Episode)<-[:HAS_EPISODE]-(p:Podcast)
            RETURN p.name AS podcast, p.host AS host,
                   e.episode_id AS episode_id, e.title AS episode_title,
                   chunk.text AS quote, chunk.timestamp_start AS timestamp_start
            ORDER BY p.name, chunk.timestamp_start
            """,
            canonical=meta["name"],
        )
        rows = await result.data()

        # 3) Group by podcast in Python (clearer than nested Cypher aggregation).
        grouped: dict[str, dict] = {}
        for row in rows:
            bucket = grouped.setdefault(
                row["podcast"],
                {"podcast": row["podcast"], "host": row["host"], "quotes": []},
            )
            bucket["quotes"].append({
                "episode_id": row["episode_id"],
                "episode_title": row["episode_title"],
                "quote": row["quote"],
                "timestamp_start": row["timestamp_start"],
            })

        return {"name": meta["name"], "category": meta["category"],
                "podcasts": list(grouped.values())}

    async def get_guest(self, name: str) -> dict:
        result = await self.session.run(
            "MATCH (g:Guest) WHERE toLower(g.name) = toLower($name) "
            "RETURN g.name AS name, g.title AS title, "
            "g.institution AS institution, g.bio AS bio",
            name=name,
        )
        meta = await result.single()
        if meta is None:
            raise NotFoundError("Guest", name)

        result = await self.session.run(
            """
            MATCH (g:Guest {name: $canonical})-[:APPEARED_IN]->(e:Episode)
                  <-[:HAS_EPISODE]-(p:Podcast)
            OPTIONAL MATCH (e)-[:CONTAINS]->(:Chunk)-[:MENTIONS]->(con:Concept)
            WITH p, e, collect(DISTINCT con.name) AS concepts
            RETURN p.name AS podcast, e.episode_id AS episode_id,
                   e.title AS episode_title, concepts
            ORDER BY p.name, e.title
            """,
            canonical=meta["name"],
        )
        episodes = await result.data()
        podcasts = sorted({ep["podcast"] for ep in episodes})
        concepts = sorted({c for ep in episodes for c in ep["concepts"]})
        return {**meta.data(), "podcasts": podcasts,
                "episodes": episodes, "concepts": concepts}

    async def search_chunks(self, term: str, limit: int, offset: int) -> list[dict]:
        result = await self.session.run(
            """
            MATCH (e:Episode)-[:CONTAINS]->(c:Chunk)
            WHERE toLower(c.text) CONTAINS toLower($term)
            RETURN e.episode_id AS episode_id, e.title AS episode_title,
                   c.chunk_id AS chunk_id, c.text AS text,
                   c.timestamp_start AS timestamp_start
            ORDER BY e.title, c.timestamp_start
            SKIP $offset LIMIT $limit
            """,
            term=term, offset=offset, limit=limit,
        )
        return await result.data()