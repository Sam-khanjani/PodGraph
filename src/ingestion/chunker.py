from src.ingestion.models import Chunk, Segment, Transcript

MAX_CHARS = 2500  # a topic longer than this is split on caption boundaries


def chunk(t: Transcript, target: int = 1000) -> list[Chunk]:
    """Fixed-size fallback (no LLM): group consecutive segments into ~target-char chunks on caption boundaries."""
    segs = [x for x in t.segments if x.text.strip()]
    return _pack(t.episode_id, segs, target, start_index=1)


def chunks_from_ranges(t: Transcript, segs: list[Segment], starts: list[int]) -> list[Chunk]:
    """Semantic chunks: `starts` are caption indices where topics begin (first 0, last len(segs)).
    Over-long topics are still split at MAX_CHARS. IDs are positional (episode-0001...) so re-ingest replaces."""
    chunks: list[Chunk] = []
    for a, b in zip(starts, starts[1:]):
        chunks += _pack(t.episode_id, segs[a:b], MAX_CHARS, start_index=len(chunks) + 1)
    return chunks


def _pack(episode_id: str, segs: list[Segment], target: int, start_index: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    parts: list[Segment] = []

    def flush():
        chunks.append(Chunk(chunk_id=f"{episode_id}-{start_index + len(chunks):04d}", episode_id=episode_id,
                            text=" ".join(s.text.strip() for s in parts), timestamp_start=int(parts[0].start),
                            timestamp_end=int(parts[-1].start + parts[-1].duration), segments=list(parts)))
        parts.clear()

    for seg in segs:
        parts.append(seg)
        if sum(len(s.text) for s in parts) >= target:
            flush()
    if parts:
        flush()
    return chunks


def timestamp_turns(turns: list[dict], c: Chunk) -> list[dict]:
    """Give each speaker turn the start time of the caption segment its first words came from."""
    norm = " ".join(c.text.split())
    starts, pos = [], 0
    for s in c.segments:  # char offset of every segment inside the whitespace-normalised chunk text
        starts.append((pos, int(s.start)))
        pos += len(" ".join(s.text.split())) + 1
    for turn in turns:
        i = norm.find(" ".join(turn["text"].split())[:40])
        turn["start"] = c.timestamp_start if i < 0 else max(st for off, st in starts if off <= i)
    return turns
