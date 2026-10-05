# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"YOUR_PATH\backend\home")

print("=== call_manager 模块是否存在 ===")
try:
    import call_manager
    print("导入成功:", call_manager.__file__)
    print("属性:", [x for x in dir(call_manager) if not x.startswith("_")])
except Exception as e:
    print("导入失败:", type(e).__name__, e)
    sys.exit(0)

print("\n=== 调 start_call + call_link ===")
try:
    call_manager.start_call("companion")
    link = call_manager.call_link()
    print("link 返回:", repr(link))
except Exception as e:
    print("调用失败:", type(e).__name__, e)
