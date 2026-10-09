from __future__ import annotations

import chromadb
from chromadb.config import Settings

from config import DATA_DIR, ensure_data_dir

CHROMA_DIR = str(DATA_DIR / "chroma")

_client: chromadb.PersistentClient | None = None


def get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        ensure_data_dir()
        _client = chromadb.PersistentClient(
            path=CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def query_collection(query_embedding: list[float], n_results: int = 5):
    client = get_client()
    try:
        col = client.get_collection("memories")
    except Exception:
        return []
    results = col.query(query_embeddings=[query_embedding], n_results=n_results)
    return results["documents"][0] if results["documents"] else []
