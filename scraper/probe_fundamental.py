#!/usr/bin/env python3
"""Probe the analysis page to understand why standings and team_stats aren't parsed."""
import urllib.request
import re
import sys
import json

SID = int(sys.argv[1]) if len(sys.argv) > 1 else 3021929
URL = f"https://zq.titan007.com/analysis/{SID}.htm"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

req = urllib.request.Request(URL, headers={"User-Agent": UA})
resp = urllib.request.urlopen(req, timeout=15)
html = resp.read().decode("utf-8", errors="replace")

print(f"Page size: {len(html)} chars")
print()

# 1. Look for standings arrays: [[number,number,'...',number
print("=== 1. Searching for [[NUMBER,NUMBER,'...',NUMBER patterns ===")
candidates = list(re.finditer(r'\[\[(\d+),\d+,', html))
print(f"Found {len(candidates)} [[N,N, candidates")
for i, m in enumerate(candidates):
    start = m.start()
    # Extract a context window
    context_before = html[max(0, start-80):start]
    # Extract 300 chars after
    snippet = html[start:start+300]
    print(f"\n--- Candidate {i+1} at pos {start} ---")
    print(f"Context before: ...{context_before[-60:]}")
    print(f"First 300 chars: {snippet}")

# 2. Search for team stats tables
print("\n\n=== 2. Searching for team stats tables ===")
tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
print(f"Found {len(tables)} <table> blocks")
for i, tbl in enumerate(tables):
    # Get rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
    if not rows:
        continue
    # Check if table contains Chinese team name or stats keywords
    text = re.sub(r'<[^>]+>', ' ', tbl)
    text = re.sub(r'\s+', ' ', text).strip()
    if any(kw in text for kw in ['勝', '總', '積分', '排名', '近6', 'SKA', '哈巴', '科斯特']):
        print(f"\n--- Table {i+1}: {len(rows)} rows ---")
        print(f"First 500 chars: {text[:500]}")

# 3. Search for the specific region near team stats
print("\n\n=== 3. Searching for 'SKA' or team name in HTML ===")
for keyword in ['SKA', '哈巴', '科斯特', '斯巴達', '斯巴达']:
    positions = [m.start() for m in re.finditer(keyword, html)]
    print(f"'{keyword}': found at {len(positions)} positions")
    if positions:
        for pos in positions[:3]:
            snippet = html[max(0,pos-30):pos+100]
            print(f"  pos {pos}: ...{snippet}...")

# 4. Look for var declarations near standings
print("\n\n=== 4. Searching for 'var' near 'Score' or 'Integral' or 'rank' ===")
for keyword in ['ScoreStr', 'Integral', 'rankStr', 'rank', 'standings', '積分', '积分']:
    for m in re.finditer(keyword, html, re.IGNORECASE):
        pos = m.start()
        context = html[max(0,pos-50):pos+100]
        print(f"  '{keyword}' at {pos}: ...{context[:150]}...")
        break  # just first occurrence

# 5. Dump all var declarations
print("\n\n=== 5. All 'var xxx =' declarations ===")
vars_found = re.findall(r'var\s+(\w+)\s*=', html)
print(f"Found {len(vars_found)} vars: {vars_found}")

# 6. Specifically look for arrays assigned to vars (rank/score/table related)
print("\n\n=== 6. Arrays assigned to variables ===")
for m in re.finditer(r'(?:var\s+)?(\w+)\s*=\s*(\[\[)', html):
    var_name = m.group(1)
    start = m.start(2)
    # Extract first 200 chars
    snippet = html[start:start+200]
    print(f"  {var_name} = {snippet[:150]}...")

print("\n\nDone.")
