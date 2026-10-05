import json
import random
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from config import TIMEZONE
from pathlib import Path

MARKET_KB_PATH = Path("./data/market_kb.txt")

# 酱类：每瓶可使用次数
SAUCE_USES_PER_BOTTLE = 15


# ===== market_kb 解析：品牌行 + 商品行 =====

_DESC_WORDS = {
    "有机饲料", "户外活动", "鸡只户外活动", "放养", "蛋黄浓郁", "切片放吐司上", "做茶泡饭",
    "做smoothie", "做 smoothie", "评测高分", "成分干净", "无添加剂",
    "瑞士顶级", "比利时高级", "法国高级", "超市高级线",
    "city老牌", "亚洲超市", "city精品烘焙",
    "传奇熟成师", "半盐", "无盐",
    "法国最高等级", "最早上市", "野草莓风味", "秋季", "细长型",
    "发明了 praline", "发明了praline",
    "达能旗下有机品牌", "诺曼底顶级",
    "1894年创立", "夏朗德地区",
    "木柴炉烤制",
    "user喜欢的",
}


def _is_good_name(name: str) -> bool:
    if not name or len(name) < 2:
        return False
    if name in _DESC_WORDS:
        return False
    # 纯数字/标点/符号
    if re.fullmatch(r"[\d\s\.\-、，。！？：:；;%+·/]+", name):
        return False
    # 描述性长句
    if len(name) > 15 and ("，" in name or "。" in name):
        return False
    # "XX 年创立/历史"
    if re.search(r"\d+年?(创立|历史|陈)", name) and len(name) <= 12:
        return False
    # "XX地区"
    if name.endswith("地区") and len(name) <= 6:
        return False
    # 只有一个中文字的长串
    if len(re.findall(r"[\u4e00-\u9fff]", name)) == 1 and len(name) > 6:
        return False
    return True


def _split_items(text: str) -> list[str]:
    parts = re.split(r"[、，/]", text)
    return [p.strip() for p in parts if p.strip() and _is_good_name(p.strip())]


def _extract_brackets(text: str) -> tuple[str, list[str]]:
    brackets = re.findall(r"[（(]([^）)]+)[）)]", text)
    main = re.sub(r"[（(][^）)]*[）)]", "", text).strip()
    return main, brackets


def _find_zh(brackets: list[str]) -> str | None:
    """从括号内容里找最像中文译名的词（2~6字，不是描述词）。"""
    for b in brackets:
        if re.fullmatch(r"[A-Za-zÀ-ÿ\s/\-&.'0-9]+", b.strip()):
            continue
        zh_words = re.findall(r"[\u4e00-\u9fff]{2,8}", b)
        for z in zh_words:
            if z in _DESC_WORDS:
                continue
            if z.endswith("有售") or z.endswith("系列"):
                continue
            return z
    return None


def _has_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-zÀ-ÿ]", text))


_CATEGORY_WORDS = {
    "冰淇淋", "水果雪葩", "经典冰淇淋", "创意口味",
    "气泡水", "白巧克力", "黑巧克力", "牛奶巧克力",
    "速冻水饺", "冷冻莓果",
}


def _is_brand_line(main_before_colon: str) -> bool:
    """判断冒号前的部分是不是品牌名（而不是品类/描述）。"""
    if not _is_good_name(main_before_colon):
        return False
    # 纯品类词不当品牌
    if main_before_colon in _CATEGORY_WORDS:
        return False
    # 含外文且长度合适 → 大概率是品牌
    if _has_latin(main_before_colon) and len(main_before_colon) <= 50:
        return True
    # 纯中文 + 品类词结尾 → 是商品名不是品牌
    if re.search(r"(气泡水|雪葩|冰淇淋|巧克力)$", main_before_colon) and not _has_latin(main_before_colon):
        return False
    return True


