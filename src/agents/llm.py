"""One LLM call helper (OpenRouter, OpenAI-compatible) + the ingestion-time agents (turns+concepts, metadata)."""

import json
import re
import time

import requests

from src.config import settings

ANALYSE = """You get a passage of a podcast transcript (auto captions, no speaker labels) and its participants.
Split it into speaker turns and tag each turn with the concepts it discusses.
Return JSON: {"turns": [{"speaker": "...", "text": "...", "concepts": [{"name": "...", "category": "..."}]}]}
- speaker: exactly one participant name (the host usually asks, the guest answers). "Unknown" only if impossible.
- text: that turn's words verbatim and in order; together the turns must cover the whole passage.
- concepts: 0-3 per turn. name: a short, general, reusable Title Case term ("Open Source", "Hiring", "AI Agents"),
  singular, no parentheses. category: ONE word such as Technology, Career, Business, Skill, Tool, Company.
Reuse these existing concept names when they fit: """

METADATA = """This is the opening of a podcast episode transcript. Identify the host and the guest.
Return JSON: {"host": "...", "guest": "...", "summary": "one sentence"}. Use null for host/guest when unsure."""


def chat(system: str, user: str, json_mode: bool = False) -> str:
    """Blocking HTTP call — use asyncio.to_thread from async code."""
    body = {"model": settings.llm_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    for attempt in range(5):  # transient TLS drops are common with several threads hitting the API at once
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body, timeout=120,
                              headers={"Authorization": f"Bearer {settings.openrouter_api_key}"})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(2**attempt)


def chat_json(system: str, user: str) -> dict:
    text = chat(system, user, json_mode=True)
    return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()))  # tolerate fenced output


def analyse_chunk(text: str, participants: list[str], known: list[str] = ()) -> list[dict]:
    """Speaker turns with concepts. `known`: concept names already in the graph, so topics converge across shows."""
    out = chat_json(ANALYSE + ", ".join(known), f"Participants: {', '.join(participants)}\n\n{text}")
    turns = []
    for t in out.get("turns", []):
        if not isinstance(t, dict) or not str(t.get("text") or "").strip():
            continue
        concepts = [c if isinstance(c, dict) else {"name": c} for c in t.get("concepts") or []]  # models vary
        turns.append({"speaker": str(t.get("speaker") or "Unknown").strip(), "text": str(t["text"]).strip(),
                      "concepts": [{"name": str(c["name"]).strip(), "category": str(c.get("category") or "Other").strip().title()}
                                   for c in concepts if c.get("name")]})
    return turns


def infer_metadata(opening: str) -> dict:
    """host / guest / summary from the first few thousand characters. Used when the CLI wasn't told."""
    return chat_json(METADATA, opening)
