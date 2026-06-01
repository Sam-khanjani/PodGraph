from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from neo4j import Driver
import logging
from src.config import settings
from src.query.db import get_db, Neo4jConnection

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="GraphRAG Podcast AI",
    description="Agentic AI system for cross-podcast synthesis",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Verify Neo4j connection on startup"""
    logger.info("Starting up GraphRAG API...")
    if Neo4jConnection.verify_connection():
        logger.info("✓ Neo4j connection verified")
    else:
        logger.error("✗ Neo4j connection failed")


@app.on_event("shutdown")
async def shutdown_event():
    """Close Neo4j connection on shutdown"""
    logger.info("Shutting down GraphRAG API...")
    Neo4jConnection.close()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "graphrag-api",
        "version": "0.1.0"
    }


@app.get("/info")
async def info():
    """System info endpoint"""
    return {
        "name": "GraphRAG Podcast AI",
        "neo4j_uri": settings.neo4j_uri,
        "kafka_bootstrap_servers": settings.kafka_bootstrap_servers,
    }


@app.get("/podcasts")
async def get_podcasts(db: Driver = Depends(get_db)):
    """Get all podcasts in the database"""
    try:
        with db.session() as session:
            result = session.run("MATCH (p:Podcast) RETURN p.name as name, p.host as host")
            podcasts = [dict(record) for record in result]
        
        if not podcasts:
            return {"podcasts": [], "message": "No podcasts found yet"}
        
        return {"podcasts": podcasts}
    
    except Exception as e:
        logger.error(f"Error fetching podcasts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)