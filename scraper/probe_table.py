#!/usr/bin/env python3
"""Dump raw HTML of the team stats table to understand exact structure."""
import urllib.request
import re
import sys

SID = int(sys.argv[1]) if len(sys.argv) > 1 else 3021929
URL = f"https://zq.titan007.com/analysis/{SID}.htm"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

req = urllib.request.Request(URL, headers={"User-Agent": UA})
resp = urllib.request.urlopen(req, timeout=15)
html = resp.read().decode("utf-8", errors="replace")

# Get hometeam/guestteam values
ht_m = re.search(r"var\s+hometeam\s*=\s*['\"]([^'\"]+)['\"]", html)
at_m = re.search(r"var\s+guestteam\s*=\s*['\"]([^'\"]+)['\"]", html)
print(f"hometeam var = {ht_m.group(1) if ht_m else 'NOT FOUND'}")
print(f"guestteam var = {at_m.group(1) if at_m else 'NOT FOUND'}")

# Find all tables and dump the ones containing team names
tables = re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL)
print(f"\nTotal tables: {len(tables)}")

for i, tbl in enumerate(tables):
    text = re.sub(r'<[^>]+>', ' ', tbl)
    text = re.sub(r'\s+', ' ', text).strip()
    if 'SKA' in text or '哈巴' in text or '科斯特' in text:
        if any(kw in text for kw in ['賽', '勝', '積分', '全場']):
            print(f"\n{'='*60}")
            print(f"=== TABLE {i+1} (contains team name + stats keywords) ===")
            print(f"{'='*60}")
            # Print raw HTML, truncate if too long
            print(tbl[:5000])
            print(f"\n--- Text version ---")
            print(text[:1000])
            print()

# Also specifically test: what does our cell extraction produce for table 1?
print("\n\n=== SIMULATING CELL EXTRACTION FOR TABLE 1 ===")
for i, tbl in enumerate(tables):
    text = re.sub(r'<[^>]+>', ' ', tbl)
    text = re.sub(r'\s+', ' ', text).strip()
    if 'SKA' in text and '全場' in text and '賽' in text:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
        print(f"Table {i+1}: {len(rows)} rows")
        for j, row in enumerate(rows):
            cells_raw = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
            cells = []
            for c in cells_raw:
                txt = re.sub(r'<[^>]+>', '', c)
                txt = txt.replace('&nbsp;', ' ').strip()
                cells.append(txt)
            print(f"  Row {j}: {len(cells)} cells -> {cells}")
        break
