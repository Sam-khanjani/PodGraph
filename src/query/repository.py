"""All Cypher the API runs. One GraphRepository per request, bound to an async session."""

import json

from neo4j import AsyncSession


class NotFoundError(Exception):
    def __init__(self, entity: str, key: str):
        super().__init__(f"{entity} '{key}' not found")


class GraphRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _rows(self, query: str, **params) -> list[dict]:
        return await (await self.session.run(query, **params)).data()

    async def _one(self, entity: str, key: str, query: str, **params) -> dict:
        rows = await self._rows(query, **params)
        if not rows:
            raise NotFoundError(entity, key)
        return rows[0]

    # ---- entities ------------------------------------------------------------------

    async def list_podcasts(self):
        return await self._rows("""
            MATCH (p:Podcast) OPTIONAL MATCH (p)-[:HAS_EPISODE]->(e)
            RETURN p.name AS name, p.host AS host, p.platform_url AS platform_url, count(e) AS episode_count
            ORDER BY name""")

    async def get_episode(self, episode_id: str):
        ep = await self._one("Episode", episode_id, """
            MATCH (p:Podcast)-[:HAS_EPISODE]->(e:Episode {episode_id: $id})
            OPTIONAL MATCH (g:Guest)-[:APPEARED_IN]->(e)
            OPTIONAL MATCH (e)-[:CONTAINS]->(c:Chunk)
            WITH e, p, collect(DISTINCT g.name) AS guests, c ORDER BY c.timestamp_start
            WITH e, p, guests, collect(c {.chunk_id, .text, .timestamp_start, .timestamp_end, .topic, .summary, .turns}) AS chunks
            RETURN e.episode_id AS episode_id, e.title AS title, e.number AS number,
                   toString(e.publish_date) AS publish_date, e.audio_url AS audio_url,
                   e.summary AS summary, e.duration_seconds AS duration_seconds,
                   p.name AS podcast, guests, chunks""", id=episode_id)
        for c in ep["chunks"]:
            c["turns"] = json.loads(c["turns"] or "[]")  # stored as a JSON string (Neo4j has no list-of-map property)
        return ep

    async def get_guest(self, name: str):
        return await self._one("Guest", name, """
            MATCH (g:Guest) WHERE toLower(g.name) = toLower($name)
            OPTIONAL MATCH (g)-[:APPEARED_IN]->(e:Episode)<-[:HAS_EPISODE]-(p:Podcast)
            OPTIONAL MATCH (e)-[:CONTAINS]->(:Chunk)-[:MENTIONS]->(k:Concept)
            WITH g, p, e, collect(DISTINCT k.name) AS concepts
            WITH g, collect(DISTINCT p.name) AS podcasts,
                 collect(CASE WHEN e IS NULL THEN null ELSE
                   {podcast: p.name, episode_id: e.episode_id, episode_title: e.title, concepts: concepts} END) AS episodes
            RETURN g.name AS name, g.title AS title, g.institution AS institution, g.bio AS bio,
                   podcasts, episodes""", name=name)

    async def list_concepts(self, category: str | None, limit: int, offset: int):
        return await self._rows("""
            MATCH (k:Concept) WHERE $category IS NULL OR k.category = $category
            OPTIONAL MATCH (k)<-[:MENTIONS]-(c:Chunk)
            RETURN k.name AS name, k.category AS category, count(c) AS mentions
            ORDER BY mentions DESC, name SKIP $offset LIMIT $limit""",
            category=category, offset=offset, limit=limit)

    async def get_concept(self, name: str):
        """What each show says about a concept — quotes grouped by podcast."""
        return await self._one("Concept", name, """
            MATCH (k:Concept) WHERE toLower(k.name) = toLower($name)
            OPTIONAL MATCH (k)<-[:MENTIONS]-(c:Chunk)<-[:CONTAINS]-(e:Episode)<-[:HAS_EPISODE]-(p:Podcast)
            WITH k, p, c, e ORDER BY c.timestamp_start
            WITH k, p, collect({episode_id: e.episode_id, episode_title: e.title,
                                quote: c.text, timestamp_start: c.timestamp_start}) AS quotes
            WITH k, collect(CASE WHEN p IS NULL THEN null ELSE
                   {podcast: p.name, host: p.host, quotes: quotes} END) AS podcasts
            RETURN k.name AS name, k.category AS category, podcasts""", name=name)

    async def concept_recommendations(self, name: str):
        """What a concept is recommended for / by, with the passage that said so."""
        return await self._rows("""
            MATCH (a:Concept)-[r:RECOMMENDS]->(b:Concept)
            WHERE toLower(a.name) = toLower($name) OR toLower(b.name) = toLower($name)
            MATCH (p:Podcast)-[:HAS_EPISODE]->(e:Episode)-[:CONTAINS]->(c:Chunk {chunk_id: r.chunk_id})
            RETURN a.name AS source, b.name AS target, r.reason AS reason, c.chunk_id AS chunk_id,
                   c.timestamp_start AS timestamp, e.title AS episode_title, p.name AS podcast
            ORDER BY podcast, episode_title, timestamp""", name=name)

    # ---- people: who said what ---------------------------------------------------

    async def list_people(self):
        return await self._rows("""
            MATCH ()-[m:MENTIONS]->() RETURN m.speaker AS name, count(m) AS mentions ORDER BY mentions DESC""")

    async def person_topics(self, person: str):
        """What this person talks about, across shows."""
        return await self._rows("""
            MATCH (p:Podcast)-[:HAS_EPISODE]->(:Episode)-[:CONTAINS]->(:Chunk)-[m:MENTIONS]->(k:Concept)
            WHERE toLower(m.speaker) = toLower($person)
            RETURN k.name AS concept, k.category AS category, count(m) AS mentions, collect(DISTINCT p.name) AS podcasts
            ORDER BY mentions DESC, concept""", person=person)

    async def person_mentions(self, person: str, concept: str | None):
        """When and where this person talked about a concept (case-insensitive; either name may contain the other)."""
        return await self._rows("""
            MATCH (p:Podcast)-[:HAS_EPISODE]->(e:Episode)-[:CONTAINS]->(:Chunk)-[m:MENTIONS]->(k:Concept)
            WHERE toLower(m.speaker) CONTAINS toLower($person)
              AND ($concept IS NULL OR toLower(k.name) CONTAINS toLower($concept)
                   OR toLower($concept) CONTAINS toLower(k.name))
            RETURN p.name AS podcast, e.episode_id AS episode_id, e.title AS episode_title, m.speaker AS speaker,
                   k.name AS concept, m.start AS timestamp, m.quote AS quote
            ORDER BY podcast, episode_title, timestamp LIMIT 50""", person=person, concept=concept)

    # ---- search --------------------------------------------------------------------

    async def search_chunks(self, term: str, limit: int, offset: int):
        return await self._rows("""
            MATCH (e:Episode)-[:CONTAINS]->(c:Chunk) WHERE toLower(c.text) CONTAINS toLower($term)
            RETURN e.episode_id AS episode_id, e.title AS episode_title,
                   c.chunk_id AS chunk_id, c.text AS text, c.timestamp_start AS timestamp_start
            ORDER BY e.title, c.timestamp_start SKIP $offset LIMIT $limit""",
            term=term, offset=offset, limit=limit)

    async def semantic_search(self, embedding: list[float], k: int):
        """Vector hit + graph context in ONE query — the GraphRAG core."""
        return await self._rows("""
            CALL db.index.vector.queryNodes('chunk_embedding_index', $k, $embedding) YIELD node AS c, score
            MATCH (p:Podcast)-[:HAS_EPISODE]->(e:Episode)-[:CONTAINS]->(c)
            OPTIONAL MATCH (g:Guest)-[:APPEARED_IN]->(e)
            RETURN c.chunk_id AS chunk_id, c.text AS text, c.timestamp_start AS timestamp_start,
                   e.episode_id AS episode_id, e.title AS episode_title, p.name AS podcast,
                   g.name AS guest, round(score, 4) AS score
            ORDER BY score DESC""", k=k, embedding=embedding)

    async def semantic_compare(self, embedding: list[float], k: int):
        """Semantic hits grouped per podcast: 'what does EACH show say about <any phrasing>?'"""
        return await self._rows("""
            CALL db.index.vector.queryNodes('chunk_embedding_index', $k, $embedding) YIELD node AS c, score
            MATCH (p:Podcast)-[:HAS_EPISODE]->(e:Episode)-[:CONTAINS]->(c)
            WITH p, e, c, score ORDER BY score DESC
            WITH p, collect({episode_id: e.episode_id, episode_title: e.title, quote: c.text,
                             timestamp_start: c.timestamp_start, score: round(score, 4)})[..3] AS quotes
            RETURN p.name AS podcast, quotes ORDER BY podcast""", k=k, embedding=embedding)

    # ---- insights (the queries that justify the graph) ----------------------------

    async def shared_guests(self):
        return await self._rows("""
            MATCH (g:Guest)-[:APPEARED_IN]->(e:Episode)<-[:HAS_EPISODE]-(p:Podcast)
            WITH g, collect(DISTINCT p.name) AS podcasts, count(DISTINCT e) AS episode_count
            WHERE size(podcasts) >= 2
            RETURN g.name AS guest, podcasts, episode_count ORDER BY episode_count DESC""")

    async def concept_reach(self, min_podcasts: int, limit: int):
        return await self._rows("""
            MATCH (k:Concept)<-[:MENTIONS]-(c:Chunk)<-[:CONTAINS]-(:Episode)<-[:HAS_EPISODE]-(p:Podcast)
            WITH k, collect(DISTINCT p.name) AS podcasts, count(c) AS mention_count
            WHERE size(podcasts) >= $min
            RETURN k.name AS concept, k.category AS category, size(podcasts) AS podcast_count,
                   podcasts, mention_count
            ORDER BY podcast_count DESC, mention_count DESC LIMIT $limit""", min=min_podcasts, limit=limit)

    async def bridge_guests(self, a: str, b: str):
        return await self._rows("""
            MATCH (ka:Concept) WHERE toLower(ka.name) = toLower($a)
            MATCH (kb:Concept) WHERE toLower(kb.name) = toLower($b)
            MATCH (g:Guest)-[:APPEARED_IN]->(e:Episode)
            WHERE (e)-[:CONTAINS]->(:Chunk)-[:MENTIONS]->(ka) AND (e)-[:CONTAINS]->(:Chunk)-[:MENTIONS]->(kb)
            RETURN g.name AS guest, collect(DISTINCT e.title) AS episodes""", a=a, b=b)

    # ---- agent support -------------------------------------------------------------

    async def read_cypher(self, query: str):
        """Run LLM-written Cypher inside a read transaction (writes are rejected by the DB)."""
        async def work(tx):
            return await (await tx.run(query)).data()

        return await self.session.execute_read(work)

    async def get_cached(self, question: str):
        rows = await self._rows("""
            MATCH (a:CachedAnswer {key: toLower(trim($q))})
            RETURN a.question AS question, a.answer AS answer, a.tool AS tool,
                   a.args AS args, a.sources AS sources, a.verified AS verified, a.verification AS verification""",
                                q=question)
        return rows and {**rows[0], "verified": bool(rows[0]["verified"]),
                         **{k: json.loads(rows[0][k] or "{}") for k in ("args", "sources", "verification")}}

    async def cache(self, result: dict):
        await self._rows("""
            MERGE (a:CachedAnswer {key: toLower(trim($question))})
            SET a.question = $question, a.answer = $answer, a.tool = $tool, a.args = $args, a.sources = $sources,
                a.verified = $verified, a.verification = $verification, a.created_at = datetime()""",
            **{**result, **{k: json.dumps(result[k], default=str) for k in ("args", "sources", "verification")}})
