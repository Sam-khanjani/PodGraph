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
timestamp written as mm:ss when the evidence has one (evidence timestamps are in seconds); if the
evidence has no episode titles, cite the podcast name alone. Never write placeholders.
If the evidence does not answer the question, say exactly that — never guess or extrapolate. 3-6 sentences."""

WRITE_KEYWORDS = re.compile(r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|LOAD|CALL\s*\{)\b", re.I)


async def _retrieve(tool: str, args: dict, repo: GraphRepository):
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


async def answer(question: str, repo: GraphRepository) -> dict:
    if cached := await repo.get_cached(question):
        return {**cached, "cached": True}

    plan = await asyncio.to_thread(chat_json, ROUTER, question)
    for attempt in range(2):
        tool, args = plan.get("tool", "semantic_compare"), plan.get("args") or {}
        try:
            evidence = await _retrieve(tool, args, repo)
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
            break

    text = await asyncio.to_thread(chat, SYNTH, json.dumps({"question": question, "evidence": evidence}, default=str))
    result = {"question": question, "answer": text, "tool": tool, "args": args, "sources": evidence}
    await repo.cache(result)
    return {**result, "cached": False}
