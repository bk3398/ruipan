#!/usr/bin/env python3
"""诊断前端完场赔率渲染 + 胜率lookup匹配逻辑"""
import json, re, os

HTML_PATH = "/opt/ruipan/static/live-scores-preview-v6.html"
LOOKUP_PATH = "/opt/ruipan/static/backtest_winrate_lookup.json"

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. 提取renderAsianTable完整函数
print("="*60)
print("【renderAsianTable函数】")
m = re.search(r'function\s+renderAsianTable\s*\([^)]*\)\s*\{', html)
if m:
    start = m.start()
    depth = 0
    i = m.end() - 1
    while i < len(html):
        if html[i] == '{': depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0: break
        i += 1
    func_text = html[start:i+1]
    print(func_text[:3000])
    if len(func_text) > 3000:
        print(f"\n... (truncated, total {len(func_text)} chars)")
else:
    print("NOT FOUND")

# 2. 提取renderEuroTable完整函数
print("\n" + "="*60)
print("【renderEuroTable函数】")
m = re.search(r'function\s+renderEuroTable\s*\([^)]*\)\s*\{', html)
if m:
    start = m.start()
    depth = 0
    i = m.end() - 1
    while i < len(html):
        if html[i] == '{': depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0: break
        i += 1
    func_text = html[start:i+1]
    print(func_text[:3000])
    if len(func_text) > 3000:
        print(f"\n... (truncated, total {len(func_text)} chars)")
else:
    print("NOT FOUND")

# 3. 搜索win_rate/lookup/backtest相关JS代码
print("\n" + "="*60)
print("【胜率/lookup相关代码片段】")
# 搜索所有包含win_rate或lookup的行
lines = html.split('\n')
for i, line in enumerate(lines):
    if 'win_rate' in line.lower() or 'lookup' in line.lower() or 'backtest' in line.lower():
        print(f"  L{i+1}: {line.strip()[:200]}")

# 4. 搜索loadLookup/fetchJson等加载lookup表的代码
print("\n【lookup表加载代码】")
for i, line in enumerate(lines):
    if 'backtest_winrate' in line or 'winrate_lookup' in line or 'loadLookup' in line or 'LOOKUP' in line:
        # 打印上下文5行
        for j in range(max(0,i-2), min(len(lines), i+5)):
            print(f"  L{j+1}: {lines[j].strip()[:200]}")
        print()

# 5. lookup表结构
print("="*60)
print("【lookup表结构】")
if os.path.exists(LOOKUP_PATH):
    with open(LOOKUP_PATH, 'r') as f:
        lookup = json.load(f)
    print(f"类型: {type(lookup).__name__}")
    if isinstance(lookup, dict):
        keys = list(lookup.keys())
        print(f"总key数: {len(keys)}")
        print(f"前10个key: {keys[:10]}")
        if keys:
            first_key = keys[0]
            first_val = lookup[first_key]
            print(f"\n第一个key: {first_key}")
            print(f"value类型: {type(first_val).__name__}")
            if isinstance(first_val, dict):
                print(f"value keys: {list(first_val.keys())[:20]}")
                print(f"value内容: {json.dumps(first_val, ensure_ascii=False)[:500]}")
            elif isinstance(first_val, list):
                print(f"value长度: {len(first_val)}")
                if first_val:
                    print(f"第一项: {json.dumps(first_val[0], ensure_ascii=False)[:500]}")
            else:
                print(f"value: {first_val}")
            # 看几个不同key的结构
            for k in keys[1:3]:
                print(f"\nkey={k}: {json.dumps(lookup[k], ensure_ascii=False)[:300]}")
    elif isinstance(lookup, list):
        print(f"总条数: {len(lookup)}")
        if lookup:
            print(f"第一条: {json.dumps(lookup[0], ensure_ascii=False)[:500]}")
            if len(lookup) > 1:
                print(f"第二条: {json.dumps(lookup[1], ensure_ascii=False)[:500]}")
else:
    print("lookup表不存在!")

# 6. 检查analysis API返回的phase中asia/euro嵌套结构
print("\n" + "="*60)
print("【analysis API phase结构（第一个有数据的公司）】")
import urllib.request
try:
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1/matches/2967663/analysis")
    with urllib.request.urlopen(req, timeout=5) as r:
        an = json.loads(r.read())
    bks = an.get("bookmakers", {})
    for bk_name in bks:
        bk = bks[bk_name]
        phases = bk.get("phases", {})
        for phase_name in phases:
            phase = phases[phase_name]
            print(f"\n{bk_name}.{phase_name}:")
            print(f"  keys: {list(phase.keys())}")
            print(f"  euro: {json.dumps(phase.get('euro',{}), ensure_ascii=False)[:200]}")
            print(f"  asia: {json.dumps(phase.get('asia',{}), ensure_ascii=False)[:200]}")
            if 'win_rate' in phase:
                print(f"  win_rate: {phase['win_rate']}")
        break  # 只看第一个公司
except Exception as e:
    print(f"Error: {e}")
