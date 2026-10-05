# -*- coding: utf-8 -*-
"""雅思翻译练习：抽文章句子 -> 提交批改 -> 错词入库。

数据文件：
  ielts_sentences.json   句子库（DeepSeek 预挑的长难句）
  ielts_state.json       当前进行中的一次练习
  ielts_wrong_words.json 错词本（去重，同词只留最近一次）
"""
import json
import random
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone, date

SENTENCES_PATH = Path("./data/ielts_sentences.json")
WORDS_PATH = Path("./data/ielts_wrong_words.json")
STATE_PATH = Path("./data/ielts_state.json")

# config.py 在 YOUR_PATH\backend
for _p in (r"YOUR_PATH\backend", r"YOUR_PATH\backend\agent"):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_sentences():
    if not SENTENCES_PATH.exists():
        return []
    with open(SENTENCES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_state():
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _load_wrong_words():
    if not WORDS_PATH.exists():
        return []
    with open(WORDS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_wrong_words(words):
    # 去重：同一个词只留最近一次
    seen = {}
    for w in words:
        seen[w["word"]] = w
    with open(WORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(list(seen.values()), f, ensure_ascii=False, indent=2)


def start_session(num: int = 10) -> dict:
    """抽一篇文章，从里面取 num 句。"""
    all_sentences = _load_sentences()
    if not all_sentences:
        return {"error": "没有句子库"}
    # 按 article_id 分组（没有 article_id 的归入 unknown）
    by_article = {}
    for s in all_sentences:
        aid = s.get("article_id", s.get("article", "unknown"))
        by_article.setdefault(aid, []).append(s)
    # 优先选句子数 >= num 的文章
    candidates = [v for v in by_article.values() if len(v) >= num]
    if candidates:
        pool = random.choice(candidates)
    else:
        pool = all_sentences
    picked = random.sample(pool, min(num, len(pool)))
    session = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "article_id": picked[0].get("article_id", ""),
        "article_title": picked[0].get("article_title", ""),
        "sentences": [
            {"sentence": p["sentence"], "target_word": p["target_word"]}
            for p in picked
        ],
        "submitted": False,
    }
    _save_state(session)
    return session


def get_state():
    return _load_state()


def submit(translations: list) -> dict:
    """翻译提交后批改。translations 是和 sentences 等长的中文翻译列表。"""
    state = _load_state()
    if not state or state.get("submitted"):
        return {"error": "没有进行中的练习"}

    from config import load_config
    cfg = load_config()
    api_key = cfg.get("api_key", "")
    base_url = (cfg.get("base_url") or "https://api.deepseek.com").rstrip("/")
    # config.json 里的 model 名可能过期；官方 /models 当前为 deepseek-flash / deepseek-v4-pro
    model = cfg.get("model") or "deepseek-flash"
    if model not in ("deepseek-flash", "deepseek-v4-pro", "deepseek-chat"):
        model = "deepseek-flash"

    pairs = []
    for i, s in enumerate(state["sentences"]):
        pairs.append({
            "index": i + 1,
            "english": s["sentence"],
            "target_word": s["target_word"],
            "user_translation": translations[i] if i < len(translations) else "",
        })
    prompt = (
        "你是雅思阅读翻译批改官。逐句判断用户的中文翻译是否句意正确"
        "（不必逐字对应，意思对即可；关键词 target_word 译偏就算错）。"
        "对每句返回字段：index（数字）、correct（布尔）、reference（参考翻译）、"
        "comment（简短点评，错的说明哪里理解偏了，对的可给一句话鼓励）。"
        "只输出 JSON，格式为 {\"results\": [ ... ]}，不要输出其他文字。\n\n"
        + json.dumps(pairs, ensure_ascii=False)
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result_text = json.load(resp)["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    try:
        parsed = json.loads(result_text)
        if isinstance(parsed, dict):
            parsed = parsed.get("results", parsed.get("data", []))
        assert isinstance(parsed, list)
    except Exception:
        return {"error": "批改结果解析失败", "raw": result_text[:500]}

    # 存错词：correct 非 true 的句子对应目标词入本
    wrong_words = _load_wrong_words()
    today = date.today().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in parsed:
        if not r.get("correct"):
            idx = int(r.get("index", 1)) - 1
            if 0 <= idx < len(state["sentences"]):
                tw = state["sentences"][idx]["target_word"]
                wrong_words.append({
                    "word": tw,
                    "date": today,
                    "added_at": now_iso,
                    "article_id": state.get("article_id", ""),
                    "article_title": state.get("article_title", ""),
                })
    _save_wrong_words(wrong_words)

    state["submitted"] = True
    state["results"] = parsed
    _save_state(state)
    return {"results": parsed}


def get_wrong_words(limit: int = 50) -> list:
    words = _load_wrong_words()
    words.sort(key=lambda w: w.get("added_at", ""), reverse=True)
    return words[:limit]


def get_today_wrong_words() -> list:
    today = date.today().isoformat()
    words = [w for w in _load_wrong_words() if w.get("date") == today]
    words.sort(key=lambda w: w.get("added_at", ""), reverse=True)
    return words


def reset():
    _save_state({})
