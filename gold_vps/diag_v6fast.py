#!/usr/bin/env python3
"""快速诊断：3秒超时，3场比赛，4接口并行"""
import urllib.request, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

API = "http://localhost:8000/api/v1/matches"
TIMEOUT = 5

def fetch(url):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode()
            return url.split('/')[-1], r.status, len(body), body[:200]
    except urllib.error.HTTPError as e:
        return url.split('/')[-1], e.code, 0, str(e)[:150]
    except Exception as e:
        return url.split('/')[-1], 'ERR', 0, f"{type(e).__name__}: {e}"[:150]

# Get today's matches
try:
    with urllib.request.urlopen(f"{API}/today", timeout=5) as r:
        data = json.loads(r.read())
    matches = data.get('data', [])[:5]
    print(f"今日比赛: {len(data.get('data',[]))} 场，取前5场测试\n")
except Exception as e:
    print(f"获取比赛列表失败: {e}")
    sys.exit(1)

endpoints = ['odds-timeline', 'analysis', 'fundamental', 'odds-quick']

for m in matches:
    fid = m['fixture_id']
    home = m.get('home_team','')
    away = m.get('away_team','')
    status = m.get('status','')
    bk_count = m.get('bookmaker_count', 0)
    print(f"=== {fid} {home} vs {away} [{status}] bookmakers={bk_count} ===")
    
    urls = [f"{API}/{fid}/{ep}" for ep in endpoints]
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, u): u for u in urls}
        for f in as_completed(futures):
            ep_name, code, size, snippet = f.result()
            marker = "✅" if code == 200 else "❌"
            print(f"  {marker} {ep_name:20s} [{code}] {size:>8} bytes  {snippet[:100]}")
    print()

print("=== 总结 ===")
print("如果 fundamental 或 odds-quick 返回 ❌，就是 Promise.all 全盘崩溃的根因")
