"""
Apply the Neo4j schema (constraints + indexes).

Run from the repo root:
    poetry run python -m src.setup.init_neo4j

This reads NEO4J_* from your .env. On your laptop that means
NEO4J_URI=bolt://localhost:7687 (see Task 0.3).

Run this from the HOST, not inside the container: the schema file
lives in config/, which is not copied into the api image.
"""

from pathlib import Path
import logging

from src.query.db import Neo4jConnection

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# repo_root/src/setup/init_neo4j.py  ->  parents[2] == repo root
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "config" / "neo4j_schema.cypher"


def load_statements(path: Path) -> list[str]:
    """Read a .cypher file and split it into individual statements on ';'.

    Good enough for our schema (no semicolons inside strings). For complex
    files you'd use a real parser, but simple beats clever here.
    """
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("//")]
    text = "\n".join(lines)
    return [stmt.strip() for stmt in text.split(";") if stmt.strip()]


def init_schema() -> None:
    statements = load_statements(SCHEMA_FILE)
    logger.info("Loaded %d schema statements from %s", len(statements), SCHEMA_FILE.name)

    driver = Neo4jConnection.get_driver()
    with driver.session() as session:
        for stmt in statements:
            first_line = stmt.splitlines()[0][:72]
            session.run(stmt) # type: ignore
            logger.info("applied: %s", first_line)

        constraints = list(session.run("SHOW CONSTRAINTS"))
        indexes = list(session.run("SHOW INDEXES"))

    logger.info("Schema ready: %d constraints, %d indexes", len(constraints), len(indexes))


if __name__ == "__main__":
    init_schema()
    Neo4jConnection.close()