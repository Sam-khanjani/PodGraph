from neo4j import GraphDatabase

try:
    d = GraphDatabase.driver("bolt://localhost:7687", auth=None, connection_timeout=5)
    with d.session() as s:
        s.run("RETURN 1")
    print("ok")
except Exception as e:
    print("FAILED:", e)
