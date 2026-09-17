# Agents

All LLM calls go through `src/agents/llm.py: chat()` — one OpenRouter chat-completions request.
Model is `LLM_MODEL` in `.env`. Default `nex-agi/nex-n2.5-pro:free` — OpenRouter's free tier, $0, rate-limited
(~20 req/min, hence `LLM_PARALLEL=2`). Any model that supports structured output works; `openai/gpt-4o-mini` is
the tested paid alternative (faster, pennies per episode). Free models that ignore JSON schemas (e.g. gemma) fail.

## Ingestion agents (`src/agents/llm.py`, wired by the LangGraph in `src/ingestion/pipeline.py`)

Each is one prompt with a Pydantic output schema (`llm.with_structured_output`), so the pipeline never
parses free text.

| agent | in → out | node |
|---|---|---|
| `find_boundaries` | numbered captions → indices where a new topic starts | `segment` |
| `infer_metadata` | transcript opening → host, guest, summary (null when unsure) | `analyse` (once per episode, only if CLI didn't say) |
| `analyse` | one topic passage + participants + known concept names → topic, summary, speaker turns each with 0-3 concepts | `analyse` (per chunk) |
| `same_concept` | two labels → same concept? (strict: 'Pull Requests'='Pull Request', 'AI'≠'AI Agents') | `resolve_concepts` (only for 0.80–0.92 vector matches) |
| `recommend` | chunk summary + its concept names → `source helps target` + reason | `recommend` (per chunk) |

**Concept bank.** `Concept` nodes carry an embedding of their name (`concept_embedding_index`). A candidate
is embedded, its nearest bank entry looked up, and reused at ≥0.92 cosine (or exact name), LLM-confirmed
between 0.80 and 0.92, otherwise added — immediately, so the next candidate in the same run can match it.
The analyser is also shown the 80 most-used names up front. Re-ingesting an episode replaces its tags and
relations; concepts nothing mentions any more are deleted.

**Speaker attribution** is inferred from text (the analyser is told who is in the room). Reliable for
two-person interviews, "Unknown" when it can't tell; audio diarization would be the accurate alternative.

## Router agent (`qa.answer`, step 1)

Gets the graph schema and a tool list, returns `{"tool", "args"}`:

| tool | runs | good for |
|---|---|---|
| `semantic_compare(q)` | vector search grouped per podcast | "what do they say about X" (default) |
| `shared_guests()` | guests on ≥2 podcasts | cross-show people |
| `concept_reach()` | concepts on ≥2 podcasts | cross-show topics |
| `bridge_guests(a, b)` | guests whose episodes touch both concepts | multi-hop |
| `person_mentions(person, concept)` | speaker-attributed mentions with timestamps | "when did X talk about Y" |
| `cypher(query)` | LLM-written read-only Cypher | counts, lists, dates |

## Cypher safety

Generated Cypher is rejected if it contains write keywords (`CREATE MERGE DELETE SET REMOVE DROP LOAD CALL {`)
and is executed inside `session.execute_read`, so Neo4j itself refuses any write that slips through.
If the plan or the query fails, the router falls back to `semantic_compare` — the user still gets an answer.

## Synthesis agent (step 2)

Receives `{question, evidence}` and must answer **only** from the evidence, citing
`(Podcast — Episode title)`, or say the evidence is insufficient.

## Cache

The full result is stored as a `CachedAnswer` node keyed by the lower-cased, trimmed question.
Repeat questions return `"cached": true` without any LLM call.
