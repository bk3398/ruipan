#!/usr/bin/env python3
"""
Fix patch:
1. renderOddsQuickTab call missing tlData arg -> add it
2. "暂无皇冠/澳彩/威廉希尔初盘数据" -> generic "暂无数据"
"""
import re, sys

PATH = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(PATH, "r", encoding="utf-8") as f:
    html = f.read()

original = html

# Fix 1: ensure renderOddsQuickTab call passes tlData
# Match any call: renderOddsQuickTab(fid, oqData, match) with or without tlData
old_call = "renderOddsQuickTab(fid, oqData, match);"
new_call = "renderOddsQuickTab(fid, oqData, match, tlData);"
if old_call in html:
    html = html.replace(old_call, new_call, 1)
    print("Fixed renderOddsQuickTab call -> now passes tlData")
elif "renderOddsQuickTab(fid, oqData, match, tlData)" in html:
    print("renderOddsQuickTab call already passes tlData, skipping")
else:
    # Try regex fallback
    pat = re.compile(r'renderOddsQuickTab\(fid,\s*oqData,\s*match\s*\)')
    html, n = pat.subn("renderOddsQuickTab(fid, oqData, match, tlData)", html)
    if n:
        print(f"Fixed renderOddsQuickTab call via regex ({n} match)")
    else:
        print("WARNING: could not find renderOddsQuickTab call!")
        sys.exit(1)

# Fix 2: generic no-data text, do not expose algorithm source
old_text = "暂无皇冠/澳彩/威廉希尔初盘数据"
new_text = "暂无数据"
if old_text in html:
    html = html.replace(old_text, new_text)
    print(f"Replaced no-data text -> '{new_text}'")
else:
    print("No-data text already replaced or not found")

if html == original:
    print("No changes made.")
else:
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK - fix applied")
