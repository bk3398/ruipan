#!/usr/bin/env python3
"""直接按行号提取app.py关键端点代码"""
import os

APP = "/opt/ruipan/app.py"

with open(APP, "r") as f:
    lines = f.readlines()

total = len(lines)
print(f"app.py 总行数: {total}")
print("=" * 60)

# 端点范围（从路由装饰器到下一个路由装饰器前）
endpoints = [
    ("odds-timeline", 130, 177),
    ("analysis", 178, 375),
    ("odds-quick", 724, 763),
]

for name, start, end in endpoints:
    print(f"\n{'='*60}")
    print(f"【{name} 端点 L{start}-L{end}】")
    print(f"{'='*60}")
    for i in range(start - 1, min(end, total)):
        print(f"L{i+1}: {lines[i]}", end="")

# 也提取today端点看数据结构
print(f"\n{'='*60}")
print(f"【matches/today 端点 L73-L129】")
print(f"{'='*60}")
for i in range(72, min(129, total)):
    print(f"L{i+1}: {lines[i]}", end="")
