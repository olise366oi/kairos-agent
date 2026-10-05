import json
import uuid
from pathlib import Path
from datetime import datetime, timezone, date, timedelta


def _home_today() -> date:
    """按city时区取今天日期（夏令时 UTC+2，冬令时 UTC+1）。"""
    now_utc = datetime.now(timezone.utc)
    # 夏令时：3月最后周日 ~ 10月最后周日
    year = now_utc.year
    # 简单判断：4-9月是夏令时
    offset = 2 if 4 <= now_utc.month <= 9 else 1
    home_tz = now_utc + timedelta(hours=offset)
    return home_tz.date()

DIARY_PATH = Path(r"./data\diary.json")
ARCHIVE_PATH = Path(r"./data\diary_archive.json")


def _load():
    if not DIARY_PATH.exists():
        return {"entries": []}
    with open(DIARY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data):
    with open(DIARY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_entries():
    data = _load()
    return sorted(data["entries"], key=lambda e: e.get("date", ""), reverse=True)


def has_today() -> bool:
    today = _home_today().isoformat()
    data = _load()
    return any(e.get("date") == today for e in data["entries"])


def add_entry(content: str) -> dict:
    data = _load()
    entry = {
        "id": uuid.uuid4().hex[:8],
        "date": _home_today().isoformat(),
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["entries"].append(entry)
    _save(data)
    return entry


def recent_entries(limit: int = 5) -> list:
    return list_entries()[:limit]


def _load_archive():
    if not ARCHIVE_PATH.exists():
        return {"batches": []}
    with open(ARCHIVE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_archive(data):
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def archive_current() -> dict:
    """点新对话时调用：把当前日记打包成一个归档批次，清空当前 diary.json。"""
    current = _load()
    if not current["entries"]:
        return {"archived": 0}
    dates = sorted(e["date"] for e in current["entries"])
    batch = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "date_from": dates[0],
        "date_to": dates[-1],
        "count": len(current["entries"]),
        "entries": current["entries"],
    }
    arch = _load_archive()
    arch["batches"].insert(0, batch)
    _save_archive(arch)
    _save({"entries": []})
    return {"archived": len(current["entries"])}


def list_archive() -> list:
    """返回所有归档批次（每个批次含 entries）。"""
    return _load_archive()["batches"]
