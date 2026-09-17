# Agents

All LLM calls go through `src/agents/llm.py: chat()` — one OpenRouter chat-completions request.
Model is `LLM_MODEL` in `.env` (default `openai/gpt-4o-mini`, pennies per episode / per question).

## Turn + concept analyser (ingestion time)

`llm.analyse_chunk(text, participants, known)` — one call per chunk. YouTube captions carry no
speaker labels, so the model is told who is in the room ("Patrick Akil (host), Bruno Schaatsbergen
(guest)") and splits the passage into speaker turns, tagging each turn with 0-3 concepts. Each turn's
timestamp comes from aligning its opening words back to the caption segments (`chunker.timestamp_turns`).
Stored as `(Chunk)-[:MENTIONS {speaker, start, quote}]->(Concept)` plus `Chunk.turns` for display,
which is what answers "when did X talk about Y, on which show".

Accuracy note: attribution is inferred from text (question/answer rhythm, names in context). Good for
two-person interviews, weaker for panels or unnamed speakers, where it labels "Unknown". Audio
diarization would be the accurate alternative, at the cost of a much heavier dependency stack.

Concept names: the model is shown the graph's 80 most-used names and told to reuse them, so the same
topic from different shows lands on one node. Chunks run in a thread pool of 4; transient network
errors are retried. Re-ingesting an episode replaces its tags. Skip with `--no-llm`.

## Metadata agent (ingestion time)

`llm.infer_metadata(opening)` — when the CLI wasn't given `--host`/`--guest`, the first ~4000
characters are sent once to identify host, guest and a one-sentence summary (null when unsure).

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
