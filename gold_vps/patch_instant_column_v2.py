#!/usr/bin/env python3
"""
Fix v2: 即时列 hasStarted → hasInstantData
v1只加了变量但替换没命中(实际是<span class="phase-na">—</span>不是纯'—')
"""
import shutil, os, sys
from datetime import datetime

html_path = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

print(f"File size before: {len(content.encode('utf-8'))} bytes")

# Verify hasInstantData exists from v1
if 'hasInstantData' not in content:
    print("❌ hasInstantData not found - v1 didn't apply correctly")
    sys.exit(1)
print("✅ hasInstantData variable exists")

changes = 0

# The 4 lines use pattern: ${hasStarted ? VALUE : '<span class="phase-na">—</span>'}
# Replace hasStarted with hasInstantData in these 4 specific contexts
replacements = [
    # L2185: handicap
    ('${hasStarted ? fmtUpperHdp(displayData.handicap) : \'<span class="phase-na">—</span>\'}',
     '${hasInstantData ? fmtUpperHdp(displayData.handicap) : \'<span class="phase-na">—</span>\'}'),
    # L2186: water
    ('${hasStarted ? dWater : \'<span class="phase-na">—</span>\'}',
     '${hasInstantData ? dWater : \'<span class="phase-na">—</span>\'}'),
    # L2187: divg
    ('${hasStarted ? dDiff : \'<span class="phase-na">—</span>\'}',
     '${hasInstantData ? dDiff : \'<span class="phase-na">—</span>\'}'),
    # L2188: winrate
    ('${hasStarted ? dispWR : \'<span class="phase-na">—</span>\'}',
     '${hasInstantData ? dispWR : \'<span class="phase-na">—</span>\'}'),
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new, 1)
        changes += 1
        print(f"✅ Replaced: {old[:70]}...")
    else:
        # Try a more flexible approach: find hasStarted in the analysis tab area
        print(f"⚠️  Exact match failed for: {old[:60]}...")

# If exact match failed, try regex approach for remaining hasStarted in phase-live cells
if changes < 4:
    import re
    # Find all occurrences of hasStarted within phase-live <td> tags
    pattern = r'(<td class="phase-live[^"]*"[^>]*>)\$\{hasStarted \?'
    matches = list(re.finditer(pattern, content))
    print(f"Regex found {len(matches)} remaining hasStarted in phase-live cells")
    for m in matches:
        content = content[:m.start()] + m.group(1) + '${hasInstantData ?' + content[m.end():]
        changes += 1
        print(f"✅ Regex replaced hasStarted → hasInstantData at position {m.start()}")

# Write
bak = f"{html_path}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy2(html_path, bak)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

new_size = len(content.encode('utf-8'))
print("=" * 50)
print(f"Backup: {bak}")
print(f"Changes: {changes}")
print(f"File size: {os.path.getsize(bak)} → {new_size} bytes")

# Verify: show remaining hasStarted in analysis area
lines = content.split('\n')
print("=" * 50)
print("Remaining hasStarted in renderAnalysisTab:")
in_func = False
for i, line in enumerate(lines, 1):
    if 'function renderAnalysisTab' in line:
        in_func = True
    if in_func and 'hasStarted' in line:
        print(f"  L{i}: {line.strip()[:150]}")
    if in_func and line.strip().startswith('}') and i > 2100:
        # Check if this is the end of function
        if 'renderAnalysisTab' not in line:
            in_func = False

print("=" * 50)
print("Done! Hard refresh: Ctrl+Shift+R")
