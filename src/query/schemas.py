from pydantic import BaseModel


class PodcastOut(BaseModel):
    name: str
    host: str | None = None
    platform_url: str | None = None
    episode_count: int


class ChunkOut(BaseModel):
    chunk_id: str
    text: str
    timestamp_start: int
    timestamp_end: int
    topic: str | None = None
    summary: str | None = None
    turns: list[dict] = []  # who said what: [{speaker, text, start, concepts}]


class RecommendationOut(BaseModel):
    source: str
    target: str
    reason: str
    chunk_id: str
    timestamp: int
    episode_title: str
    podcast: str


class PersonOut(BaseModel):
    name: str
    mentions: int


class PersonTopic(BaseModel):
    concept: str
    category: str | None = None
    mentions: int
    podcasts: list[str]


class Mention(BaseModel):
    podcast: str
    episode_id: str
    episode_title: str
    speaker: str
    concept: str
    timestamp: int
    quote: str


class EpisodeOut(BaseModel):
    episode_id: str
    title: str
    number: int | None = None
    publish_date: str | None = None
    audio_url: str | None = None
    summary: str | None = None
    duration_seconds: int | None = None
    podcast: str
    guests: list[str]
    chunks: list[ChunkOut]


class GuestEpisode(BaseModel):
    podcast: str
    episode_id: str
    episode_title: str
    concepts: list[str]


class GuestOut(BaseModel):
    name: str
    title: str | None = None
    institution: str | None = None
    bio: str | None = None
    podcasts: list[str]
    episodes: list[GuestEpisode]


class ConceptSummary(BaseModel):
    name: str
    category: str | None = None
    mentions: int


class Quote(BaseModel):
    episode_id: str
    episode_title: str
    quote: str
    timestamp_start: int
    score: float | None = None  # only for semantic results


class PodcastQuotes(BaseModel):
    podcast: str
    host: str | None = None
    quotes: list[Quote]


class ConceptOut(BaseModel):
    name: str
    category: str | None = None
    podcasts: list[PodcastQuotes]


class SearchHit(BaseModel):
    chunk_id: str
    text: str
    timestamp_start: int
    episode_id: str
    episode_title: str
    podcast: str | None = None
    guest: str | None = None
    score: float | None = None


class SharedGuest(BaseModel):
    guest: str
    podcasts: list[str]
    episode_count: int


class ConceptReach(BaseModel):
    concept: str
    category: str | None = None
    podcast_count: int
    podcasts: list[str]
    mention_count: int


class BridgeGuest(BaseModel):
    guest: str
    episodes: list[str]


class Question(BaseModel):
    question: str


class Answer(BaseModel):
    question: str
    answer: str
    tool: str
    args: dict
    sources: list
    verified: bool  # verifier agent: every sentence supported by the sources and every cited mm:ss found in them
    verification: dict = {}  # {claims, supported, unsupported: [{text, reason}], bad_timestamps} — answer is untouched
    cached: bool
