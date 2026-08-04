#!/usr/bin/env python3
"""Dump lookupWR and calcUpperDivg full code, plus test with actual API data"""
import json

html_path = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
print("=" * 70)
print("calcUpperDivg + lookupWR + fmtWinRate (L2030-L2085):")
print("-" * 70)
for i in range(2029, min(2085, len(lines))):
    print(f"L{i+1}: {lines[i].rstrip()[:300]}")

print("=" * 70)
# Also dump the BACKTEST_WINRATE_LOOKUP loading code
print("BACKTEST_WINRATE_LOOKUP references:")
for i, line in enumerate(lines, 1):
    if 'BACKTEST_WINRATE_LOOKUP' in line or 'backtest_winrate' in line.lower():
        print(f"L{i}: {line.rstrip()[:250]}")

print("=" * 70)
# Check if lookup table is loaded
import os
lookup_path = "/opt/ruipan/static/backtest_winrate_lookup.json"
if os.path.exists(lookup_path):
    size = os.path.getsize(lookup_path)
    with open(lookup_path, 'r') as f:
        data = json.load(f)
    print(f"Lookup file: {lookup_path}")
    print(f"Size: {size} bytes")
    print(f"Top-level keys: {list(data.keys())[:10]}")
    for k in data:
        if isinstance(data[k], dict):
            subkeys = list(data[k].keys())[:5]
            print(f"  {k}: {len(data[k])} entries, first keys: {subkeys}")
            # Show one nested entry
            if subkeys:
                first = data[k][subkeys[0]]
                if isinstance(first, dict):
                    fk = list(first.keys())[:3]
                    print(f"    {subkeys[0]} -> {fk}")
                    if fk:
                        print(f"      {fk[0]} -> {first[fk[0]]}")
else:
    print(f"Lookup file NOT FOUND: {lookup_path}")
