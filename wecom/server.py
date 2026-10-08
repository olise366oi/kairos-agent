# -*- coding: utf-8 -*-
"""企业微信接入服务。

- GET  /wecom/callback  回调验证（msg_signature/timestamp/nonce/echostr）
- POST /wecom/callback  接收用户消息 → 调 agent.chat() → 企业微信 send API 回发

Access Token 自动缓存刷新（有效期 2 小时，提前 5 分钟过期）。
配置从 ~/.kairos/wecom_config.json 读取（用户手动填，不写死在代码）。
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import threading
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

# 复用重逢后端：agent.loop.chat 与 chat.history
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
for _p in (str(_BACKEND), str(_BACKEND / "chat"), str(_BACKEND / "agent"), str(_BACKEND / "persona")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from wecom.config import load_wecom_config, is_configured  # noqa: E402
from wecom import crypto  # noqa: E402
from wecom.push import record_last_user  # noqa: E402
from wecom.dedup import is_processed as dedup_is_processed  # noqa: E402

app = FastAPI(title="重逢 · 企业微信接入")

# ---------- Access Token 管理（自动刷新，2h 有效，提前 5 分钟过期） ----------

_token_lock = threading.Lock()
_token_cache: dict = {"token": None, "expire_at": 0}


def _get_access_token(cfg: dict) -> str:
    """获取企业微信 access_token，带缓存 + 锁，过期自动刷新。"""
    with _token_lock:
        now = time.time()
        if _token_cache["token"] and _token_cache["expire_at"] > now + 300:
            return _token_cache["token"]

        url = (
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            f"?corpid={urllib.parse.quote(cfg['corp_id'])}"
            f"&corpsecret={urllib.parse.quote(cfg['secret'])}"
        )
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"获取 access_token 失败: {data}")
        _token_cache["token"] = data["access_token"]
        _token_cache["expire_at"] = now + int(data.get("expires_in", 7200))
        return _token_cache["token"]


def _download_media(cfg: dict, media_id: str) -> str:
    """用 media_id 从企业微信下载临时素材，返回 base64 字符串。失败返回空字符串。"""
    try:
        try:
            with open(r"YOUR_PATH\wecom\wecom_voice_debug.log", "a", encoding="utf-8") as _lf:
                _lf.write(f"{__import__('time').strftime('%H:%M:%S')} _download_media start, media_id={media_id[:25]}...\n")
        except Exception:
            pass
        token = _get_access_token(cfg)
        url = (
            "https://qyapi.weixin.qq.com/cgi-bin/media/get"
            f"?access_token={urllib.parse.quote(token)}"
            f"&media_id={urllib.parse.quote(media_id)}"
        )
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
        if "application/json" in content_type or "text/plain" in content_type:
            # 出错时企业微信返回 JSON
            try:
                err = json.loads(body.decode("utf-8"))
                print(f"[wecom] 下载素材失败: {err}", flush=True)
            except Exception:
                pass
            return ""
        try:
            with open(r"YOUR_PATH\wecom\wecom_voice_debug.log", "a", encoding="utf-8") as _lf:
                _lf.write(f"{__import__('time').strftime('%H:%M:%S')} _download_media OK, b64_len={len(base64.b64encode(body))}\n")
        except Exception:
            pass
        return base64.b64encode(body).decode("ascii")
    except Exception as e:
        try:
            with open(r"YOUR_PATH\wecom\wecom_voice_debug.log", "a", encoding="utf-8") as _lf:
                _lf.write(f"{__import__('time').strftime('%H:%M:%S')} _download_media ERR: {type(e).__name__} {e}\n")
        except Exception:
            pass
        print(f"[wecom] 下载素材异常: {type(e).__name__} {e}", flush=True)
        return ""


def _analyze_image(image_base64: str, prompt: str = "") -> str:
    """调 VisionBridge 分析图片，返回描述文本。失败返回空字符串。"""
    if not image_base64:
        return ""
    try:
        payload = json.dumps({
            "image_base64": image_base64,
            "prompt": prompt or "请用简洁的中文描述这张图片的内容。如果有文字，也一并提取。",
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:24602/api/vision/analyze",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("error"):
            print(f"[wecom] VisionBridge 报错: {data.get('error')} {data.get('detail', '')}", flush=True)
            return ""
        return (data.get("result") or "").strip()
    except Exception as e:
        print(f"[wecom] 调 VisionBridge 异常: {type(e).__name__} {e}", flush=True)
        return ""


def _process_image_in_background(cfg: dict, from_user: str, media_id: str, user_text: str = "") -> None:
    """后台线程：下载图片 → 分析 → 拼成文本 → 走原聊天流程。"""
    def worker():
        try:
            img_b64 = _download_media(cfg, media_id)
            if not img_b64:
                desc = "（图片下载失败，暂时看不到这张图）"
            else:
                desc = _analyze_image(img_b64)
                if not desc:
                    desc = "（图片分析失败，暂时看不到这张图）"

            if user_text:
                combined = f"{user_text}\n（user发了一张图片，图片内容：{desc}）"
            else:
                combined = f"（user发了一张图片，图片内容：{desc}）"

            reply = _handle_message_sync(from_user, combined)
            _send_message(cfg, from_user, reply)
        except Exception as e:
            print(f"[wecom] 图片处理异常: {type(e).__name__} {e}", flush=True)

    threading.Thread(target=worker, daemon=True).start()


def _transcribe_audio(audio_b64: str) -> dict:
    """调本地 VoiceASR 服务，返回 {text, emotions}。失败返回空 dict。"""
    if not audio_b64:
        return {}
    try:
        try:
            with open(r"YOUR_PATH\wecom\wecom_voice_debug.log", "a", encoding="utf-8") as _lf:
                _lf.write(f"{__import__('time').strftime('%H:%M:%S')} _transcribe_audio start, b64_len={len(audio_b64)}\n")
        except Exception:
            pass
        payload = json.dumps({"audio_base64": audio_b64}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:24603/api/voice/transcribe",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        try:
            with open(r"YOUR_PATH\wecom\wecom_voice_debug.log", "a", encoding="utf-8") as _lf:
                _lf.write(f"{__import__('time').strftime('%H:%M:%S')} _transcribe_audio OK, text={repr(data.get(chr(116)+chr(101)+chr(120)+chr(116),chr(39)+chr(39))[:80])}, emotions={data.get(chr(101)+chr(109)+chr(111)+chr(116)+chr(105)+chr(111)+chr(110)+chr(115),{})}\n")
        except Exception:
            pass
        return {
            "text": (data.get("text") or "").strip(),
            "emotions": data.get("emotions") or {},
        }
    except Exception as e:
        try:
            with open(r"YOUR_PATH\wecom\wecom_voice_debug.log", "a", encoding="utf-8") as _lf:
                _lf.write(f"{__import__('time').strftime('%H:%M:%S')} _transcribe_audio ERR: {type(e).__name__} {e}\n")
        except Exception:
            pass
        print(f"[wecom] VoiceASR 调用异常: {type(e).__name__} {e}", flush=True)
        return {}


def _process_voice_in_background(cfg: dict, from_user: str, media_id: str) -> None:
    """后台线程：下载音频 → ASR 转文字 + 情绪 → 拼成文本 → 走原聊天流程。"""
    def worker():
        try:
            audio_b64 = _download_media(cfg, media_id)
            if not audio_b64:
                combined = "（user发了一条语音，但音频下载失败）"
            else:
                # wecom 端先转成 16kHz 单声道 16bit wav，再传给 VoiceASR
                import tempfile, subprocess as _sp
                FFMPEG = r"YOUR_PATH\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe"
                try:
                    amr_path = ""
                    wav_path = ""
                    raw = base64.b64decode(audio_b64)
                    with tempfile.NamedTemporaryFile(suffix=".amr", delete=False) as _af:
                        _af.write(raw)
                        amr_path = _af.name
                    wav_path = amr_path[:-4] + ".wav"
                    _sp.run([FFMPEG, "-y", "-i", amr_path, "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", wav_path], capture_output=True, timeout=30)
                    with open(wav_path, "rb") as _wf:
                        audio_b64 = base64.b64encode(_wf.read()).decode("ascii")
                except Exception as _fe:
                    print(f"[wecom] ffmpeg 转码失败: {_fe}", flush=True)
                finally:
                    for _p in (amr_path, wav_path):
                        try:
                            if _p and os.path.exists(_p):
                                os.remove(_p)
                        except Exception:
                            pass
                result = _transcribe_audio(audio_b64)
                text = (result.get("text") or "").strip() if isinstance(result, dict) else ""
                emotions = result.get("emotions") or {} if isinstance(result, dict) else {}

                try:
                    with open(r"YOUR_PATH\wecom\wecom_voice_debug.log", "a", encoding="utf-8") as _lf:
                        _lf.write(f"{__import__('time').strftime('%H:%M:%S')} worker: text_len={len(text)}, text={repr(text)[:80]}, emotions={emotions}\n")
                except Exception:
                    pass
                if not text:
                    combined = "（user发了一条语音，但没听清内容）"
                else:
                    top_emotion = ""
                    if emotions:
                        emo_zh = {
                            "Embarrassment": "害羞",
                            "Amusement": "开心",
                            "Sadness": "难过",
                            "Anger": "生气",
                        }
                        top_name = max(emotions, key=lambda k: emotions[k])
                        top_score = emotions[top_name]
                        if top_score >= 0.1:
                            top_emotion = emo_zh.get(top_name, top_name)

                    if top_emotion:
                        combined = f"（user发了一条语音，内容：{text}，语气{top_emotion}）"
                    else:
                        combined = f"（user发了一条语音，内容：{text}）"

            reply = _handle_message_sync(from_user, combined)
            _send_message(cfg, from_user, reply)
        except Exception as e:
            print(f"[wecom] 语音处理异常: {type(e).__name__} {e}", flush=True)

    threading.Thread(target=worker, daemon=True).start()
def _send_message(cfg: dict, user_id: str, content: str) -> None:
    """通过企业微信 message/send 主动发消息给用户。"""
    token = _get_access_token(cfg)
    body = {
        "touser": user_id,
        "msgtype": "text",
        "agentid": int(cfg["agent_id"]),
        "text": {"content": content},
    }
    url = (
        "https://qyapi.weixin.qq.com/cgi-bin/message/send"
        f"?access_token={urllib.parse.quote(token)}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"发送消息失败: {data}")


# ---------- 消息处理（异步，不阻塞回调响应） ----------

def _handle_message_sync(user_id: str, content: str) -> str:
    """调用重逢 agent 生成回复（独立 API 调用，与桌面版同一套逻辑）。"""
    from config import load_config, set_llm_source
    from agent.loop import chat as agent_chat
    from chat.history import save_message

    set_llm_source("wecom")  # 三 API 切换：企微侧非峰谷走 api1（DeepSeek 官方）
    api_key = load_config().get("api_key", "")
    if not api_key:
        return "我这边还没配置好 DeepSeek API，暂时回不了你。"

    save_message("user", content)
    reasoning = None
    try:
        reply, reasoning = agent_chat(content, api_key, return_reasoning=True)
    except Exception as e:
        reply = f"（我这边出了点问题：{type(e).__name__}）"
    if not (reply or "").strip():
        reply = "……"
    save_message("assistant", reply, reasoning_content=reasoning)
    return reply


def _process_in_background(cfg: dict, user_id: str, content: str) -> None:
    """后台线程：生成回复并发回。失败重试一次 token 后重发。"""

    def run():
        try:
            reply = _handle_message_sync(user_id, content)
        except Exception:
            reply = "（我这边处理消息时出了点问题，稍后再试试？）"
        try:
            _send_message(cfg, user_id, reply)
        except Exception:
            # 可能 token 过期，强制刷新一次再试
            with _token_lock:
                _token_cache["token"] = None
                _token_cache["expire_at"] = 0
            try:
                _send_message(cfg, user_id, reply)
            except Exception as e:
                print(f"[wecom] 回发失败: {e}", flush=True)

    threading.Thread(target=run, daemon=True).start()


# ---------- 回调路由 ----------

def _parse_xml(body: bytes) -> dict:
    root = ET.fromstring(body)
    out = {}
    for child in root:
        out[child.tag] = child.text or ""
    return out


def _build_encrypted_xml(encrypt: str, nonce: str, timestamp: str, signature: str) -> str:
    return (
        "<xml>"
        f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
        f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
        f"<TimeStamp>{timestamp}</TimeStamp>"
        f"<Nonce><![CDATA[{nonce}]]></Nonce>"
        "</xml>"
    )


@app.get("/wecom/callback")
async def verify_callback(request: Request):
    """企业微信回调验证：验证签名后解密 echostr 并返回。"""
    cfg = load_wecom_config()
    if not is_configured(cfg):
        return PlainTextResponse("wecom_config.json 未配置完整", status_code=500)

    params = dict(request.query_params)
    msg_signature = params.get("msg_signature", "")
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")
    echostr = params.get("echostr", "")
    if not (msg_signature and timestamp and nonce and echostr):
        return PlainTextResponse("缺少参数", status_code=400)

    calc = crypto.get_signature(cfg["token"], timestamp, nonce, echostr)
    if calc != msg_signature:
        return PlainTextResponse("签名验证失败", status_code=403)

    try:
        aes_key = crypto.aes_key_from_encoding_aes_key(cfg["encoding_aes_key"])
        plain = crypto.decrypt(echostr, aes_key, cfg["corp_id"])
    except Exception as e:
        return PlainTextResponse(f"解密失败: {e}", status_code=403)
    return PlainTextResponse(plain)


@app.get("/wecom/callback2")
async def verify_callback_thoughts(request: Request):
    """思考链 bot（AgentId 1000003）回调验证：用 wecom_config_thoughts.json 验签。"""
    try:
        import sys as _sys2
        from push_thoughts import load_thoughts_config
        cfg = load_thoughts_config()
    except Exception:
        cfg = {}
    if not cfg.get("token") or not cfg.get("encoding_aes_key"):
        return PlainTextResponse("thoughts 配置未完整（缺 token/encoding_aes_key）", status_code=500)
    params = dict(request.query_params)
    msg_signature = params.get("msg_signature", "")
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")
    echostr = params.get("echostr", "")
    if not (msg_signature and timestamp and nonce and echostr):
        return PlainTextResponse("缺少参数", status_code=400)
    calc = crypto.get_signature(cfg["token"], timestamp, nonce, echostr)
    if calc != msg_signature:
        return PlainTextResponse("签名验证失败", status_code=403)
    try:
        aes_key = crypto.aes_key_from_encoding_aes_key(cfg["encoding_aes_key"])
        plain = crypto.decrypt(echostr, aes_key, cfg["corp_id"])
    except Exception as e:
        return PlainTextResponse(f"解密失败: {e}", status_code=403)
    return PlainTextResponse(plain)


@app.post("/wecom/callback2")
async def receive_callback_thoughts(request: Request):
    """思考链 bot 回调（暂不处理消息，返回 200 空，防企微重试）。"""
    return Response(content=b"", status_code=200)


@app.post("/wecom/callback")
async def receive_callback(request: Request):
    """接收企业微信推送消息：验证签名 → 解密 → 后台生成回复并主动回发。"""
    cfg = load_wecom_config()
    if not is_configured(cfg):
        return PlainTextResponse("wecom_config.json 未配置完整", status_code=500)

    params = dict(request.query_params)
    msg_signature = params.get("msg_signature", "")
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")

    body = await request.body()
    xml = _parse_xml(body)
    encrypt = xml.get("Encrypt", "")
    if not encrypt:
        return PlainTextResponse("缺少 Encrypt", status_code=400)

    calc = crypto.get_signature(cfg["token"], timestamp, nonce, encrypt)
    if calc != msg_signature:
        return PlainTextResponse("签名验证失败", status_code=403)

    try:
        aes_key = crypto.aes_key_from_encoding_aes_key(cfg["encoding_aes_key"])
        plain_xml_text = crypto.decrypt(encrypt, aes_key, cfg["corp_id"])
    except Exception as e:
        print(f"[wecom] 解密失败: {e}", flush=True)
        return PlainTextResponse("解密失败", status_code=403)

    msg = _parse_xml(plain_xml_text.encode("utf-8"))
    msg_type = msg.get("MsgType", "")
    from_user = msg.get("FromUserName", "")
    content = msg.get("Content", "").strip()
    msg_id = msg.get("MsgId", "")

    # MsgId 去重：企业微信可能对同一条消息重复推送，同一条 MsgId 只处理一次
    if msg_id and dedup_is_processed(msg_id):
        print(f"[wecom] 忽略重复消息 MsgId={msg_id}", flush=True)
        return Response(content=b"", status_code=200)

    if msg_type == "text" and from_user and content:
        # 记录最近一次从企微发消息的 userid（供电脑端回复精确推送）
        try:
            record_last_user(from_user)
        except Exception:
            pass
        # 立即返回空响应（企业微信 5 秒限制），后台生成回复后主动 send 回发
        _process_in_background(cfg, from_user, content)
    elif msg_type == "image" and from_user:
        # 记录最近一次从企微发消息的 userid
        try:
            record_last_user(from_user)
        except Exception:
            pass
        media_id = msg.get("MediaId", "")
        if media_id:
            _process_image_in_background(cfg, from_user, media_id, user_text="")
        else:
            print(f"[wecom] 图片消息没有 MediaId，忽略", flush=True)
    elif msg_type == "voice" and from_user:
        try:
            record_last_user(from_user)
        except Exception:
            pass
        # 临时诊断：打印 voice 消息完整内容
        try:
            with open(r"YOUR_PATH\wecom\voice_debug.log", "a", encoding="utf-8") as f:
                f.write(f"=== voice msg at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                f.write(f"msg_type={msg_type}\n")
                f.write(f"msg keys: {list(msg.keys())}\n")
                f.write(f"msg full: {msg}\n")
                f.write(f"Recognition: {repr(msg.get('Recognition', ''))}\n")
                f.write(f"MediaId: {msg.get('MediaId', '')}\n")
                f.write(f"Format: {msg.get('Format', '')}\n")
                f.write("\n")
        except Exception as e:
            print(f"[wecom] 写诊断日志失败: {e}", flush=True)
        media_id = msg.get("MediaId", "")
        _process_voice_in_background(cfg, from_user, media_id)
    else:
        print(f"[wecom] 忽略非文本消息: type={msg_type} from={from_user}", flush=True)

# ---------- Apple Watch 健康数据采集（Health Auto Export 推送） ----------

@app.get("/health/webhook")
async def health_webhook_verify():
    """GET 验证：接口是否就绪。"""
    return {"status": "ok", "msg": "health webhook 已就绪，POST JSON（心率/步数/睡眠）即可"}


@app.post("/health/webhook")
async def health_webhook(request: Request):
    """接收 Health Auto Export 推送：立即返回 ok；数据写入放后台线程（写失败只记错误日志，不影响已返回的响应）。"""
    try:
        body = await request.json()
    except Exception:
        return Response(
            content=json.dumps({"error": "body 不是合法 JSON"}, ensure_ascii=False),
            status_code=400, media_type="application/json",
        )
    threading.Thread(target=_ingest_health_in_background, args=(body,), daemon=True).start()
    return Response(
        content=json.dumps({"status": "ok"}, ensure_ascii=False),
        status_code=200, media_type="application/json",
    )


def _ingest_health_in_background(body: dict) -> None:
    """后台线程：写入健康数据到 health.json。失败只记错误日志，不抛回主线程。"""
    try:
        from health import ingest
        ingest(body)
    except Exception as e:
        try:
            err_log = Path(__file__).resolve().parent.parent / "backend" / "logs" / "health_err.log"
            err_log.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "error": f"{type(e).__name__}: {e}",
            }, ensure_ascii=False) + "\n"
            with open(err_log, "a", encoding="utf-8") as f:
                f.write(line)
            print(f"[health] 后台写入失败，已记入 {err_log}", flush=True)
        except Exception as e2:
            print(f"[health] 后台写入失败，且错误日志也写不进去: {type(e).__name__}: {e}; log_err={e2}", flush=True)

