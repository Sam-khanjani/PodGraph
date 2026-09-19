# API

Interactive docs: `http://localhost:8010/docs`. All list endpoints return `[]`, not 404, when nothing matches;
404 is only for a missing entity. Name lookups are case-insensitive.

| Method | Path | Params | Returns |
|---|---|---|---|
| GET | `/health` | | liveness |
| GET | `/ready` | | 200 if Neo4j reachable, else 503 |
| GET | `/podcasts` | | podcasts with episode counts |
| GET | `/episodes/{episode_id}` | | episode + guests + ordered chunks |
| GET | `/guests/{name}` | | guest + podcasts + episodes (with concepts per episode) |
| GET | `/concepts` | `category`, `limit`, `offset` | concepts ranked by mentions |
| GET | `/concepts/{name}` | | quotes grouped by podcast |
| GET | `/concepts/{name}/recommendations` | | what it is recommended for / by, with reason and the passage |
| GET | `/people` | | everyone attributed as a speaker, with mention counts |
| GET | `/people/{name}` | | concepts this person talks about, per show |
| GET | `/people/{name}/mentions` | `concept` (optional, substring) | when (seconds) and on which show they talked about it, with the quote |
| GET | `/search` | `term` (≥2), `limit`, `offset` | substring hits |
| GET | `/search/semantic` | `q` (≥2), `k` (1–50) | vector hits with podcast / episode / guest / score |
| GET | `/insights/shared-guests` | | guests on ≥2 podcasts |
| GET | `/insights/concept-reach` | `min_podcasts`, `limit` | concepts ranked by podcast reach |
| GET | `/insights/bridge-guests` | `concept_a`, `concept_b` | guests whose episodes touch both |
| GET | `/insights/semantic-compare` | `q`, `k` (2–50) | top-3 semantic quotes per podcast |
| POST | `/query` | body `{"question": "..."}` | `{answer, tool, args, sources, cached}` — 502 if the LLM step fails |

Examples:

```bash
curl "localhost:8010/search/semantic?q=how%20to%20get%20hired%20as%20an%20engineer&k=5"
curl "localhost:8010/insights/concept-reach"
curl -X POST localhost:8010/query -H 'content-type: application/json' \
     -d '{"question": "Who are the guests and which show was each on?"}'
```
