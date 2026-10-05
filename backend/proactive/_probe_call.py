# -*- coding: utf-8 -*-
import sys, inspect
sys.path.insert(0, r"YOUR_PATH\backend\proactive")
sys.path.insert(0, r"YOUR_PATH\backend\home")

import adapter
a = adapter.KairosAdapter()
a.DRY_RUN = True

print("=== send_message 实际源码（call 分支附近）===")
src = inspect.getsource(a.send_message)
# 只打印 call 分支及上下文
lines = src.splitlines()
for i, line in enumerate(lines):
    if "intent == \"call\"" in line:
        for j in range(max(0, i-2), min(len(lines), i+12)):
            print(lines[j])
        break

print("\n=== DRY-RUN 模拟 call ===")
ok = a.send_message("在忙吗。", {"intent": "call"})
print("结果:", ok)
