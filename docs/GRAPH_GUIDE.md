# Graph Guide

## The model 
Podcast --HAS_EPISODE--> Episode --CONTAINS--> Chunk


## Keys
- Podcast: `name` (unique)
- Episode: `episode_id` (unique, e.g. "huberman-31"); `number` is NOT globally unique
- Chunk:   `chunk_id` (unique, e.g. "huberman-31-0001")

## Useful queries
See `docs/queries/`. Set parameters in Neo4j Browser with `:param key => value;`.

| File | What it answers |
|------|-----------------|
| list_podcasts.cypher      | Which podcasts exist? |
| episodes_for_podcast.cypher | What episodes does a podcast have? |
| chunks_for_episode.cypher | What's the transcript of an episode (in order)? |
| keyword_search.cypher     | Which chunks mention a literal word? (substring, not semantic) |
| chunks_per_episode.cypher | How much content per episode? |

## Cypher notes
- MERGE = match-or-create (idempotent). CREATE = always new (can duplicate).
- Pass values as $parameters, never f-strings. Labels/types can't be parameterized.
- WITH pipes results from one stage to the next (like a Unix pipe).
- UNWIND turns a list into rows so you can MERGE many items in one query.

## relationships are live (last update)
Podcast --HAS_EPISODE--> Episode --CONTAINS--> Chunk --MENTIONS--> Concept
Guest --APPEARED_IN--> Episode

### The point of the graph
A single Concept node (e.g. "Sleep") is referenced by chunks from MULTIPLE podcasts.
A single Guest node (e.g. "Matthew Walker") links episodes of MULTIPLE podcasts.
Shared nodes = connections that plain vector RAG cannot represent.

### Concept categories (controlled vocabulary)
Supplement, Biomarker, Exercise, Diet, Disease, Physiology



### Canonical names matter
"Circadian Rhythm" and "circadian rhythm" would be two different nodes.
We keep one canonical spelling per concept.

### New queries
See shared_concept_across_podcasts, guest_appearances, concepts_for_guest,
concept_mention_counts in docs/queries/.

