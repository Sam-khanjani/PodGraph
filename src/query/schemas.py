from datetime import date
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class ConceptCategory(str, Enum):
    """Controlled vocabulary for concept categories (matches the seed data)."""
    supplement = "Supplement"
    biomarker = "Biomarker"
    exercise = "Exercise"
    diet = "Diet"
    disease = "Disease"
    physiology = "Physiology"


class PodcastOut(BaseModel):
    model_config = ConfigDict( 
        json_schema_extra={
            "example": {
                "name": "Huberman Lab",
                "host": "Andrew Huberman",
                "platform_url": "https://hubermanlab.com",
                "episode_count": 2,
            }
        }
    )
    name: str
    host: str
    platform_url: str | None = None
    episode_count: int = 0


class GuestOut(BaseModel):
    name: str
    title: str | None = None
    institution: str | None = None
    bio: str | None = None


class ChunkOut(BaseModel):
    chunk_id: str
    text: str
    timestamp_start: int = Field(..., description="Start time in seconds")
    timestamp_end: int = Field(..., description="End time in seconds")


class EpisodeOut(BaseModel):
    episode_id: str
    title: str
    number: int | None = None
    publish_date: date | None = None
    summary: str | None = None
    audio_url: str | None = None
    podcast: str
    guests: list[GuestOut] = []
    chunks: list[ChunkOut] = []


class ConceptSummary(BaseModel):
    name: str
    category: str
    mentions: int = Field(0, description="How many chunks mention this concept")


# --- The cross-podcast "graph power" response, grouped by show ---

class QuoteOut(BaseModel):
    episode_id: str
    episode_title: str
    quote: str
    timestamp_start: int


class PodcastQuotes(BaseModel):
    podcast: str
    host: str
    quotes: list[QuoteOut]


class ConceptDetailOut(BaseModel):
    name: str
    category: str
    podcasts: list[PodcastQuotes] = []


# --- Guest detail (multi-hop) ---

class GuestEpisodeOut(BaseModel):
    podcast: str
    episode_id: str
    episode_title: str
    concepts: list[str] = []


class GuestDetailOut(GuestOut):
    podcasts: list[str] = []
    episodes: list[GuestEpisodeOut] = []
    concepts: list[str] = []


class SearchHit(BaseModel):
    episode_id: str
    episode_title: str
    chunk_id: str
    text: str
    timestamp_start: int