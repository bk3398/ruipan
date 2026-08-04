import re, sys

filepath = "/opt/ruipan/static/live-scores-preview-v6.html"

try:
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
except Exception as e:
    print(f"ERROR reading file: {e}")
    sys.exit(1)

print(f"File: {filepath}")
print(f"Total lines: {len(lines)}")
print(f"File size: {sum(len(l) for l in lines)} bytes")
print("=" * 70)

keywords = [
    'hasStarted', 'isMatchLive', 'displayData', 'displayPhase',
    'winRateCell', 'lookupWR', 'calcUpperDivg', 'actual_upper_odds',
    'normalizePhase', 'renderAnalysisTab', 'phases.live', 'phases.initial',
    'phases.closing', 'liv || ter', '? ter : liv'
]

found_any = False
for i, line in enumerate(lines, 1):
    for kw in keywords:
        if kw in line:
            print(f"L{i}: {line.rstrip()[:250]}")
            found_any = True
            break

if not found_any:
    print("NO KEYWORDS FOUND - broader search...")
    for i, line in enumerate(lines, 1):
        ll = line.lower()
        if 'hasstarted' in ll or 'displaydata' in ll or 'winrate' in ll or 'lookupwr' in ll:
            print(f"L{i}: {line.rstrip()[:250]}")
            found_any = True

if not found_any:
    print("Still nothing. Searching for analysis/render/tab functions...")
    for i, line in enumerate(lines, 1):
        ll = line.lower()
        if 'analysis' in ll and ('function' in ll or 'render' in ll or 'tab' in ll):
            print(f"L{i}: {line.rstrip()[:250]}")

print("=" * 70)
print("Done.")
