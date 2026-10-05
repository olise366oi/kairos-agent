from __future__ import annotations

import os

# 模型已预下载到本地缓存，强制离线加载，避免启动/首次使用时连接 HuggingFace 卡住
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_embedder = None


def get_embedder():
    # 惰性加载：sentence_transformers 会连带导入 PyTorch（约 3~4 秒），
    # 只在第一次真正需要向量化时才加载，避免每次启动都变慢。
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(MODEL_NAME)
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of text chunks."""
    model = get_embedder()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()
