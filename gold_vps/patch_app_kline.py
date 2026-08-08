#!/usr/bin/env python3
"""
app.py 注册 kline_api 路由补丁
用法: python3 patch_app_kline.py
"""
import shutil

APP_PATH = '/opt/ruipan/app.py'
KLINE_API_SRC = '/opt/ruipan/scraper/kline_api.py'
KLINE_API_DST = '/opt/ruipan/kline_api.py'

# 1. 复制 kline_api.py 到 app.py 同目录
shutil.copy2(KLINE_API_SRC, KLINE_API_DST)
print(f"✅ 复制 kline_api.py → {KLINE_API_DST}")

# 2. 读取 app.py
with open(APP_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

if 'kline_router' in content:
    print("⚠️ kline路由已注册，跳过")
else:
    # 添加 import
    content = content.replace(
        'import uvicorn\n',
        'import uvicorn\nfrom kline_api import router as kline_router\n',
        1
    )

    # 添加 include_router（在 app = FastAPI(...) 之后）
    content = content.replace(
        'app = FastAPI(title="锐盘 API", version="1.1.0", lifespan=lifespan)\n',
        'app = FastAPI(title="锐盘 API", version="1.1.0", lifespan=lifespan)\n'
        'app.include_router(kline_router)\n',
        1
    )

    # 在 lifespan 中 db_pool 创建后注入连接池
    content = content.replace(
        'db_pool = await asyncpg.create_pool(PG_DSN, min_size=5, max_size=20)\n',
        'db_pool = await asyncpg.create_pool(PG_DSN, min_size=5, max_size=20)\n'
        '    import kline_api\n'
        '    kline_api._db_pool = db_pool\n',
        1
    )

    with open(APP_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ app.py 已补丁：kline路由注册 + db_pool注入")

# 3. 验证
with open(APP_PATH, 'r', encoding='utf-8') as f:
    verify = f.read()
assert 'from kline_api import router' in verify
assert 'app.include_router(kline_router)' in verify
assert 'kline_api._db_pool = db_pool' in verify
print("✅ 验证通过")
