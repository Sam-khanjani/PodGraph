"""Ingestion as a LangGraph: one node per agent, a Transcript in, a written episode out.

    segment ─▶ embed ─▶ analyse ─▶ resolve_concepts ─▶ recommend ─▶ write        (--no-llm: segment ─▶ embed ─▶ write)

    python -m src.ingestion.pipeline youtube VIDEO_ID --podcast "Beyond Coding"   # also saves data/transcripts/<id>.json
    python -m src.ingestion.pipeline file data/transcripts/*.json                 # offline, reproducible
    python -m src.ingestion.pipeline --no-llm file ...                            # fixed-size chunks, no LLM
    python -m src.ingestion.pipeline backfill                                     # embed chunks/concepts that lack vectors
"""

import argparse
import asyncio
import glob
import logging
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents import llm as agents
from src.config import settings
from src.ingestion import sources
from src.ingestion.chunker import chunk, chunks_from_ranges, timestamp_turns
from src.ingestion.embedder import embed
from src.ingestion.graph_writer import record_run, write
from src.ingestion.models import Chunk, Transcript
from src.query.db import close, run

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
log = logging.getLogger(__name__)

TRANSCRIPTS = Path("data/transcripts")
WINDOW_CHARS = 8000   # captions sent per boundary-detection call
PARALLEL = asyncio.Semaphore(settings.llm_parallel)


class State(TypedDict, total=False):
    t: Transcript
    llm: bool
    chunks: list[Chunk]
    result: dict


async def _each(items, fn):
    """Run fn over items concurrently, at most PARALLEL at a time."""
    async def guarded(x):
        async with PARALLEL:
            return await fn(x)
    return await asyncio.gather(*(guarded(x) for x in items))


# ---- nodes -----------------------------------------------------------------------------

async def segment(s: State) -> State:
    """Semantic chunking: an LLM marks topic changes in windows of numbered captions."""
    t = s["t"]
    if not s["llm"]:
        return {"chunks": chunk(t)}
    segs = [x for x in t.segments if x.text.strip()]
    starts, i = {0}, 0
    while i < len(segs):
        n, size = i, 0
        while n < len(segs) and size < WINDOW_CHARS:
            size += len(segs[n].text)
            n += 1
        numbered = "\n".join(f"[{j}] {' '.join(segs[j].text.split())}" for j in range(i, n))
        starts.update(b for b in await agents.find_boundaries(numbered) if i < b < n)
        starts.add(n)
        i = n
    return {"chunks": chunks_from_ranges(t, segs, sorted(starts))}


async def embed_chunks(s: State) -> State:
    for c, vec in zip(s["chunks"], embed([c.text for c in s["chunks"]])):
        c.embedding = vec
    return {}


async def analyse(s: State) -> State:
    """Per chunk: topic, summary, speaker turns with timestamps, concept candidates."""
    t = s["t"]
    if not (t.guest_name and t.podcast_host):
        meta = await agents.infer_metadata(" ".join(x.text for x in t.segments)[:4000])
        t.podcast_host, t.guest_name = t.podcast_host or meta.host, t.guest_name or meta.guest
        t.summary = t.summary or meta.summary
    people = [f"{t.podcast_host or 'Host'} (host)", f"{t.guest_name or 'Guest'} (guest)"]
    known = [r["name"] for r in run("MATCH (k:Concept)<-[:MENTIONS]-(c) WITH k, count(c) AS n "
                                     "ORDER BY n DESC LIMIT 80 RETURN k.name AS name")]

    async def one(c: Chunk):
        a = await agents.analyse(c.text, people, known)
        c.topic, c.summary = a.topic, a.summary
        c.turns = timestamp_turns([t.model_dump() for t in a.turns], c)

    await _each(s["chunks"], one)
    return {"t": t}


async def resolve_concepts(s: State) -> State:
    """Concept bank: map every candidate name onto an existing concept (vector match, LLM-confirmed when
    borderline) or add it to the bank. Sequential, so a concept added now is matched by the next candidate."""
    canon: dict[str, str] = {}
    for c in s["chunks"]:
        for turn in c.turns:
            for con in turn["concepts"]:
                if con["name"] not in canon:
                    canon[con["name"]] = await _resolve(con["name"], con["category"])
                con["name"] = canon[con["name"]]
    merged = {k: v for k, v in canon.items() if k != v}
    log.info("concepts: %d candidates -> %d merged onto existing names %s", len(canon), len(merged), merged or "")
    return {}


