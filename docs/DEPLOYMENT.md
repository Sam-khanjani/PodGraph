# Deployment

The whole stack is `docker-compose.yml`; a single VPS with Docker is enough.

```bash
git clone <repo> && cd PodGraph
cp .env.example .env               # set GROQ_API_KEY; set NEO4J_PASSWORD and NEO4J_AUTH for anything public
docker compose up -d --build       # Neo4j + API (+ Kafka, unused)
docker compose exec api python -m src.setup.init_neo4j
docker compose exec api python -m src.ingestion.pipeline file "data/transcripts/*.json"   # the saved real episodes
docker compose exec api python -m src.ingestion.pipeline youtube VIDEO_ID --podcast "Show"   # add more
```

- The API image is built by CI and pushed to `ghcr.io/<owner>/<repo>:latest` on every push to `main`;
  swap `build:` for `image:` in the compose file to use it.
- The embedding model (~90 MB) downloads on first use inside the container; mount `~/.cache/huggingface`
  as a volume to keep it across restarts.
- Neo4j data lives in the `neo4j_data` volume. Back it up with `docker run --rm -v podgraph_neo4j_data:/data -v $PWD:/backup alpine tar czf /backup/neo4j.tgz /data`.
- Put the API behind a reverse proxy (Caddy/nginx) for TLS; the app itself has no auth.
