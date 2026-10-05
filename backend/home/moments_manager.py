import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

MOMENTS_PATH = Path(r"./data\moments.json")


def _load():
    if not MOMENTS_PATH.exists():
        return {"posts": []}
    with open(MOMENTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data):
    with open(MOMENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_posts():
    data = _load()
    return sorted(data["posts"], key=lambda p: (1 if p.get("pinned", False) else 0, p.get("created_at", "")), reverse=True)


def add_post(author: str, content: str, pinned: bool = False) -> dict:
    data = _load()
    post = {
        "id": uuid.uuid4().hex[:8],
        "author": author,  # "companion" / "user"
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "likes": [],
        "comments": [],
        "pinned": pinned,
    }
    data["posts"].append(post)
    _save(data)
    return post


def like_post(post_id: str, liker: str):
    data = _load()
    for p in data["posts"]:
        if p["id"] == post_id:
            if liker in p["likes"]:
                p["likes"].remove(liker)   # 取消赞
            else:
                p["likes"].append(liker)   # 点赞
            break
    _save(data)


def comment_post(post_id: str, author: str, content: str, reply_to: str | None = None) -> dict:
    data = _load()
    comment = {
        "id": uuid.uuid4().hex[:6],
        "author": author,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reply_to": reply_to,  # 回复的评论 id（可选）
    }
    for p in data["posts"]:
        if p["id"] == post_id:
            p.setdefault("comments", []).append(comment)
            break
    _save(data)
    return comment


def recent_user_posts(limit: int = 5) -> list:
    """给 loop.py 用：user最近的朋友圈。"""
    data = _load()
    user_posts = [p for p in data["posts"] if p.get("author") == "user"]
    user_posts.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return user_posts[:limit]