async def _resolve(name: str, category: str) -> str:
    vec = embed([name])[0]
    hit = run("CALL db.index.vector.queryNodes('concept_embedding_index', 1, $v) YIELD node, score "
              "RETURN node.name AS name, score", v=vec)
    if hit:
        best, score = hit[0]["name"], hit[0]["score"]
        if best.lower() == name.lower() or score >= 0.92:
            return best
        if score >= 0.80 and await agents.same_concept(name, best):
            return best
    run("MERGE (k:Concept {name: $name}) ON CREATE SET k.category = $category, k.embedding = $v",
        name=name, category=category, v=vec)
    return name


async def recommend(s: State) -> State:
    """Per chunk: RECOMMENDS relations between its (canonical) concepts, with a reason."""
    async def one(c: Chunk):
        names = sorted({con["name"] for turn in c.turns for con in turn["concepts"]})
        recs = await agents.recommend(c.summary, names) if len(names) >= 2 else []
        c.recommendations = [r.model_dump() for r in recs]

    await _each(s["chunks"], one)
    return {}


async def write_graph(s: State) -> State:
    # ---- KAFKA SEAM: a producer would publish `chunks` here; a consumer would call write() ----
    return {"result": write(s["t"], s["chunks"])}


def build() -> StateGraph:
    g = StateGraph(State)
    for name, fn in [("segment", segment), ("embed", embed_chunks), ("analyse", analyse),
                     ("resolve_concepts", resolve_concepts), ("recommend", recommend), ("write", write_graph)]:
        g.add_node(name, fn)
    g.add_edge(START, "segment")
    g.add_edge("segment", "embed")
    g.add_conditional_edges("embed", lambda s: "analyse" if s["llm"] else "write")
    g.add_edge("analyse", "resolve_concepts")
    g.add_edge("resolve_concepts", "recommend")
    g.add_edge("recommend", "write")
    g.add_edge("write", END)
    return g


graph = build().compile()


async def aingest(t: Transcript, llm: bool = True) -> dict:
    try:
        out = await graph.ainvoke({"t": t, "llm": llm, "chunks": []})
    except Exception as exc:
        record_run("failed", t.episode_id, reason=str(exc))
        raise
    log.info("'%s': %d segments -> %d chunks (guest=%s)", t.episode_id, len(t.segments), len(out["chunks"]), t.guest_name)
    return out["result"]


def ingest(t: Transcript, llm: bool = True) -> dict:
    """Sync convenience for tests/scripts. The CLI keeps ONE event loop (the async LLM client is bound to it)."""
    return asyncio.run(aingest(t, llm))


def save(t: Transcript) -> None:
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    (TRANSCRIPTS / f"{t.episode_id}.json").write_text(t.model_dump_json(indent=1, exclude_none=True), encoding="utf-8")


def backfill() -> int:
    """Embed every chunk and concept that has no vector yet (idempotent)."""
    n = 0
    for label, key in (("Chunk", "text"), ("Concept", "name")):
        rows = run(f"MATCH (x:{label}) WHERE x.embedding IS NULL RETURN elementId(x) AS id, x.{key} AS text")
        if rows:
            run(f"UNWIND $rows AS r MATCH (x:{label}) WHERE elementId(x) = r.id SET x.embedding = r.embedding",
                rows=[{"id": r["id"], "embedding": v} for r, v in zip(rows, embed([r["text"] for r in rows]))])
        n += len(rows)
    log.info("backfilled %d nodes", n)
    return n


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-llm", action="store_true", help="fixed-size chunks; skip all LLM agents")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("file").add_argument("paths", nargs="+", help="transcript JSON file(s) or globs")
    yt = sub.add_parser("youtube")
    yt.add_argument("video_id")
    yt.add_argument("--podcast", required=True)
    for flag in ("--title", "--host", "--number", "--date", "--guest"):
        yt.add_argument(flag)
    sub.add_parser("backfill")
    a = p.parse_args()

    async def run_all():
        if a.cmd == "backfill":
            backfill()
        elif a.cmd == "file":
            for path in (f for pattern in a.paths for f in sorted(glob.glob(pattern))):
                await aingest(sources.from_file(path), llm=not a.no_llm)
        else:
            t = sources.from_youtube(a.video_id, a.podcast, episode_title=a.title, podcast_host=a.host,
                                     episode_number=a.number, publish_date=a.date, guest_name=a.guest)
            save(t)  # keep the raw data: reproducible + offline tests (saved again after LLM metadata is filled in)
            await aingest(t, llm=not a.no_llm)
            save(t)

    try:
        asyncio.run(run_all())
    finally:
        close()


if __name__ == "__main__":
    main()
