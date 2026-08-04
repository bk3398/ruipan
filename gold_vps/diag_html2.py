#!/usr/bin/env python3
"""Extract key JS functions from the VPS live HTML."""
import re

with open("/opt/ruipan/static/live-scores-preview-v6.html", "r", encoding="utf-8") as f:
    html = f.read()

# Extract switchDate function
m = re.search(r'function\s+switchDate\s*\([^)]*\)\s*\{', html)
if m:
    start = m.start()
    # find matching brace
    depth = 0
    i = m.end() - 1
    while i < len(html):
        if html[i] == '{': depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0: break
        i += 1
    print("=== switchDate ===")
    print(html[start:i+1][:2000])
    print()

# Extract loadMatches function
m = re.search(r'(?:async\s+)?function\s+loadMatches\s*\([^)]*\)\s*\{', html)
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
    print("=== loadMatches ===")
    print(html[start:i+1][:3000])
    print()

# Extract loadOddsData function
m = re.search(r'(?:async\s+)?function\s+loadOddsData\s*\([^)]*\)\s*\{', html)
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
    print("=== loadOddsData ===")
    print(html[start:i+1][:3000])
    print()

# Extract renderAnalysisTab function
m = re.search(r'function\s+renderAnalysisTab\s*\([^)]*\)\s*\{', html)
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
    print("=== renderAnalysisTab ===")
    print(html[start:i+1][:4000])
    print()

# Also check: what API endpoints does the JS call?
apis = re.findall(r"fetch\(\s*[`'\"]([^`'\"]+)[`'\"]", html)
print("=== All fetch URLs ===")
for a in apis:
    print(f"  {a}")

# Check for ANALYSIS_CACHE or similar
for pattern in ['ANALYSIS_CACHE', 'PRELOADED', 'analysis_cache', 'BK_ORDER', 'BK_NAMES']:
    idx = html.find(pattern)
    if idx >= 0:
        print(f"\n{pattern} found at char {idx}: ...{html[idx:idx+150]}...")
    else:
        print(f"\n{pattern}: NOT FOUND")
