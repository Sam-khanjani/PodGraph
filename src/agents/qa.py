"""Question answering as a LangGraph: route ─▶ retrieve ─▶ synthesize ─▶ verify.

      ┌──────────── cypher failed, first try: router re-plans, shown the error
      ▼            │
    route ─▶ retrieve ─▶ synthesize ─▶ verify ─▶ END
                   │                   ▲
                   └─▶ fallback ───────┘      no rows / unsafe Cypher: meaning-based retrieval instead

The verifier never changes the answer: it reports, per sentence, whether the evidence supports it
(`verified`, `verification` in the response) and leaves the decision to the caller.
"""

import asyncio
import json
import logging
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.llm import chat, chat_json, verify_claims
from src.ingestion.embedder import embed
from src.query.repository import GraphRepository

log = logging.getLogger(__name__)

SCHEMA = """(Podcast {name, host})-[:HAS_EPISODE]->(Episode {episode_id, title, number, publish_date, summary, duration_seconds})
(Guest {name})-[:APPEARED_IN]->(Episode)
(Episode)-[:CONTAINS]->(Chunk {chunk_id, text, topic, summary, timestamp_start})
(Chunk)-[:MENTIONS {speaker, start, quote}]->(Concept {name, category})   // who said it, when (seconds)
(Concept)-[:RECOMMENDS {reason, chunk_id, episode_id}]->(Concept)         // 'source helps target', per passage"""

ROUTER = f"""You route a user question about a podcast knowledge graph to exactly ONE tool.
Graph schema:
{SCHEMA}
Tools:
- semantic_compare(q): passages about topic q, grouped per podcast. Default for "what do they say about X".
- shared_guests(): PEOPLE (guests) who appeared on more than one podcast.
- concept_reach(): TOPICS/concepts discussed on more than one podcast, ranked. Use for "which topics/themes do both shows..."
- bridge_guests(a, b): guests whose episodes touch both concepts a and b.
- recommendations(concept): what a concept is recommended for / recommended by, with the reason and the passage.
  Use for "what is X recommended for", "what helps with Y".
- person_mentions(person, concept): when (timestamp) and on which show a named person talked about a concept;
  concept may be null for everything they said. Use for "when did X talk about Y" questions.
- cypher(query): a READ-ONLY Cypher query you write, for structural questions the other tools cannot
  answer (counts, lists, dates, comparisons between speakers via MENTIONS.speaker). Return readable
  properties, not nodes. Add LIMIT 25. Follow the schema's arrows exactly and match names case-insensitively:
  MATCH (p:Podcast)-[:HAS_EPISODE]->(e:Episode)<-[:APPEARED_IN]-(g:Guest) ...
  MATCH (:Chunk)-[m:MENTIONS]->(k:Concept) WHERE toLower(k.name) CONTAINS 'problem' RETURN m.speaker, count(m)
Pick a named tool only when the question names a person or topic that is plainly a node in the graph.
If you would have to invent a concept name, or the question asks an opinion ("is X ok?", "what do they
think about X"), use semantic_compare — it matches on meaning and needs no exact name.
Reply with JSON: {{"tool": "<name>", "args": {{...}}}}"""

SYNTH = """Answer the question using ONLY the evidence JSON. After each claim cite its source in parentheses
as the podcast name and episode title taken from the evidence, e.g. (Some Show — Some Episode Title), plus the
timestamp written as mm:ss, e.g. 12:54, when the evidence has one (evidence timestamps are in seconds); if the
evidence has no episode titles, cite the podcast name alone. Never write placeholders.
If the evidence does not answer the question, say exactly that — never guess or extrapolate. 3-6 sentences."""

