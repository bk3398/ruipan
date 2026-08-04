#!/usr/bin/env python3
"""Dump full analysis JSON for a match that HAS bookmakers data."""
import json, urllib.request

def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())

# Get today's matches
data = fetch("http://localhost:8000/api/v1/matches/today")
matches = data.get("data", [])
print(f"Total matches: {len(matches)}")

# Find first match with analysis data
target = None
for m in matches:
    fid = m.get("fixture_id")
    an = fetch(f"http://localhost:8000/api/v1/matches/{fid}/analysis")
    bk_count = len(an.get("bookmakers", {}))
    print(f"  {fid}: {m.get('home_team')} vs {m.get('away_team')} -> {bk_count} bookmakers, phases={an.get('available_phases')}")
    if bk_count > 0 and target is None:
        target = fid
        target_data = an

if target:
    print(f"\n=== Full analysis for fid={target} ===")
    print(json.dumps(target_data, ensure_ascii=False, indent=2, default=str)[:4000])
    
    # Also check one bookmaker's phase structure in detail
    bks = target_data.get("bookmakers", {})
    for bk_name, bk_data in bks.items():
        print(f"\n--- bookmaker: {bk_name} ---")
        print(json.dumps(bk_data, ensure_ascii=False, indent=2, default=str)[:1500])
        break  # just first one
