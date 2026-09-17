"""Chunk objects -> Neo4j. Idempotent (MERGE on deterministic keys) and self-healing (prunes stale chunks)."""

import json
import logging

from src.ingestion.models import Chunk, Transcript
from src.query.db import run

log = logging.getLogger(__name__)


def write(t: Transcript, chunks: list[Chunk]) -> dict:
    run("MERGE (p:Podcast {name: $name}) SET p.host = coalesce($host, p.host)",
        name=t.podcast_name, host=t.podcast_host)
    run("""
        MATCH (p:Podcast {name: $podcast_name})
        MERGE (e:Episode {episode_id: $episode_id})
        SET e.title = $episode_title,
            e.audio_url = coalesce($audio_url, e.audio_url),
            e.summary = coalesce($summary, e.summary),
            e.number = coalesce($episode_number, e.number),
            e.publish_date = coalesce(date($publish_date), e.publish_date),
            e.duration_seconds = $duration
        MERGE (p)-[:HAS_EPISODE]->(e)
        """, duration=max((c.timestamp_end for c in chunks), default=0), **t.model_dump(exclude={"segments", "guest_name"}))
    if t.guest_name:
        run("""
            MATCH (e:Episode {episode_id: $episode_id})
            MERGE (g:Guest {name: $guest}) MERGE (g)-[:APPEARED_IN]->(e)
            """, episode_id=t.episode_id, guest=t.guest_name)
    if any(c.turns for c in chunks):  # re-analysis replaces old speaker/concept tags; --no-llm leaves them alone
        run("""
            MATCH (:Episode {episode_id: $episode_id})-[:CONTAINS]->(:Chunk)-[m:MENTIONS]->() DELETE m
            WITH count(*) AS _ MATCH (k:Concept) WHERE NOT (k)<-[:MENTIONS]-() DELETE k
            """, episode_id=t.episode_id)
    run("""
        MATCH (e:Episode {episode_id: $episode_id})
        UNWIND $chunks AS ch
        MERGE (c:Chunk {chunk_id: ch.chunk_id})
        SET c.text = ch.text, c.timestamp_start = ch.timestamp_start, c.timestamp_end = ch.timestamp_end,
            c.embedding = ch.embedding, c.turns = coalesce(ch.turns_json, c.turns)
        MERGE (e)-[:CONTAINS]->(c)
        WITH c, ch UNWIND ch.turns AS t UNWIND t.concepts AS con
        MERGE (k:Concept {name: con.name}) ON CREATE SET k.category = con.category
        MERGE (c)-[m:MENTIONS {speaker: t.speaker}]->(k) SET m.start = t.start, m.quote = left(t.text, 300)
        """, episode_id=t.episode_id,
        chunks=[{**c.model_dump(exclude={"segments"}), "turns_json": json.dumps(c.turns) if c.turns else None}
                for c in chunks])
    run("""
        MATCH (:Episode {episode_id: $episode_id})-[:CONTAINS]->(c:Chunk)
        WHERE NOT c.chunk_id IN $ids DETACH DELETE c
        """, episode_id=t.episode_id, ids=[c.chunk_id for c in chunks])

    run("MATCH (a:CachedAnswer) DELETE a")  # new evidence invalidates old answers
    result = {"episode_id": t.episode_id, "chunks": len(chunks), "status": "success"}
    record_run(**result)
    log.info("wrote %s", result)
    return result


def record_run(status: str, episode_id: str | None = None, chunks: int = 0, reason: str = "") -> None:
    """Append-only audit trail (CREATE, not MERGE): one IngestRun node per run."""
    run("""
        CREATE (r:IngestRun {run_at: datetime(), status: $status, episode_id: $episode_id,
                             chunks: $chunks, reason: $reason})
        WITH r MATCH (e:Episode {episode_id: $episode_id}) CREATE (r)-[:INGESTED]->(e)
        """, status=status, episode_id=episode_id, chunks=chunks, reason=reason[:500])
