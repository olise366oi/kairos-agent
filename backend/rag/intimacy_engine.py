from __future__ import annotations

from config import DATA_DIR

INTIMACY_ENGINE_PATH = DATA_DIR / "intimacy_engine.txt"

_cache = {"mtime": None, "ready": False, "chunks": []}


def chunk_intimacy_engine(text: str) -> list[str]:
    """按结构把亲密场景推进手册切成片段：模块头作为新块起点，超长截断。"""
    chunks = []
    current = []

    def flush():
        nonlocal current
        if current:
            c = "\n".join(current).strip()
            if len(c) >= 10:
                chunks.append(c)
            current = []

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("=== ") and current:
            flush()
        current.append(line)
        if sum(len(x) for x in current) > 500:
            flush()
    flush()
    return chunks


def _ensure_index() -> bool:
    """懒加载索引：只在第一次检索时建，文件变更后自动重建。"""
    import os
    from rag.embedder import embed_texts
    from rag.store import get_client

    if not INTIMACY_ENGINE_PATH.exists():
        _cache["ready"] = False
        return False
    mtime = INTIMACY_ENGINE_PATH.stat().st_mtime
    if _cache["mtime"] == mtime and _cache["ready"]:
        return True

    text = INTIMACY_ENGINE_PATH.read_text(encoding="utf-8")
    chunks = chunk_intimacy_engine(text)
    if not chunks:
        _cache["ready"] = False
        return False

    embeddings = embed_texts(chunks)
    client = get_client()
    existing = [c.name for c in client.list_collections()]
    if "intimacy_engine" in existing:
        client.delete_collection("intimacy_engine")
    col = client.create_collection(name="intimacy_engine", metadata={"hnsw:space": "cosine"})
    col.add(
        ids=[f"ie{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=embeddings,
    )
    _cache["mtime"] = mtime
    _cache["ready"] = True
    _cache["chunks"] = chunks
    return True


def search_intimacy_engine(query: str, n_results: int = 3) -> list[str]:
    """检索亲密场景推进规则（按需调用，仅在亲密场景明确发生时使用）。"""
    if not _ensure_index():
        return []
    from rag.embedder import embed_texts
    from rag.store import get_client

    qemb = embed_texts([query])[0]
    try:
        col = get_client().get_collection("intimacy_engine")
    except Exception:
        return []
    res = col.query(query_embeddings=[qemb], n_results=n_results)
    docs = res["documents"][0] if res["documents"] else []
    # 强制注入「细节质感」段：不依赖检索命中，亲密场景必带
    for c in _cache.get("chunks", []):
        if c.startswith("=== 细节质感"):
            if not any("细节质感" in d for d in docs):
                docs.insert(0, c)
            break
    return docs
