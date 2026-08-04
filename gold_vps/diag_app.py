#!/usr/bin/env python3
"""提取app.py中odds-timeline和odds-quick端点代码"""
import re

APP_PATH = "/opt/ruipan/app.py"

with open(APP_PATH, 'r') as f:
    content = f.read()

lines = content.split('\n')
print(f"app.py 总行数: {len(lines)}\n")

# 找所有路由定义
print("="*60)
print("【所有API路由】")
for i, line in enumerate(lines):
    if '@app.' in line or '@router.' in line:
        print(f"  L{i+1}: {line.strip()}")

# 找odds-timeline端点
print("\n" + "="*60)
print("【odds-timeline端点代码】")
for i, line in enumerate(lines):
    if 'odds-timeline' in line or 'odds_timeline' in line:
        # 打印从这里开始的80行或到下一个@app
        start = max(0, i-2)
        end = min(len(lines), i+80)
        for j in range(start, end):
            if j > start and ('@app.' in lines[j] or '@router.' in lines[j]):
                end = j
                break
        for j in range(start, end):
            print(f"L{j+1}: {lines[j]}")
        print()
        break

# 找odds-quick端点
print("="*60)
print("【odds-quick端点代码】")
for i, line in enumerate(lines):
    if 'odds-quick' in line or 'odds_quick' in line:
        start = max(0, i-2)
        end = min(len(lines), i+80)
        for j in range(start, end):
            if j > start and ('@app.' in lines[j] or '@router.' in lines[j]):
                end = j
                break
        for j in range(start, end):
            print(f"L{j+1}: {lines[j]}")
        print()
        break

# 找analysis端点
print("="*60)
print("【analysis端点代码（前100行）】")
for i, line in enumerate(lines):
    if '/analysis' in line and 'def ' not in line:
        start = max(0, i-2)
        end = min(len(lines), i+100)
        for j in range(start, end):
            if j > start and ('@app.' in lines[j] or '@router.' in lines[j]):
                end = j
                break
        for j in range(start, end):
            print(f"L{j+1}: {lines[j]}")
        print()
        break

# 搜索数据库查询odds的代码
print("="*60)
print("【odds_asia/odds_euro查询代码】")
for i, line in enumerate(lines):
    if ('odds_asia' in line or 'odds_euro' in line) and ('SELECT' in line.upper() or 'select' in line or 'query' in line or 'fetch' in line):
        start = max(0, i-3)
        end = min(len(lines), i+10)
        for j in range(start, end):
            print(f"L{j+1}: {lines[j]}")
        print()
