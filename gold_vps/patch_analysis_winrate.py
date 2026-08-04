#!/usr/bin/env python3
"""
patch_analysis_winrate.py
修复renderAnalysisTab中完场赛事取closing(不存在)导致胜率和即时列空白。
统一用live(最后一笔即时数据)作为终盘，胜率lookup用live phase。
"""
import re, shutil, datetime

HTML_PATH = "/opt/ruipan/static/live-scores-preview-v6.html"
BACKUP_PATH = HTML_PATH + f".bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

shutil.copy2(HTML_PATH, BACKUP_PATH)
print(f"备份: {BACKUP_PATH}")

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

original_len = len(html)
patches = 0

# Fix 1: renderAnalysisTab displayData - use liv instead of ter for finished matches
old1 = "const displayData = (hasStarted && !isMatchLive) ? ter : liv;"
new1 = "const displayData = liv || ter;  // 完场用最后live作为终盘"
if old1 in html:
    html = html.replace(old1, new1)
    patches += 1
    print("✅ displayData: closing → live")
else:
    print("⚠️ displayData pattern not found")

# Fix 2: win rate lookup phase - use 'live' not 'closing'
old2 = "const displayPhase = (hasStarted && !isMatchLive) ? 'closing' : 'live';"
new2 = "const displayPhase = 'live';  // 终盘=最后live, 用live phase lookup"
if old2 in html:
    html = html.replace(old2, new2)
    patches += 1
    print("✅ displayPhase: closing → live")
else:
    print("⚠️ displayPhase pattern not found")

# Write
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

new_len = len(html)
print(f"\n文件大小: {original_len} → {new_len} bytes (diff: {new_len-original_len})")
print(f"应用补丁数: {patches}")
print("✅ 完成！Ctrl+Shift+R 强制刷新")

# Also check: how many lookup entries have sample >= 5?
print("\n" + "="*60)
print("【胜率覆盖率分析】")
lookup_match = re.search(r'const BACKTEST_WINRATE_LOOKUP\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL)
if lookup_match:
    import json
    try:
        lookup = json.loads(lookup_match.group(1))
        for phase in ['initial', 'live', 'closing']:
            if phase in lookup:
                total = len(lookup[phase])
                qualified = sum(1 for v in lookup[phase].values() if v.get('sample', 0) >= 5)
                print(f"  {phase}: {total} 条, 其中样本≥5: {qualified} 条 ({qualified*100//total}%)")
    except:
        # Fallback: count with regex
        lookup_str = lookup_match.group(1)
        for phase in ['initial', 'live', 'closing']:
            pm = re.search(rf'"{phase}"\s*:\s*\{{(.*?)\}}(?:\s*,\s*"|\s*\}})', lookup_str, re.DOTALL)
            if pm:
                section = pm.group(1)
                total = section.count('"sample"')
                # Count sample >= 5
                samples = re.findall(r'"sample":\s*(\d+)', section)
                qualified = sum(1 for s in samples if int(s) >= 5)
                print(f"  {phase}: {total} 条, 其中样本≥5: {qualified} 条")
