"""LLM clients (LangChain ChatOpenAI over Groq's free tier) + the ingestion agents as typed, single-purpose calls.

Groq's free limits are per model, so each agent is pinned to one of three models (see config.py).
Each agent is one prompt with a Pydantic output schema; the LangGraph in src/ingestion/pipeline.py wires them.
"""

import asyncio
import itertools
import json
import re
import time

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.config import settings


def _groq(model: str) -> ChatOpenAI:
    # gpt-oss models "think" ~1000 hidden tokens per call by default; at 8k tokens/min that is the bottleneck
    extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}
    return ChatOpenAI(model=model, api_key=settings.groq_api_key or "unset", temperature=0, model_kwargs=extra,
                      base_url="https://api.groq.com/openai/v1", timeout=120, max_retries=0)  # 429s handled below


reason, fast = _groq(settings.llm_model_reason), _groq(settings.llm_model_fast)
bulk = itertools.cycle([_groq(settings.llm_model_bulk), fast])  # heavy per-chunk calls alternate: 2× the TPM budget


async def _typed(models: tuple[ChatOpenAI, ...], schema, messages):
    """Structured call that survives Groq's free tier: on 429 sleep exactly as long as Groq asks; when a model
    emits invalid JSON (400 json_validate_failed) retry on the next model of the pair."""
    bad_json = 0
    for attempt in range(30):
        model = models[attempt % len(models)]
        try:  # after two schema-mode failures use tool calling, which skips Groq's strict server-side validator
            method = "json_schema" if bad_json < 2 else "function_calling"
            return await model.with_structured_output(schema, method=method).ainvoke(messages)
        except Exception as exc:
            if "429" in str(exc):
                m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(exc))
                await asyncio.sleep(60 * int(m.group(1) or 0) + float(m.group(2)) + 0.5 if m else 5)
            elif "400" in str(exc) and ("json" in str(exc).lower() or "parsed" in str(exc)) and bad_json < 4:
                bad_json += 1
            else:
                raise
    raise RuntimeError(f"{models[0].model_name}: rate limited for too long")


def chat(system: str, user: str, json_mode: bool = False) -> str:
    """Plain sync call (used by the query-time agents). Blocking — use asyncio.to_thread from async code."""
    model = reason.bind(response_format={"type": "json_object"}) if json_mode else reason
    for _ in range(10):
        try:
            return model.invoke([("system", system), ("human", user)]).content
        except Exception as exc:
            if "429" not in str(exc):
                raise
            m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(exc))
            time.sleep(60 * int(m.group(1) or 0) + float(m.group(2)) + 0.5 if m else 5)
    raise RuntimeError("rate limited for too long")


def chat_json(system: str, user: str) -> dict:
    return json.loads(re.sub(r"^```(?:json)?|```$", "", chat(system, user, json_mode=True).strip()))


# ---- typed outputs -----------------------------------------------------------------

class Metadata(BaseModel):
    host: str | None = None
    guest: str | None = None
    summary: str = ""


class Boundaries(BaseModel):
    starts: list[int] = Field(default=[], description="caption indices where a new topic of discussion begins")


class ConceptRef(BaseModel):
    name: str
    category: str = "Other"


class Turn(BaseModel):
    speaker: str = "Unknown"
    text: str
    concepts: list[ConceptRef] = []


class Analysis(BaseModel):
    topic: str = Field(description="3-8 word title of what this passage discusses")
    summary: str = Field(description="2-3 sentence summary of the discussion in this passage")
    turns: list[Turn]


class Recommendation(BaseModel):
    source: str
    target: str
    reason: str


class Recommendations(BaseModel):
    items: list[Recommendation] = []


class Same(BaseModel):
    same: bool


# ---- ingestion agents --------------------------------------------------------------

async def infer_metadata(opening: str) -> Metadata:
    return await _typed((fast, reason), Metadata, [
        ("system", "This is the opening of a podcast episode transcript. Identify the host and the guest "
                   "(null when unsure) and write a one-sentence summary of the episode."),
        ("human", opening)])


async def find_boundaries(numbered_captions: str) -> list[int]:
    """Semantic chunking: where does the discussion change topic? Returns caption indices."""
    out = await _typed((reason, fast), Boundaries, [
        ("system", "You get numbered caption lines from a podcast. Split them into coherent discussion topics: "
                   "return the indices of the lines where a NEW topic begins (not the first line). Aim for topics "
                   "of roughly 1-3 minutes of talk; never split mid-thought."),
        ("human", numbered_captions)])
    return out.starts


async def analyse(text: str, participants: list[str], known: list[str]) -> Analysis:
    """Topic + summary + speaker turns + concept candidates for one chunk, in one read of the text."""
    return await _typed((next(bulk), next(bulk)), Analysis, [
        ("system", "You get one topic-coherent passage of a podcast transcript (auto captions, no speaker labels) "
                   "and its participants. Return its topic, a summary, and the passage split into speaker turns.\n"
                   "- speaker: exactly one participant name (the host usually asks, the guest answers); "
                   "'Unknown' only if impossible.\n"
                   "- text: that turn's words verbatim and in order; together the turns must cover the passage.\n"
                   "- concepts: 0-3 per turn. name: a short, general, reusable Title Case term ('Open Source', "
                   "'Hiring', 'AI Agents'), singular, no parentheses. category: ONE word (Technology, Career, "
                   "Business, Skill, Tool, Company, ...).\n"
                   f"Reuse these existing concept names when they fit: {', '.join(known)}"),
        ("human", f"Participants: {', '.join(participants)}\n\n{text}")])


async def same_concept(a: str, b: str) -> bool:
    out = await _typed((fast, reason), Same, [
        ("system", "Do these two podcast-topic labels denote the same concept (one would be a duplicate of the "
                   "other in a topic index)? Be strict: 'Pull Requests' = 'Pull Request', but 'AI' != 'AI Agents'."),
        ("human", f"A: {a}\nB: {b}")])
    return out.same


async def recommend(summary: str, concepts: list[str]) -> list[Recommendation]:
    """Which of this passage's concepts does the speaker recommend FOR another of its concepts?"""
    out = await _typed((reason, fast), Recommendations, [
        ("system", "From this podcast passage summary, list recommendations the speakers make of the form "
                   "'<source> helps/is advised for <target>', using ONLY the given concept names for source and "
                   "target. Give a one-sentence reason quoting the gist. Return an empty list if none."),
        ("human", f"Concepts: {', '.join(concepts)}\n\nSummary: {summary}")])
    return [r for r in out.items if r.source in concepts and r.target in concepts and r.source != r.target]
