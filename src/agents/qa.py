"""Question answering: router agent picks a tool -> tool runs on the graph -> synthesis agent writes the answer."""

import asyncio
import json
import logging
import re

from src.agents.llm import chat, chat_json
from src.ingestion.embedder import embed
from src.query.repository import GraphRepository

log = logging.getLogger(__name__)

SCHEMA = """(Podcast {name, host})-[:HAS_EPISODE]->(Episode {episode_id, title, number, publish_date, summary, duration_seconds})
(Episode)-[:CONTAINS]->(Chunk {chunk_id, text, timestamp_start})
(Guest {name})-[:APPEARED_IN]->(Episode)
(Chunk)-[:MENTIONS {speaker, start, quote}]->(Concept {name, category})   // who said it, when (seconds)"""

ROUTER = f"""You route a user question about a podcast knowledge graph to exactly ONE tool.
Graph schema:
{SCHEMA}
Tools:
- semantic_compare(q): passages about topic q, grouped per podcast. Default for "what do they say about X".
- shared_guests(): guests who appeared on more than one podcast.
- concept_reach(): concepts discussed on multiple podcasts, ranked.
- bridge_guests(a, b): guests whose episodes touch both concepts a and b.
- person_mentions(person, concept): when (timestamp) and on which show a named person talked about a concept;
  concept may be null for everything they said. Use for "when did X talk about Y" questions.
- cypher(query): a READ-ONLY Cypher query you write, for structural questions the other tools cannot
  answer (counts, lists, dates, comparisons between speakers via MENTIONS.speaker). Return readable
  properties, not nodes. Add LIMIT 25. Follow the schema's arrows exactly and match names case-insensitively:
  MATCH (p:Podcast)-[:HAS_EPISODE]->(e:Episode)<-[:APPEARED_IN]-(g:Guest) ...
  MATCH (:Chunk)-[m:MENTIONS]->(k:Concept) WHERE toLower(k.name) CONTAINS 'problem' RETURN m.speaker, count(m)
Reply with JSON: {{"tool": "<name>", "args": {{...}}}}"""

SYNTH = """Answer the question using ONLY the evidence JSON. After each claim cite its source in parentheses
as the podcast name and episode title taken from the evidence, e.g. (Some Show — Some Episode Title), plus the
timestamp as mm:ss when the evidence has one; if the
evidence has no episode titles, cite the podcast name alone. Never write placeholders.
If the evidence does not answer the question, say exactly that — never guess or extrapolate. 3-6 sentences."""

WRITE_KEYWORDS = re.compile(r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|LOAD|CALL\s*\{)\b", re.I)


async def _retrieve(tool: str, args: dict, question: str, repo: GraphRepository):
    if tool == "shared_guests":
        return await repo.shared_guests()
    if tool == "concept_reach":
        return await repo.concept_reach(2, 20)
    if tool == "bridge_guests":
        return await repo.bridge_guests(args["a"], args["b"])
    if tool == "person_mentions":
        return await repo.person_mentions(args["person"], args.get("concept"))
    if tool == "cypher" and not WRITE_KEYWORDS.search(args["query"]):
        rows = await repo.read_cypher(args["query"])  # read transaction: Neo4j rejects writes anyway
        if rows:
            return rows
    raise ValueError(f"unusable plan: {tool} {args}")  # incl. Cypher that matched nothing -> semantic fallback


async def answer(question: str, repo: GraphRepository) -> dict:
    if cached := await repo.get_cached(question):
        return {**cached, "cached": True}

    plan = await asyncio.to_thread(chat_json, ROUTER, question)
    for attempt in range(2):
        tool, args = plan.get("tool", "semantic_compare"), plan.get("args") or {}
        try:
            evidence = await _retrieve(tool, args, question, repo)
            break
        except Exception as exc:
            log.warning("plan %s failed: %s", plan, exc)
            if attempt == 0 and tool == "cypher":  # one self-correction round: shown the error, models usually fix it
                plan = await asyncio.to_thread(chat_json, ROUTER, f"{question}\n\nYour previous plan {json.dumps(plan)} "
                                               f"failed with: {exc}\nReturn a corrected plan.")
                continue
            tool, args = "semantic_compare", {"q": args.get("q") or question}  # last resort: semantic retrieval
            vec = await asyncio.to_thread(embed, [args["q"]])
            evidence = await repo.semantic_compare(vec[0], 12)

    text = await asyncio.to_thread(chat, SYNTH, json.dumps({"question": question, "evidence": evidence}, default=str))
    result = {"question": question, "answer": text, "tool": tool, "args": args, "sources": evidence}
    await repo.cache(result)
    return {**result, "cached": False}
