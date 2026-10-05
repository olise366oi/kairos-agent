# -*- coding: utf-8 -*-
"""MCP stdio 客户端（JSON-RPC 2.0 over stdio）——从 backend/home/watch_manager.py 提取的独立可复用实现。

用法：以 npx 拉起任意 MCP server（如 football-api-mcp），按 JSON-RPC 2.0 逐行收发。
协议：initialize(protocolVersion) → notifications/initialized → tools/call(name, arguments)。
密钥一律经环境变量注入，代码内不含任何真实值。
"""
import json
import os
import subprocess
import threading
import time


def mcp_call(
    name: str,
    args: dict,
    api_key: str,
    cmd: list | None = None,
    initialize_timeout: float = 10.0,
    call_timeout: float = 20.0,
):
    """调用一次 MCP 工具，返回解析后的内容（JSON 或文本）。

    - cmd: 拉起 MCP server 的命令列表；默认 `cmd.exe /c npx -y football-api-mcp`。
    - api_key: 经环境变量注入 MCP server（FIVEDOLLARFOOTBALL_API_KEY）。
    - 失败统一抛超时/运行时异常，由调用方按需静默兜底。
    """
    if cmd is None:
        cmd = ["cmd.exe", "/c", "npx", "-y", "football-api-mcp"]
    child = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "FIVEDOLLARFOOTBALL_API_KEY": api_key},
    )
    result = {}

    def reader():
        for line in child.stdout:
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                continue
            result[j.get("id")] = j

    threading.Thread(target=reader, daemon=True).start()

    def send(obj):
        child.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        child.stdin.flush()

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "watch", "version": "1.0"}}})
    deadline = time.time() + initialize_timeout
    while time.time() < deadline and 1 not in result:
        time.sleep(0.05)
    if 1 not in result:
        child.kill()
        raise TimeoutError("mcp initialize timeout")
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": name, "arguments": args}})
    deadline = time.time() + call_timeout
    while time.time() < deadline and 2 not in result:
        time.sleep(0.05)
    child.kill()
    j = result.get(2)
    if not j:
        raise TimeoutError(f"mcp call {name} timeout")
    if j.get("error"):
        raise RuntimeError(json.dumps(j["error"], ensure_ascii=False))
    content = j["result"]["content"]
    text = content[0]["text"]
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    return text
