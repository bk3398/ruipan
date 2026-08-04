#!/usr/bin/env python3
"""Check the live HTML file on VPS for PRELOADED dates and analysis rendering."""
import re, json

# Read the live HTML
with open("/opt/ruipan/static/live-scores-preview-v6.html", "r", encoding="utf-8") as f:
    html = f.read()

print(f"HTML size: {len(html)} bytes")

# Find PRELOADED
m = re.search(r'const PRELOADED\s*=\s*(\{.*?\});\s*(?:const|let|var|function|//|\n)', html, re.DOTALL)
if m:
    try:
        preloaded = json.loads(m.group(1))
        print(f"PRELOADED dates: {sorted(preloaded.keys())}")
        for d in sorted(preloaded.keys()):
            data = preloaded[d]
            total = data.get("summary", {}).get("total", len(data.get("data", [])))
            print(f"  {d}: {total} matches")
    except json.JSONDecodeError as e:
        print(f"PRELOADED JSON parse error: {e}")
        # Try to find date keys
        dates = re.findall(r'"(2026-\d{2}-\d{2})"', m.group(1)[:2000])
        print(f"  dates found in first 2000 chars: {dates[:10]}")
else:
    print("PRELOADED not found!")
    # Search for it differently
    idx = html.find("PRELOADED")
    if idx >= 0:
        print(f"  PRELOADED found at char {idx}")
        print(f"  context: {html[idx:idx+200]}")

# Find TODAY_DATE
m2 = re.search(r'(?:const|let|var)\s+TODAY_DATE\s*=\s*["\']([^"\']+)["\']', html)
if m2:
    print(f"\nTODAY_DATE: {m2.group(1)}")
else:
    print("\nTODAY_DATE not found directly, searching...")
    for m3 in re.finditer(r'TODAY_DATE[^;]*;', html):
        print(f"  {m3.group()[:100]}")

# Find currentDate initialization
m4 = re.search(r'(?:const|let|var)\s+currentDate\s*=\s*([^;]+);', html)
if m4:
    print(f"currentDate init: {m4.group(1)[:100]}")

# Check if ANALYSIS_CACHE exists and what fids it has
m5 = re.search(r'const ANALYSIS_CACHE\s*=\s*(\{.*?\});\s*(?:const|let|var|function)', html, re.DOTALL)
if m5:
    try:
        ac = json.loads(m5.group(1))
        print(f"\nANALYSIS_CACHE fids: {sorted(ac.keys())[:20]}")
        print(f"  total: {len(ac)} entries")
    except:
        print("\nANALYSIS_CACHE found but parse error")
        fids = re.findall(r'"(\d{4,})"', m5.group(1)[:5000])
        print(f"  fids in first 5000 chars: {fids[:20]}")

# Check the date nav - what dates are available
m6 = re.search(r'(?:const|let|var)\s+DATES\s*=\s*(\[[^\]]+\])', html)
if m6:
    print(f"\nDATES array: {m6.group(1)[:200]}")

# Look for date nav generation
m7 = re.search(r'function\s+initDateNav[^{]*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}', html, re.DOTALL)
if m7:
    print(f"\ninitDateNav snippet (first 500):\n{m7.group(0)[:500]}")
