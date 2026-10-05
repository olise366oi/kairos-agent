import random
from pathlib import Path
import json

COOK_KB_PATH = Path(r"./data\cook_kb.txt")
MARKET_KB_PATH = Path(r"./data\market_kb.txt")
STATE_PATH = Path(r"./data\home_state.json")


def _load_cook_kb() -> dict:
    """返回 {'三明治 · 碳水': [{'name','qty','unit'}...], ...}"""
    if not COOK_KB_PATH.exists():
        return {}
    result = {}
    current = None
    for line in COOK_KB_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            result.setdefault(current, [])
            continue
        if current and "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                try:
                    qty = float(parts[1])
                except ValueError:
                    continue
                result[current].append({
                    "name": parts[0],
                    "qty": qty,
                    "unit": parts[2],
                })
    return result


def _load_market_items() -> list:
    """从 market_kb 提取商品名。"""
    if not MARKET_KB_PATH.exists():
        return []
    import re
    items = []
    for line in MARKET_KB_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        content = re.sub(r"（[^）]*）", "", line[2:]).strip()
        content = re.sub(r"\([^)]*\)", "", content).strip()
        for p in re.split(r"[、，/]", content):
            p = p.strip()
            if p and len(p) >= 2:
                items.append(p)
    return items


def _fridge_index(fridge: list) -> dict:
    """{'名称': index}，方便查和改。"""
    return {item.get("name", ""): i for i, item in enumerate(fridge) if isinstance(item, dict)}


def _ensure_in_fridge(fridge: list, name: str, qty: float, unit: str) -> bool:
    """保证冰箱里有 name。缺则从 market_kb 补货。返回是否补过。"""
    idx = _fridge_index(fridge)
    if name in idx:
        # 有就补到标准量
        item = fridge[idx[name]]
        if float(item.get("qty", 0)) < qty:
            item["qty"] = qty
            return True
        return False
    # 不在冰箱，从 market_kb 补
    market = _load_market_items()
    # 匹配：name 或相似（规范化：去括号、去空格后再比）
    def _norm(s):
        import re
        s = re.sub(r"（[^）]*）", "", s)
        s = re.sub(r"\([^)]*\)", "", s)
        s = s.replace(" ", "").replace("　", "")
        return s

    name_n = _norm(name)
    if any(name_n in _norm(m) or _norm(m) in name_n for m in market):
        fridge.append({"name": name, "qty": qty, "unit": unit, "added_at": ""})
        return True
    return False


def _norm_name(s: str) -> str:
    """规范化名字：去括号内容、去空格，用于模糊匹配。"""
    import re
    s = re.sub(r"（[^）]*）", "", s or "")
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace(" ", "").replace("　", "")
    return s


def _match_from_fridge(fridge: list, kb_items: list) -> list:
    """从冰箱里匹配某板块的可用食材（名字规范化后互相包含）。返回匹配到的板块项列表。"""
    avail = []
    for ci in kb_items or []:
        cn = _norm_name(ci.get("name", ""))
        if not cn:
            continue
        for fi in fridge or []:
            if not isinstance(fi, dict):
                continue
            fn = _norm_name(fi.get("name", ""))
            if fn and (cn in fn or fn in cn):
                avail.append(ci)
                break
    return avail


def build_breakfast(fridge: list) -> dict:
    """从冰箱现有食材做早餐：每个板块从冰箱里匹配到才放，缺的跳过，不补货。"""
    kb = _load_cook_kb()
    if not kb:
        return {}

    carb_pool = _match_from_fridge(fridge, kb.get("三明治 · 碳水", []))
    meat_pool = _match_from_fridge(fridge, kb.get("三明治 · 荤", []))
    veg_pool = _match_from_fridge(fridge, kb.get("三明治 · 素", []))
    egg_pool = _match_from_fridge(fridge, kb.get("三明治 · 蛋", [])) or _match_from_fridge(
        fridge, [{"name": "有机散养鸡蛋（Label Rouge / Bio）", "qty": 6.0, "unit": "个"}]
    )
    extra_pool = _match_from_fridge(fridge, kb.get("三明治 · 附加", []))
    fruit_pool = _match_from_fridge(fridge, kb.get("早餐 · 水果", []))
    drink_pool = _match_from_fridge(fridge, kb.get("早餐 · 饮品", []))

    carb = random.choice(carb_pool) if carb_pool else None
    meat = random.choice(meat_pool) if meat_pool else None
    veg = random.choice(veg_pool) if veg_pool else None
    egg = random.choice(egg_pool) if egg_pool else None
    # 附加：冰箱里最多挑 2 样
    n_extra = random.randint(1, min(2, len(extra_pool))) if extra_pool else 0
    extras = random.sample(extra_pool, n_extra) if n_extra else []
    fruit_item = random.choice(fruit_pool) if fruit_pool else None
    drink_item = random.choice(drink_pool) if drink_pool else None

    # 组合名字：面包 + 荤 + 素 + 蛋 + 附加 + 三明治（冰箱里有啥拼啥）
    name_parts = []
    if carb:
        name_parts.append(carb["name"])
    if meat:
        name_parts.append(meat["name"])
    if veg:
        name_parts.append(veg["name"])
    if egg:
        name_parts.append(egg["name"])
    for e in extras:
        name_parts.append(e["name"])
    main_name = "".join(name_parts) + "三明治" if name_parts else "（冰箱里没什么料，先凑合）"

    fruit = fruit_item["name"] if fruit_item else ""
    drink = drink_item["name"] if drink_item else ""

    return {
        "main": main_name,
        "fruit": fruit,
        "drink": drink,
        "placed": "",
        "eaten": False,
        "fridge_updated": False,  # 从冰箱抽，不再补货
    }


def pick_dish(category: str, fridge: list) -> dict:
    """晚餐用，保留兼容。"""
    kb = _load_cook_kb()
    items = kb.get(category, [])
    if not items:
        return {}
    return random.choice(items)


if __name__ == "__main__":
    import json
    kb = _load_cook_kb()
    for k, v in kb.items():
        print(f"{k}: {len(v)} 条")
    # 测试
    test_fridge = [
        {"name": "鸡蛋", "qty": 2.0, "unit": "个"},
        {"name": "牛奶", "qty": 1.0, "unit": "瓶"},
        {"name": "草莓", "qty": 1.0, "unit": "份"},
    ]
    print("\n测试早餐：")
    print(json.dumps(build_breakfast(test_fridge), ensure_ascii=False, indent=2))
    print("\n补货后冰箱：")
    print(json.dumps(test_fridge, ensure_ascii=False, indent=2))
