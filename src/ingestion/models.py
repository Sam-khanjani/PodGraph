"""Data contracts between pipeline stages (what a Kafka message would carry)."""

from pydantic import BaseModel


class Segment(BaseModel):
    text: str
    start: float  # seconds
    duration: float


class Transcript(BaseModel):
    podcast_name: str
    podcast_host: str | None = None
    episode_id: str
    episode_title: str
    episode_number: int | None = None
    publish_date: str | None = None  # ISO YYYY-MM-DD
    audio_url: str | None = None
    guest_name: str | None = None
    summary: str | None = None
    segments: list[Segment]


class Chunk(BaseModel):
    """Mirrors the Chunk node in the graph."""

    chunk_id: str
    episode_id: str
    text: str
    timestamp_start: int
    timestamp_end: int
    embedding: list[float] | None = None
    segments: list[Segment] = []  # the captions it was built from (for turn timestamps; not stored)
    turns: list[dict] = []  # [{"speaker", "text", "start", "concepts": [{"name", "category"}]}], from the LLM
