"""Orchestrator + CLI:  source -> chunk -> embed -> LLM (metadata, speaker turns + concepts) -> write.

    python -m src.ingestion.pipeline youtube VIDEO_ID --podcast "Beyond Coding"   # also saves data/transcripts/<id>.json
    python -m src.ingestion.pipeline file data/transcripts/*.json                 # offline, reproducible
    python -m src.ingestion.pipeline --no-llm file ...                            # skip concept/metadata extraction
    python -m src.ingestion.pipeline backfill                                     # embed chunks that predate embeddings
"""

import argparse
import glob
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.agents.llm import analyse_chunk, infer_metadata
from src.ingestion import sources
from src.ingestion.chunker import chunk, timestamp_turns
from src.ingestion.embedder import embed
from src.ingestion.graph_writer import record_run, write
from src.ingestion.models import Transcript
from src.query.db import close, run

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
log = logging.getLogger(__name__)

TRANSCRIPTS = Path("data/transcripts")


def ingest(t: Transcript, llm: bool = True) -> dict:
    try:
        chunks = chunk(t)
        for c, vec in zip(chunks, embed([c.text for c in chunks])):
            c.embedding = vec
        if llm:
            if not (t.guest_name and t.podcast_host):
                meta = infer_metadata(" ".join(s.text for s in t.segments)[:4000])
                t.podcast_host = t.podcast_host or meta.get("host")
                t.guest_name = t.guest_name or meta.get("guest")
                t.summary = t.summary or meta.get("summary")
            people = [f"{t.podcast_host or 'Host'} (host)", f"{t.guest_name or 'Guest'} (guest)"]
            known = [r["name"] for r in run("MATCH (k:Concept)<-[:MENTIONS]-(c) WITH k, count(c) AS n "
                                             "ORDER BY n DESC LIMIT 80 RETURN k.name AS name")]
            with ThreadPoolExecutor(4) as pool:
                for c, turns in zip(chunks, pool.map(lambda c: analyse_chunk(c.text, people, known), chunks)):
                    c.turns = timestamp_turns(turns, c)
        log.info("'%s': %d segments -> %d chunks (guest=%s)", t.episode_id, len(t.segments), len(chunks), t.guest_name)
        # ---- KAFKA SEAM: a producer would publish `chunks` here; a consumer would call write() ----
        return write(t, chunks)
    except Exception as exc:
        record_run("failed", t.episode_id, reason=str(exc))
        raise


def save(t: Transcript) -> None:
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    (TRANSCRIPTS / f"{t.episode_id}.json").write_text(t.model_dump_json(indent=1, exclude_none=True), encoding="utf-8")


def backfill() -> int:
    """Embed every chunk with no embedding yet (idempotent)."""
    rows = run("MATCH (c:Chunk) WHERE c.embedding IS NULL RETURN c.chunk_id AS id, c.text AS text")
    if rows:
        run("UNWIND $rows AS r MATCH (c:Chunk {chunk_id: r.id}) SET c.embedding = r.embedding",
            rows=[{"id": r["id"], "embedding": v} for r, v in zip(rows, embed([r["text"] for r in rows]))])
    log.info("backfilled %d chunks", len(rows))
    return len(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-llm", action="store_true", help="skip LLM concept + metadata extraction")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("file").add_argument("paths", nargs="+", help="transcript JSON file(s) or globs")
    yt = sub.add_parser("youtube")
    yt.add_argument("video_id")
    yt.add_argument("--podcast", required=True)
    for flag in ("--title", "--host", "--number", "--date", "--guest"):
        yt.add_argument(flag)
    sub.add_parser("backfill")
    a = p.parse_args()

    try:
        if a.cmd == "backfill":
            backfill()
        elif a.cmd == "file":
            for path in (f for pattern in a.paths for f in sorted(glob.glob(pattern))):
                ingest(sources.from_file(path), llm=not a.no_llm)
        else:
            t = sources.from_youtube(a.video_id, a.podcast, episode_title=a.title, podcast_host=a.host,
                                     episode_number=a.number, publish_date=a.date, guest_name=a.guest)
            save(t)  # keep the raw data: reproducible + offline tests (saved again after LLM metadata is filled in)
            ingest(t, llm=not a.no_llm)
            save(t)
    finally:
        close()


if __name__ == "__main__":
    main()
