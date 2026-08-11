#!/usr/bin/env python3
"""
锐盘 K线图加高 + 分歧度K线Y轴刻度加密 补丁
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
幂等修改 /opt/ruipan/app.py 内嵌的前端 JS：
  1. 赔率K线 canvas 高度 180 → 260，Y轴网格 4格 → 6格
  2. 战力EMA走势图(renderSparkline) 120×36 → 240×56，线条/影线加粗
运行后重启 ruipan-api。
"""
import re, sys, shutil, datetime, os

HTML_PATH = "/opt/ruipan/static/live-scores-preview-v6.html"

BAK = HTML_PATH + ".bak_klineheight_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# ── 替换规则：(模式, 替换, 说明) ──────────────────────────────
RULES = [
    # 1a. 赔率K线 canvas HTML 高度 180 → 260
    ('<canvas id="kline-canvas-${fid}" height="180"></canvas>',
     '<canvas id="kline-canvas-${fid}" height="260"></canvas>',
     "K线canvas HTML height 180→260"),

    # 1b. drawKline 内 const H = 180; → 260
    ("const H = 180;",
     "const H = 260;",
     "drawKline H 180→260"),

    # 1c. Y轴网格 4格 → 6格（循环上限）
    ("for(let i=0;i<=4;i++){",
     "for(let i=0;i<=6;i++){",
     "Y轴网格 4格→6格"),

    # 2a. renderSparkline 尺寸 120×36 → 240×56（多点分支）
    ("const w = 120, h = 36, cx = w/2, cy = h/2;",
     "const w = 240, h = 56, cx = w/2, cy = h/2;",
     "sparkline单点尺寸 120×36→240×56"),

    # 2b. renderSparkline 多点分支尺寸
    ("const w = 120, h = 36, pad = 2;",
     "const w = 240, h = 56, pad = 3;",
     "sparkline多点尺寸 120×36→240×56"),

    # 2c. 折线 stroke-width 1.5 → 2
    ('stroke-width="1.5"/>',
     'stroke-width="2"/>',
     "sparkline折线加粗 1.5→2"),
]

def main():
    try:
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"❌ 找不到 {HTML_PATH}")
        sys.exit(1)

    shutil.copy2(HTML_PATH, BAK)
    print(f"📦 备份 → {BAK}")

    changed = 0
    for old, new, desc in RULES:
        if new in html and old not in html:
            print(f"⏭️  已应用: {desc}")
            continue
        if old in html:
            html = html.replace(old, new, 1)
            print(f"✅ {desc}")
            changed += 1
        else:
            print(f"⚠️  未找到锚点(可能已变更): {desc}")

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n应用 {changed} 处修改。重启服务： systemctl restart ruipan-api")

if __name__ == "__main__":
    main()