def _extract_names_from_line(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("- "):
        line = line[2:].strip()
    line = re.sub(r"[。.]\s*$", "", line).strip()
    if not line:
        return []

    # 找第一个冒号
    colon_idx = -1
    for sep in ["：", ":"]:
        if sep in line:
            colon_idx = line.index(sep)
            break

    if colon_idx > 0:
        brand_part = line[:colon_idx].strip()
        desc_part = line[colon_idx + 1:].strip()
        brand_main, brand_brackets = _extract_brackets(brand_part)
        brand_zh = _find_zh(brand_brackets)

        if _is_brand_line(brand_main):
            display_brand = brand_main + (f" · {brand_zh}" if brand_zh else "")
            # 从描述里提取变体（口味/系列），按句号分段，取前几段
            variants: list[str] = []
            seen = set()
            for seg in re.split(r"[。]", desc_part):
                seg = seg.strip()
                if not seg:
                    continue
                # 去掉括号里的内容再拆分
                seg_clean = re.sub(r"[（(][^）)]*[）)]", "", seg)
                for v in _split_items(seg_clean):
                    if v not in seen:
                        seen.add(v)
                        variants.append(v)
                if len(variants) >= 6:
                    break

            if variants:
                return [f"{display_brand} · {v}" for v in variants]
            else:
                return [display_brand]
        else:
            # 冒号左边是品类（不是品牌）→ 右边是品牌/商品列表
            # 例："冰淇淋：Berthillon、Häagen-Dazs" → 右边每个是独立商品
            right_items = _split_items(desc_part)
            if right_items:
                return right_items

    # 普通商品行
    main, brackets = _extract_brackets(line)
    zh = _find_zh(brackets)
    items = _split_items(main)
    if not items:
        return []

    # 单条目 + 有中文翻译 + 主名含外文 → 显示 "外文 · 中文"
    if len(items) == 1 and zh and _has_latin(items[0]):
        return [f"{items[0]} · {zh}"]

    return items


def _load_market_sections() -> dict:
    if not MARKET_KB_PATH.exists():
        return {}
    sections: dict[str, list[str]] = {}
    current = ""
    for raw in MARKET_KB_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            sections.setdefault(current, [])
            continue
        if line.startswith("【") and line.endswith("】"):
            continue
        if not line.startswith("- "):
            continue
        if "⚠️" in line or "user不吃" in line:
            continue
        for n in _extract_names_from_line(line):
            if n and n not in sections.setdefault(current, []):
                sections[current].append(n)
    return sections


def _load_market_items() -> list:
    sections = _load_market_sections()
    items = []
    seen = set()
    for sec, names in sections.items():
        if sec in ("使用说明",):
            continue
        for n in names:
            if n and n not in seen:
                seen.add(n)
                items.append(n)
    return items


def _pick_items(n: int = 2) -> list:
    items = _load_market_items()
    if not items:
        return []
    n = min(n, len(items))
    return random.sample(items, n)


# ===== 冰箱操作 =====

STATE_PATH = Path("./data/home_state.json")


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _is_sauce(name: str) -> bool:
    """判断是不是酱类商品（酱、果酱、芥末、番茄酱等）。"""
    sauce_keywords = ["酱", "芥末", "番茄酱", "蛋黄酱", "沙拉酱"]
    # 去掉品牌前缀后判断
    clean = re.sub(r"^[A-Za-zÀ-ÿ\s'\-&.]+ · ", "", name)
    return any(k in clean for k in sauce_keywords)


def _is_egg(name: str) -> bool:
    """判断是不是鸡蛋类商品。"""
    return "鸡蛋" in name


def _sauce_unit_and_qty(name: str) -> tuple[str, float]:
    """根据品类返回 (单位, 数量)。
    - 酱类：15 次/瓶
    - 鸡蛋：5 颗
    - 其他：1 份
    """
    if _is_sauce(name):
        return "次", float(SAUCE_USES_PER_BOTTLE)
    if _is_egg(name):
        return "颗", 5.0
    return "份", 1.0


def refill_fridge(force: bool = False) -> list:
    """按 market_kb 分类（板块）每个分类随机配 2 种，追加进冰箱。
    返回新增的物品列表。
    force=True 时不管冰箱有没有都填；否则只在冰箱空时填。
    """
    state = _load_state()
    if not state:
        return []
    today = state.get("today") or {}
    fridge = today.get("fridge") or []
    if fridge and not force:
        return []
    sections = _load_market_sections()
    new_names = []
    for sec, items in sections.items():
        if sec in ("使用说明",):
            continue
        pool = [it for it in items if it]
        if not pool:
            continue
        n = min(2, len(pool))
        new_names.extend(random.sample(pool, n))
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M")  # city时间
    existing_names = {it.get("name") for it in fridge if isinstance(it, dict)}
    for name in new_names:
        if name in existing_names:
            continue
        unit, qty = _sauce_unit_and_qty(name)
        fridge.append({
            "name": name,
            "qty": qty,
            "unit": unit,
            "added_at": now,
        })
        existing_names.add(name)
    today["fridge"] = fridge
    state["today"] = today
    _save_state(state)
    return new_names


DESSERT_SECTION = "甜点"


def _ensure_breakfast_staples() -> list:
    from meal_planner import _load_cook_kb, _ensure_in_fridge
    state = _load_state()
    if not state:
        return []
    fridge = state.get("today", {}).get("fridge") or []
    kb = _load_cook_kb()
    added = []
    carbs = kb.get("三明治 · 碳水", [])
    names = {it.get("name") for it in fridge if isinstance(it, dict)}
    if carbs and not any(c["name"] in names for c in carbs):
        c = random.choice(carbs)
        if _ensure_in_fridge(fridge, c["name"], c["qty"], c["unit"]):
            added.append(c["name"])
    for st in kb.get("冰箱常备", []):
        if st["name"] in ("Nicolas Alziari橄榄油", "Fleur de Sel de Guérande", "Poivre de Kampot"):
            continue
        if st["name"] not in names:
            if _ensure_in_fridge(fridge, st["name"], st["qty"], st["unit"]):
                added.append(st["name"])
    if added:
        state["today"]["fridge"] = fridge
        _save_state(state)
    return added


def generate_brought_back() -> list:
    """晚上带回来：甜品每日必买 1 个 + 其余随机 1-2 样。"""
    state = _load_state()
    if not state:
        return []
    _ensure_breakfast_staples()
    state = _load_state()
    today = state.get("today") or {}
    sections = _load_market_sections()
    dessert_pool = sections.get(DESSERT_SECTION, [])
    other_pool = []
    for sec, items in sections.items():
        if sec in ("使用说明", DESSERT_SECTION):
            continue
        other_pool.extend(items)
    brought = []
    if dessert_pool:
        brought.append(random.choice(dessert_pool))
    if other_pool:
        n = random.randint(1, min(2, len(other_pool)))
        brought.extend(random.sample(other_pool, n))
    fridge = today.get("fridge") or []
    names = {it.get("name") for it in fridge if isinstance(it, dict)}
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M")  # city时间
    for name in brought:
        if name not in names:
            unit, qty = _sauce_unit_and_qty(name)
            fridge.append({"name": name, "qty": qty, "unit": unit, "added_at": now})
    today["fridge"] = fridge
    today["brought_back"] = brought
    state["today"] = today
    _save_state(state)
    return brought


def _norm(s: str) -> str:
    s = re.sub(r"（[^）]*）", "", s or "")
    s = re.sub(r"\([^)]*\)", "", s)
    return s.replace(" ", "").replace("　", "")


def add_bought_items_to_fridge(names: list) -> list:
    """companion聊天中说买了什么 → 从 market 匹配后加入冰箱。"""
    state = _load_state()
    if not state:
        return []
    today = state.get("today") or {}
    fridge = today.get("fridge") or []
    market_items = _load_market_items()
    market_norm = {_norm(m): m for m in market_items if m}
    existing = {_norm(it.get("name", "")) for it in fridge if isinstance(it, dict)}
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M")  # city时间
    added = []
    for name in names or []:
        nm = _norm(name)
        if not nm:
            continue
        hit = None
        for mn, mfull in market_norm.items():
            if nm == mn or nm in mn or mn in nm:
                hit = mfull
                break
        if not hit:
            continue
        if _norm(hit) in existing:
            continue
        unit, qty = _sauce_unit_and_qty(hit)
        fridge.append({"name": hit, "qty": qty, "unit": unit, "added_at": now})
        existing.add(_norm(hit))
        added.append(hit)
    if added:
        today["fridge"] = fridge
        today["brought_back"] = added
        state["today"] = today
        _save_state(state)
    return added


if __name__ == "__main__":
    items = _load_market_items()
    print(f"从 market_kb 提取到 {len(items)} 个可买商品")
    print("前 10 个：", items[:10])
