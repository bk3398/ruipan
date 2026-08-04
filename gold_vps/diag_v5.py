#!/usr/bin/env python3
"""Check app.py analysis endpoint + dump full analysis JSON."""
import json, urllib.request, re

# 1. Dump full analysis JSON for a match with data
def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())

data = fetch("http://localhost:8000/api/v1/matches/today")
matches = data.get("data", [])

target = None
for m in matches:
    fid = m.get("fixture_id")
    an = fetch(f"http://localhost:8000/api/v1/matches/{fid}/analysis")
    bk_count = len(an.get("bookmakers", {}))
    if bk_count > 0 and target is None:
        target = fid
        target_data = an
        print(f"=== 选中 fid={fid}: {m.get('home_team')} vs {m.get('away_team')}, {bk_count} bookmakers ===")
        break

if target:
    print(json.dumps(target_data, ensure_ascii=False, indent=2, default=str)[:5000])

# 2. Read app.py and find the analysis endpoint
print("\n\n=== app.py analysis endpoint code ===")
with open("/opt/ruipan/app.py", "r", encoding="utf-8") as f:
    app_code = f.read()

# Find the analysis route
patterns = [
    r'@app\.(get|post)\(["\']\/api\/v1\/matches\/\{fixture_id\}\/analysis["\']',
    r'@app\.(get|post)\(["\'].*analysis.*["\']',
    r'def\s+.*analysis',
]
for pat in patterns:
    for m in re.finditer(pat, app_code):
        start = m.start()
        # Find the function definition and extract ~100 lines
        func_start = app_code.find('\n', start)
        snippet = app_code[start:start+3000]
        print(f"\n--- match at char {start} ---")
        print(snippet[:3000])
        print("...")
        break  # just first match for each pattern
    else:
        continue
    break

# Also search for "def analysis" more broadly
for m in re.finditer(r'(?:async\s+)?def\s+\w*analysis\w*', app_code, re.IGNORECASE):
    start = m.start()
    # Get 2000 chars from function start
    snippet = app_code[start:start+2500]
    print(f"\n=== function at char {start} ===")
    print(snippet[:2500])
    print("...")
