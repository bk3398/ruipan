#!/usr/bin/env python3
"""
patch_finished_odds.py
修复完场赛事亚盘/欧赔表格空白：
前端 isFinished 时取 bk.closing（不存在），改为取 bk.live（我们抓取的最后即时数据=终盘）。
同时提取胜率相关函数用于诊断。
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

# Fix: Both renderAsianTable and renderEuroTable use the same line
# isFinished ? ter (closing, doesn't exist in DB) : liv (live, our scraped data)
# Change to always use liv, falling back to ter if no live data
old_line = "const instantSrc = isFinished ? ter : liv;"
new_line = "const instantSrc = liv || ter;  // 终盘用我们抓取的最后即时live数据"
count = html.count(old_line)
if count > 0:
    html = html.replace(old_line, new_line)
    patches += count
    print(f"✅ 修复 {count} 处 instantSrc: closing → live (亚盘+欧赔终盘用我们抓取的最后即时数据)")
else:
    print("⚠️ instantSrc pattern not found")

# Write patched file
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

new_len = len(html)
print(f"\n文件大小: {original_len} → {new_len} bytes (diff: {new_len-original_len})")
print(f"应用补丁数: {patches}")
print("✅ 补丁完成！Ctrl+Shift+R 强制刷新查看完场赛事赔率")

# Now extract win rate functions for diagnosis
print("\n" + "="*60)
print("【胜率诊断：提取关键函数】")

# Extract hdpNameV3
for func_name in ['hdpNameV3', 'waterBinV3', 'divgBinV3', 'lookupWR']:
    pattern = rf'function\s+{func_name}\s*\([^)]*\)\s*\{{'
    m = re.search(pattern, html)
    if m:
        start = m.start()
        depth = 0
        i = m.end() - 1
        while i < len(html):
            if html[i] == '{': depth += 1
            elif html[i] == '}':
                depth -= 1
                if depth == 0: break
            i += 1
        func_text = html[start:i+1]
        print(f"\n--- {func_name} ---")
        print(func_text)
    else:
        print(f"\n--- {func_name}: NOT FOUND ---")

# Extract the code around L2157 where lookupWR is called
print("\n" + "="*60)
print("【lookupWR调用上下文 (L2140-L2180)】")
lines = html.split('\n')
for i in range(max(0, 2139), min(len(lines), 2185)):
    print(f"L{i+1}: {lines[i]}")

# Count lookup entries per phase
print("\n" + "="*60)
print("【lookup表各phase条目数】")
lookup_match = re.search(r'const BACKTEST_WINRATE_LOOKUP\s*=\s*(\{.*?\});', html, re.DOTALL)
if lookup_match:
    lookup_str = lookup_match.group(1)
    # Count top-level keys by finding "phase_name":{ patterns
    for phase in ['initial', 'live', 'closing', 'linkage_unchanged', 'linkage_changed']:
        # Count entries in each phase by counting "win_rate_upper" occurrences after the phase key
        phase_pattern = rf'"{phase}"\s*:\s*\{{(.*?)\}}\s*(?:"|linkage|$)'
        pm = re.search(phase_pattern, lookup_str, re.DOTALL)
        if pm:
            entry_count = pm.group(1).count('win_rate_upper')
            print(f"  {phase}: {entry_count} 条记录")
        else:
            print(f"  {phase}: not found or empty")
else:
    print("  BACKTEST_WINRATE_LOOKUP not found in HTML!")
