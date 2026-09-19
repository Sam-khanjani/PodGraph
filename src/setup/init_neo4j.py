"""Apply config/neo4j_schema.cypher (constraints + indexes). Idempotent.

    python -m src.setup.init_neo4j
"""

from pathlib import Path

from src.query.db import close, run

SCHEMA = Path(__file__).resolve().parents[2] / "config" / "neo4j_schema.cypher"


def init_schema() -> None:
    text = "\n".join(ln for ln in SCHEMA.read_text(encoding="utf-8").splitlines() if not ln.startswith("//"))
    for stmt in filter(None, map(str.strip, text.split(";"))):
        run(stmt)
    print(f"schema applied: {len(run('SHOW CONSTRAINTS'))} constraints, {len(run('SHOW INDEXES'))} indexes")


if __name__ == "__main__":
    init_schema()
    close()
