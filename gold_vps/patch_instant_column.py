#!/usr/bin/env python3
"""
Fix: 盘口解析即时列在scheduled状态下全空
根因: L2184-2187 用 hasStarted 门控, scheduled=false 导致即使有live数据也显示'—'
修复: 改为 hasInstantData (基于displayData数据存在性)
同时dump完整renderAnalysisTab模板确认初盘胜率是否同样被门控
"""
import re, shutil, os, sys
from datetime import datetime

html_path = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

print(f"File: {html_path}")
print(f"Total lines: {len(lines)}")
print(f"File size: {sum(len(l) for l in lines)} bytes")
print("=" * 70)

# Dump L2080-2210 (0-indexed: 2079-2209)
print("BEFORE FIX - renderAnalysisTab (L2080-L2210):")
print("-" * 70)
for i in range(2079, min(2210, len(lines))):
    print(f"L{i+1}: {lines[i].rstrip()[:250]}")
print("=" * 70)

# Backup
bak = f"{html_path}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy2(html_path, bak)
print(f"Backup: {bak}")

changes = 0

# Fix 1: Add hasInstantData after "const displayData = liv || ter;"
for i, line in enumerate(lines):
    if 'const displayData = liv || ter;' in line:
        indent = line[:len(line) - len(line.lstrip())]
        new_line = line.rstrip() + '\n'
        new_line += f"{indent}const hasInstantData = !!(displayData && displayData.handicap != null && displayData.actual_upper_odds != null);\n"
        lines[i] = new_line
        changes += 1
        print(f"✅ L{i+1}: Added hasInstantData after displayData")
        break
else:
    print("❌ Could not find 'const displayData = liv || ter;'")
    sys.exit(1)

# Fix 2: Replace hasStarted in instant column cells (L2184-2187 area)
# These are the 4 lines: handicap, water, divg, winrate
replacements = [
    ("${hasStarted ? fmtUpperHdp(displayData.handicap) : '—'}",
     "${hasInstantData ? fmtUpperHdp(displayData.handicap) : '—'}"),
    ("${hasStarted ? dWater : '—'}",
     "${hasInstantData ? dWater : '—'}"),
    ("${hasStarted ? dDiff : '—'}",
     "${hasInstantData ? dDiff : '—'}"),
    ("${hasStarted ? dispWR : '—'}",
     "${hasInstantData ? dispWR : '—'}"),
]

for old, new in replacements:
    found = False
    for i, line in enumerate(lines):
        if old in line:
            lines[i] = line.replace(old, new)
            changes += 1
            print(f"✅ L{i+1}: {old.strip()[:60]} → hasInstantData")
            found = True
            break
    if not found:
        print(f"⚠️  Not found: {old[:60]}")

# Check: is there a similar gate on initial win rate?
# Look for iniWR usage in template
print("-" * 70)
print("Checking initial win rate rendering (iniWR usage):")
for i, line in enumerate(lines):
    if 'iniWR' in line:
        print(f"  L{i+1}: {line.rstrip()[:200]}")

# Check: any other hasStarted gates in the analysis template?
print("-" * 70)
print("Remaining hasStarted references in renderAnalysisTab (L2084-L2250):")
for i in range(2083, min(2250, len(lines))):
    if 'hasStarted' in lines[i]:
        print(f"  L{i+1}: {lines[i].rstrip()[:200]}")

# Write
new_content = ''.join(lines)
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

new_size = len(new_content.encode('utf-8'))
old_size = os.path.getsize(bak)
print("=" * 70)
print(f"Changes applied: {changes}")
print(f"File size: {old_size} → {new_size} bytes (diff: {new_size - old_size})")

# Dump AFTER
print("=" * 70)
print("AFTER FIX - renderAnalysisTab (L2140-L2200):")
print("-" * 70)
with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
    after_lines = f.readlines()
for i in range(2139, min(2200, len(after_lines))):
    print(f"L{i+1}: {after_lines[i].rstrip()[:250]}")

print("=" * 70)
print("Done! No API restart needed (static HTML file).")
print("Hard refresh browser: Ctrl+Shift+R")
