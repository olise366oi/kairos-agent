import json
import base64
from pathlib import Path

CLIP_PATH = Path(r"./data\clipboard.json")
IMG_PATH = Path(r"./data\clipboard_image.png")


def get_clip():
    if not CLIP_PATH.exists():
        return {"type": "text", "content": ""}
    try:
        with open(CLIP_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"type": "text", "content": ""}


def set_text(content: str):
    with open(CLIP_PATH, "w", encoding="utf-8") as f:
        json.dump({"type": "text", "content": content}, f, ensure_ascii=False)
    if IMG_PATH.exists():
        IMG_PATH.unlink()


def set_image(data_url: str):
    header, b64 = data_url.split(",", 1)
    with open(IMG_PATH, "wb") as f:
        f.write(base64.b64decode(b64))
    with open(CLIP_PATH, "w", encoding="utf-8") as f:
        json.dump({"type": "image", "content": str(IMG_PATH)}, f, ensure_ascii=False)


def clear_clip():
    if CLIP_PATH.exists():
        CLIP_PATH.unlink()
    if IMG_PATH.exists():
        IMG_PATH.unlink()
