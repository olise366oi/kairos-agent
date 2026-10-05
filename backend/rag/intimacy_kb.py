from __future__ import annotations

from config import DATA_DIR

INTIMACY_KB_PATH = DATA_DIR / "intimacy_kb.txt"

_cache = {"mtime": None, "ready": False}


def chunk_intimacy_kb(text: str) -> list[str]:
    """按结构把亲密知识库切成片段：模块头作为新块起点，超长截断。"""
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

    if not INTIMACY_KB_PATH.exists():
        _cache["ready"] = False
        return False
    mtime = INTIMACY_KB_PATH.stat().st_mtime
    if _cache["mtime"] == mtime and _cache["ready"]:
        return True

    text = INTIMACY_KB_PATH.read_text(encoding="utf-8")
    chunks = chunk_intimacy_kb(text)
    if not chunks:
        _cache["ready"] = False
        return False

    embeddings = embed_texts(chunks)
    client = get_client()
    existing = [c.name for c in client.list_collections()]
    if "intimacy_kb" in existing:
        client.delete_collection("intimacy_kb")
    col = client.create_collection(name="intimacy_kb", metadata={"hnsw:space": "cosine"})
    col.add(
        ids=[f"ik{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=embeddings,
    )
    _cache["mtime"] = mtime
    _cache["ready"] = True
    return True


def search_intimacy(query: str, n_results: int = 3) -> list[str]:
    """检索与亲密话题最相关的片段（按需调用，仅在命中亲密关键词时使用）。"""
    if not _ensure_index():
        return []
    from rag.embedder import embed_texts
    from rag.store import get_client

    qemb = embed_texts([query])[0]
    try:
        col = get_client().get_collection("intimacy_kb")
    except Exception:
        return []
    res = col.query(query_embeddings=[qemb], n_results=n_results)
    return res["documents"][0] if res["documents"] else []
