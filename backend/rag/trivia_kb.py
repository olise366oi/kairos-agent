from __future__ import annotations

from config import DATA_DIR

TRIVIA_KB_PATH = DATA_DIR / "trivia.txt"

_cache = {"mtime": None, "ready": False}


def chunk_trivia_kb(text: str) -> list[str]:
    """按行切：每条琐事一行（- 开头），只保留条目行，超短行丢弃。"""
    chunks = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- ") and len(s) >= 10:
            chunks.append(s)
    return chunks


def _ensure_index() -> bool:
    """懒加载索引：只在第一次检索时建，文件变更后自动重建。"""
    import os
    from rag.embedder import embed_texts
    from rag.store import get_client

    if not TRIVIA_KB_PATH.exists():
        _cache["ready"] = False
        return False
    mtime = TRIVIA_KB_PATH.stat().st_mtime
    if _cache["mtime"] == mtime and _cache["ready"]:
        return True

    text = TRIVIA_KB_PATH.read_text(encoding="utf-8")
    chunks = chunk_trivia_kb(text)
    if not chunks:
        _cache["ready"] = False
        return False

    embeddings = embed_texts(chunks)
    client = get_client()
    existing = [c.name for c in client.list_collections()]
    if "trivia_kb" in existing:
        client.delete_collection("trivia_kb")
    col = client.create_collection(name="trivia_kb", metadata={"hnsw:space": "cosine"})
    col.add(
        ids=[f"tk{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=embeddings,
    )
    _cache["mtime"] = mtime
    _cache["ready"] = True
    return True


def search_trivia(query: str, n_results: int = 5) -> list[str]:
    """检索与伴侣琐事记忆最相关的片段（按需调用，仅在命中琐事关键词时使用）。"""
    if not _ensure_index():
        return []
    from rag.embedder import embed_texts
    from rag.store import get_client

    qemb = embed_texts([query])[0]
    try:
        col = get_client().get_collection("trivia_kb")
    except Exception:
        return []
    res = col.query(query_embeddings=[qemb], n_results=n_results)
    return res["documents"][0] if res["documents"] else []


if __name__ == "__main__":
    import sys
    ok = _ensure_index()
    print("trivia_kb index ready:", ok)
    if ok:
        from rag.store import get_client
        col = get_client().get_collection("trivia_kb")
        print("collection count:", col.count())
        if len(sys.argv) > 1:
            for d in search_trivia(sys.argv[1], n_results=5):
                print("---")
                print(d)
