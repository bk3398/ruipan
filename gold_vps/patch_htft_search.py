#!/usr/bin/env python3
"""
半全场检索 API + 页面 部署补丁
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
用法（VPS上执行）：
  cd /opt/ruipan/ruipan_repo/gold_vps
  python3 patch_htft_search.py
  systemctl restart ruipan-api

功能：
  1. 复制 htft_search_api.py → /opt/ruipan/
  2. 复制 htft-search.html → /opt/ruipan/static/htft-search.html
  3. 在 app.py 注册 router + 注入 db_pool（幂等）
"""
import shutil, os, sys

APP = "/opt/ruipan/app.py"
API_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "htft_search_api.py")
HTML_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "htft-search.html")
API_DST = "/opt/ruipan/htft_search_api.py"
STATIC_DIR = "/opt/ruipan/static"
HTML_DST = os.path.join(STATIC_DIR, "htft-search.html")

os.makedirs(STATIC_DIR, exist_ok=True)
shutil.copy2(API_SRC, API_DST)
print(f"✅ API 模块 → {API_DST}")
shutil.copy2(os.path.normpath(HTML_SRC), HTML_DST)
print(f"✅ 检索页面 → {HTML_DST}")

with open(APP, "r", encoding="utf-8") as f:
    code = f.read()

patched = 0

# 1. import router
if "from htft_search_api import router as htft_router" not in code:
    if "import uvicorn\n" in code:
        code = code.replace(
            "import uvicorn\n",
            "import uvicorn\nfrom htft_search_api import router as htft_router\n",
            1
        )
        patched += 1
        print("✅ 添加 htft import")
    else:
        print("⚠️ 未找到 import uvicorn，请手动添加 import")
else:
    print("⚠️ htft import 已存在")

# 2. include_router
if "app.include_router(htft_router)" not in code:
    anchor = 'app = FastAPI(title="锐盘 API", version="1.1.0", lifespan=lifespan)\n'
    if anchor in code:
        code = code.replace(anchor, anchor + "app.include_router(htft_router)\n", 1)
        patched += 1
        print("✅ 注册 htft router")
    else:
        # 兜底：找任意 include_router 后插入
        if "app.include_router(" in code:
            idx = code.find("app.include_router(")
            end = code.find("\n", idx) + 1
            code = code[:end] + "app.include_router(htft_router)\n" + code[end:]
            patched += 1
            print("✅ 注册 htft router（兜底位置）")
        else:
            print("⚠️ 未找到 FastAPI app 初始化位置，请手动注册")
else:
    print("⚠️ htft router 已注册")

# 3. 注入 db_pool
if "htft_search_api._db_pool = db_pool" not in code:
    anchor2 = "db_pool = await asyncpg.create_pool(PG_DSN, min_size=5, max_size=20)\n"
    if anchor2 in code:
        code = code.replace(
            anchor2,
            anchor2 + "    import htft_search_api\n    htft_search_api._db_pool = db_pool\n",
            1
        )
        patched += 1
        print("✅ 注入 db_pool")
    else:
        print("⚠️ 未找到 db_pool 创建语句，请手动注入 htft_search_api._db_pool = db_pool")
else:
    print("⚠️ db_pool 已注入")

# 4. 静态文件挂载（确保 static 目录被 serve）
if "htft-search.html" not in code and "app.mount(\"/static\"" not in code:
    if "from fastapi.staticfiles import StaticFiles" not in code:
        code = code.replace(
            "from fastapi import",
            "from fastapi.staticfiles import StaticFiles\nfrom fastapi import",
            1
        ) if "from fastapi import" in code else code
    if 'app.mount("/static"' not in code:
        # 在 include_router 之后挂载静态目录
        anchor3 = "app.include_router(htft_router)\n"
        if anchor3 in code:
            code = code.replace(
                anchor3,
                anchor3 + 'app.mount("/static", StaticFiles(directory="/opt/ruipan/static"), name="static")\n',
                1
            )
            patched += 1
            print("✅ 挂载 /static 目录")
else:
    print("⚠️ static 挂载已存在")

with open(APP, "w", encoding="utf-8") as f:
    f.write(code)

print(f"\n应用补丁数: {patched}")
print("验证引用：")
for token in ["from htft_search_api import router", "app.include_router(htft_router)",
              "htft_search_api._db_pool = db_pool", 'StaticFiles(directory="/opt/ruipan/static")']:
    print(f"  {'✅' if token in code else '❌'} {token}")

print("\n完成！重启服务：")
print("  systemctl restart ruipan-api")
print("访问：https://raypan.net/static/htft-search.html")
