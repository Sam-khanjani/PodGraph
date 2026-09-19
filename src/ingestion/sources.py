import json
import logging
import time
from pathlib import Path

import requests

from src.ingestion.models import Segment, Transcript

log = logging.getLogger(__name__)


def from_file(path: str | Path) -> Transcript:
    return Transcript.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def from_youtube(video_id: str, podcast_name: str, **meta) -> Transcript:
    """Fetch captions (no API key). meta: podcast_host, episode_title, episode_number, publish_date, guest_name."""
    from youtube_transcript_api import YouTubeTranscriptApi

    for attempt in range(3):  # the only flaky (network) step gets retries with backoff
        try:
            raw = YouTubeTranscriptApi().fetch(video_id)
            break
        except Exception as exc:
            if attempt == 2:
                raise
            log.warning("fetch %s failed (%s); retrying", video_id, exc)
            time.sleep(2**attempt)

    title = meta.pop("episode_title", None)
    if not title:
        info = requests.get("https://www.youtube.com/oembed", timeout=10,
                            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"})
        title = info.json()["title"] if info.ok else video_id
    return Transcript(
        podcast_name=podcast_name,
        episode_id=f"yt-{video_id}",
        episode_title=title,
        audio_url=f"https://www.youtube.com/watch?v={video_id}",
        segments=[Segment(text=s.text, start=s.start, duration=s.duration) for s in raw if s.text.strip()],
        **{k: v for k, v in meta.items() if v is not None},
    )
