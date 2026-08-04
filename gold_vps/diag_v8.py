#!/usr/bin/env python3
"""诊断完场赛事赔率空白 + 胜率缺失"""
import urllib.request, json, sys

BASE = "http://127.0.0.1:8000"

def fetch(path):
    try:
        req = urllib.request.Request(BASE + path)
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except Exception as e:
        return 0, str(e)

# 1. 获取今日比赛
st, data = fetch("/api/v1/matches/today")
matches = data.get("data", [])
print(f"今日比赛: {len(matches)} 场\n")

# 分类
finished = [m for m in matches if m.get("status") == "finished" or "完" in str(m.get("status",""))]
live = [m for m in matches if m.get("status") == "live" or "进行" in str(m.get("status",""))]
scheduled = [m for m in matches if m.get("status") == "scheduled" or "未" in str(m.get("status",""))]
print(f"完场: {len(finished)}, 进行: {len(live)}, 未开: {len(scheduled)}")

# 打印前3个完场和前3个未开的status原始值
if finished:
    print(f"\n完场status样例: {[m.get('status') for m in finished[:3]]}")
if scheduled:
    print(f"未开status样例: {[m.get('status') for m in scheduled[:3]]}")

# 2. 测试完场赛事赔率接口
print("\n" + "="*60)
print("【完场赛事赔率测试】")
for m in (finished[:3] or matches[:3]):
    fid = m.get("fixture_id") or m.get("match_id")
    print(f"\n--- {fid} {m.get('home_team','')} vs {m.get('away_team','')} [{m.get('status')}] ---")
    
    st, tl = fetch(f"/api/v1/matches/{fid}/odds-timeline")
    if isinstance(tl, dict):
        euro_data = tl.get("data",{}).get("euro",{})
        asia_data = tl.get("data",{}).get("asian",{})
        print(f"  odds-timeline: {st}, euro公司数={len(euro_data)}, asia公司数={len(asia_data)}")
        if euro_data:
            for bk in list(euro_data.keys())[:2]:
                phases = euro_data[bk]
                print(f"    {bk} phases: {list(phases.keys())}")
        if asia_data:
            for bk in list(asia_data.keys())[:2]:
                phases = asia_data[bk]
                print(f"    {bk} phases: {list(phases.keys())}")
    else:
        print(f"  odds-timeline: {st}, {str(tl)[:200]}")
    
    st, oq = fetch(f"/api/v1/matches/{fid}/odds-quick")
    if isinstance(oq, dict):
        euro_arr = oq.get("euro",[])
        asia_arr = oq.get("asia",[])
        print(f"  odds-quick: {st}, euro条数={len(euro_arr)}, asia条数={len(asia_arr)}")
        poisson = oq.get("poisson")
        print(f"  poisson: {'有' if poisson else '无'}")
        if euro_arr:
            # 检查odds_type分布
            types = set(e.get("odds_type") for e in euro_arr)
            print(f"  euro odds_type: {types}")
            print(f"  euro[0] keys: {list(euro_arr[0].keys())}")
    else:
        print(f"  odds-quick: {st}, {str(oq)[:200]}")

# 3. 测试分析接口中的胜率
print("\n" + "="*60)
print("【胜率数据检查】")
test_matches = (finished[:2] + live[:2] + scheduled[:2]) or matches[:6]
for m in test_matches:
    fid = m.get("fixture_id") or m.get("match_id")
    st, an = fetch(f"/api/v1/matches/{fid}/analysis")
    if isinstance(an, dict):
        bks = an.get("bookmakers", {})
        has_winrate = False
        for bk_name, bk_data in bks.items():
            phases = bk_data.get("phases", {})
            for phase_name, phase_data in phases.items():
                if isinstance(phase_data, dict):
                    if phase_data.get("win_rate") is not None:
                        has_winrate = True
                    # 检查所有key
                    if bk_name == list(bks.keys())[0] and phase_name == list(phases.keys())[0]:
                        print(f"\n  {fid} {bk_name}.{phase_name} keys: {list(phase_data.keys())}")
        status_icon = "✅" if has_winrate else "❌"
        print(f"  {fid} {m.get('home_team','')[:6]} vs {m.get('away_team','')[:6]} [{m.get('status')}] bookmakers={len(bks)} 胜率: {status_icon}")
    else:
        print(f"  {fid} analysis: {st}, {str(an)[:100]}")

# 4. 检查V3 lookup表是否存在
print("\n" + "="*60)
print("【V3回测lookup表检查】")
import os
lookup_paths = [
    "/opt/ruipan/data/v3_lookup.json",
    "/opt/ruipan/data/backtest_v3.json",
    "/opt/ruipan/backtest/v3_lookup.json",
    "/opt/ruipan/static/v3_lookup.json",
    "/opt/ruipan/v3_lookup.json",
]
for p in lookup_paths:
    if os.path.exists(p):
        sz = os.path.getsize(p)
        print(f"  ✅ {p} ({sz} bytes)")
    else:
        print(f"  ❌ {p} not found")

# 搜索可能的lookup文件
print("\n搜索包含win_rate或lookup的文件...")
for root_dir in ["/opt/ruipan"]:
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for fn in filenames:
            if "lookup" in fn.lower() or "v3" in fn.lower() or "backtest" in fn.lower():
                fp = os.path.join(dirpath, fn)
                print(f"  找到: {fp} ({os.path.getsize(fp)} bytes)")

# 5. 检查app.py中胜率相关逻辑
print("\n" + "="*60)
print("【app.py胜率逻辑检查】")
app_path = "/opt/ruipan/app.py"
if os.path.exists(app_path):
    with open(app_path, 'r') as f:
        content = f.read()
    # 找win_rate相关行
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'win_rate' in line.lower() or 'lookup' in line.lower() or 'backtest' in line.lower():
            print(f"  L{i+1}: {line.strip()[:120]}")
else:
    print(f"  app.py not found at {app_path}")
