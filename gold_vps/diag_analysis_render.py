#!/usr/bin/env python3
"""提取盘口解析Tab中即时列渲染和胜率相关代码"""
import re

HTML = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(HTML, "r") as f:
    lines = f.readlines()

# 找renderAnalysisTab函数
start = None
for i, line in enumerate(lines):
    if "function renderAnalysisTab" in line:
        start = i
        break

if start is None:
    print("未找到renderAnalysisTab")
    exit(1)

# 输出函数中关键部分
print(f"renderAnalysisTab 起始行: L{start+1}")
print("=" * 60)

# 找hasStarted相关、displayData相关、即时列渲染相关
keywords = [
    "hasStarted", "isMatchLive", "isFinished",
    "displayData", "displayPhase", "isDisplayLive",
    "actual_upper_odds", "upper",
    "hasInstantData",
    "winRateCell", "lookupWR", "fmtWinRate",
    "calcUpperDivg",
    "dWater", "dDiff", "dispWR",
]

for i in range(start, min(start + 300, len(lines))):
    line = lines[i]
    # 输出包含关键词的行及上下文
    for kw in keywords:
        if kw in line:
            print(f"L{i+1}: {line.rstrip()}")
            break

print("\n" + "=" * 60)
print("【即时列渲染区域 - hasStarted ? ... : '—'】")
print("=" * 60)
for i in range(start, min(start + 300, len(lines))):
    line = lines[i]
    if "hasStarted" in line and ("?" in line or "：" in line or "—" in line or "fmt" in line):
        # 输出前后3行上下文
        for j in range(max(0, i-2), min(len(lines), i+3)):
            marker = ">>>" if j == i else "   "
            print(f"{marker} L{j+1}: {lines[j].rstrip()}")
        print()

print("\n" + "=" * 60)
print("【数据归一化层 - normalizePhase / actual_upper】")
print("=" * 60)
for i, line in enumerate(lines):
    if "actual_upper_odds" in line or "normalizePhase" in line or "归一化" in line:
        print(f"L{i+1}: {line.rstrip()}")
