# Architecture Overview

## Components

1. **Ingestion Pipeline** (Background)
   - Kafka: message broker
   - Workers: transcribe, chunk, embed
   - Neo4j: store results

2. **Query Pipeline** (Live)
   - FastAPI: HTTP API
   - Agents: understand → query → synthesize
   - Neo4j: retrieve data

## Data Flow

[Will be expanded in later phases]
