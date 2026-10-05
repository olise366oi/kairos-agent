# -*- coding: utf-8 -*-
content = open(r"YOUR_PATH\backend\home\home.html", encoding="utf-8").read()

# 找 :root{...} 块（不进 base64 那行）
import re
m = re.search(r":root\{([^}]*)\}", content)
if m:
    print("=== :root 内容（前 600 字符）===")
    print(m.group(0)[:600])

# --lily 有没有被实际引用（除了定义那行）
defn_count = content.count("--lily:")
use_count = content.count("var(--lily)") + content.count("var( --lily )")
print(f"\n--lily 定义出现: {defn_count} 次")
print(f"var(--lily) 被引用: {use_count} 次")

# 文件大小
print(f"\n文件总大小: {len(content)} 字符")