WRITE_KEYWORDS = re.compile(r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|LOAD|CALL\s*\{)\b", re.I)
MMSS = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")  # a cited mm:ss (not part of h:mm:ss)


class QA(TypedDict, total=False):
    question: str
    repo: GraphRepository
    plan: dict
    attempts: int
    error: str | None
    tool: str
    args: dict
    evidence: list
    answer: str
    verified: bool
    verification: dict


# ---- nodes -----------------------------------------------------------------------------

async def route(s: QA) -> QA:
    q = s["question"]
    if s.get("error"):  # self-correction round: shown the error, models usually fix their Cypher
        q += f"\n\nYour previous plan {json.dumps(s['plan'])} failed with: {s['error']}\nReturn a corrected plan."
    return {"plan": await asyncio.to_thread(chat_json, ROUTER, q), "attempts": s.get("attempts", 0) + 1}


async def retrieve(s: QA) -> QA:
    tool, args = s["plan"].get("tool", "semantic_compare"), s["plan"].get("args") or {}
    try:
        return {"tool": tool, "args": args, "evidence": await _retrieve(tool, args, s["repo"]), "error": None}
    except Exception as exc:
        log.warning("plan %s failed: %s", s["plan"], exc)
        return {"tool": tool, "args": args, "error": str(exc)}


async def _retrieve(tool: str, args: dict, repo: GraphRepository) -> list:
    rows = []
    if tool == "shared_guests":
        rows = await repo.shared_guests()
    elif tool == "concept_reach":
        rows = await repo.concept_reach(2, 20)
    elif tool == "bridge_guests":
        rows = await repo.bridge_guests(args["a"], args["b"])
    elif tool == "person_mentions":
        rows = await repo.person_mentions(args["person"], args.get("concept"))
    elif tool == "recommendations":
        rows = await repo.concept_recommendations(args["concept"])
    elif tool == "cypher" and not WRITE_KEYWORDS.search(args["query"]):
        rows = await repo.read_cypher(args["query"])  # read transaction: Neo4j rejects writes anyway
    if not rows:  # unknown tool, unsafe Cypher, or a plan that matched nothing (an invented concept
        raise ValueError(f"no evidence: {tool} {args}")  # name, a misspelt guest) -> semantic fallback
    return rows


def after_retrieve(s: QA) -> str:
    if not s["error"]:
        return "synthesize"
    return "route" if s["tool"] == "cypher" and s["attempts"] < 2 else "fallback"


async def fallback(s: QA) -> QA:
    """Last resort: meaning-based retrieval needs no exact names, so it (almost) always finds something."""
    q = s["args"].get("q") or s["question"]
    vec = await asyncio.to_thread(embed, [q])
    return {"tool": "semantic_compare", "args": {"q": q}, "evidence": await s["repo"].semantic_compare(vec[0], 12)}


async def synthesize(s: QA) -> QA:
    payload = json.dumps({"question": s["question"], "evidence": s["evidence"]}, default=str)
    return {"answer": await asyncio.to_thread(chat, SYNTH, payload)}


async def verify(s: QA) -> QA:
    """Two checks on the answer, reported, never applied: every cited mm:ss must exist in the evidence (exact,
    no LLM), and every sentence must be supported by the evidence (LLM fact-checker)."""
    answer, evidence = s["answer"], s["evidence"]
    known = _timestamps(evidence)
    bad = sorted({f"{m}:{sec}" for m, sec in MMSS.findall(answer) if int(m) * 60 + int(sec) not in known})
    try:
        claims = await verify_claims(s["question"], answer, evidence, s["tool"], s["args"])
    except Exception as exc:  # the verifier is an observer: never let it sink a response
        log.warning("verifier failed: %s", exc)
        return {"verified": False, "verification": {"error": str(exc)[:200]}}
    unsupported = [{"text": c.text, "reason": c.reason or "cited timestamp is not in the evidence"} for c in claims
                   if not c.supported or any(t in c.text for t in bad)]
    return {"verified": bool(claims) and not unsupported,
            "verification": {"claims": len(claims), "supported": len(claims) - len(unsupported),
                             "unsupported": unsupported, "bad_timestamps": bad}}


def _timestamps(x, keys=("timestamp", "timestamp_start", "start")) -> set[int]:
    """Every timestamp (seconds) anywhere in the evidence rows, whatever tool produced them."""
    if isinstance(x, dict):
        own = {int(v) for k, v in x.items() if k in keys and isinstance(v, (int, float))}
        return own | _timestamps(list(x.values()))
    if isinstance(x, list):
        return set().union(*(_timestamps(v) for v in x))
    return set()


# ---- graph -----------------------------------------------------------------------------

def build() -> StateGraph:
    g = StateGraph(QA)
    for name, fn in [("route", route), ("retrieve", retrieve), ("fallback", fallback),
                     ("synthesize", synthesize), ("verify", verify)]:
        g.add_node(name, fn)
    g.add_edge(START, "route")
    g.add_edge("route", "retrieve")
    g.add_conditional_edges("retrieve", after_retrieve)
    g.add_edge("fallback", "synthesize")
    g.add_edge("synthesize", "verify")
    g.add_edge("verify", END)
    return g


graph = build().compile()


async def answer(question: str, repo: GraphRepository) -> dict:
    if cached := await repo.get_cached(question):
        return {**cached, "cached": True}
    s = await graph.ainvoke({"question": question, "repo": repo})
    result = {k: s[k] for k in ("question", "answer", "tool", "args", "verified", "verification")} | {"sources": s["evidence"]}
    await repo.cache(result)
    return {**result, "cached": False}
