from src.ingestion.models import Chunk, Segment, Transcript


def chunk(t: Transcript, target: int = 1000) -> list[Chunk]:
    """Group consecutive segments into ~target-char chunks, breaking on segment boundaries.

    Deterministic IDs (episode-0001, ...) are what make re-ingestion idempotent.
    """
    chunks: list[Chunk] = []
    parts: list[Segment] = []

    def flush():
        chunks.append(Chunk(chunk_id=f"{t.episode_id}-{len(chunks) + 1:04d}", episode_id=t.episode_id,
                            text=" ".join(s.text.strip() for s in parts), timestamp_start=int(parts[0].start),
                            timestamp_end=int(parts[-1].start + parts[-1].duration), segments=list(parts)))
        parts.clear()

    for seg in t.segments:
        if not seg.text.strip():
            continue
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
