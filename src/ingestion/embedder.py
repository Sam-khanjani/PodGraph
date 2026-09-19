"""Local embeddings (all-MiniLM-L6-v2): 384-dim, CPU, $0. Model loads lazily, once per process."""

MODEL, DIM = "all-MiniLM-L6-v2", 384
_model = None


def embed(texts: list[str]) -> list[list[float]]:
    """Batch-embed. Blocking CPU work — call via asyncio.to_thread from async code."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # slow import, deferred

        _model = SentenceTransformer(MODEL)
    return _model.encode(texts, normalize_embeddings=True).tolist()
