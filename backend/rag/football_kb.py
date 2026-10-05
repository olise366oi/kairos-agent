from __future__ import annotations

from config import DATA_DIR

FOOTBALL_KB_PATH = DATA_DIR / "football_kb.txt"

_cache = {"mtime": None, "ready": False}


def chunk_football_kb(text: str) -> list[str]:
    """按结构把足球知识库切成片段：模块头/小节头/编号条目作为新块起点，超长截断。"""
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
        is_new = (
            s.startswith("=== ")
            or s.startswith("【")
            or (len(s) > 1 and s[0].isdigit() and s[1] == ".")
        )
        if is_new and current:
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

    if not FOOTBALL_KB_PATH.exists():
        _cache["ready"] = False
        return False
    mtime = FOOTBALL_KB_PATH.stat().st_mtime
    if _cache["mtime"] == mtime and _cache["ready"]:
        return True

    text = FOOTBALL_KB_PATH.read_text(encoding="utf-8")
    chunks = chunk_football_kb(text)
    if not chunks:
        _cache["ready"] = False
        return False

    embeddings = embed_texts(chunks)
    client = get_client()
    existing = [c.name for c in client.list_collections()]
    if "football_kb" in existing:
        client.delete_collection("football_kb")
    col = client.create_collection(name="football_kb", metadata={"hnsw:space": "cosine"})
    col.add(
        ids=[f"kb{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=embeddings,
    )
    _cache["mtime"] = mtime
    _cache["ready"] = True
    return True


def search_football(query: str, n_results: int = 3) -> list[str]:
    """检索与足球问题最相关的战术片段（按需调用，仅在命中关键词时使用）。"""
    if not _ensure_index():
        return []
    from rag.embedder import embed_texts
    from rag.store import get_client

    qemb = embed_texts([query])[0]
    try:
        col = get_client().get_collection("football_kb")
    except Exception:
        return []
    res = col.query(query_embeddings=[qemb], n_results=n_results)
    return res["documents"][0] if res["documents"] else []
