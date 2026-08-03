#!/usr/bin/env python3
"""
Move total goals bar to below the score distribution groups.
"""
import sys

PATH = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(PATH, "r", encoding="utf-8") as f:
    html = f.read()

old = """    <div class="ps-tg-title">总进球分布</div>
    <div class="ps-tg-row">${po.totalGoals.map(([g,p])=>{
      const h = Math.round(Math.min(100, Math.max(4, p*100*4)));
      return `<div class="ps-tg-col"><div class="ps-tg-bar" style="height:${h}%"></div><div class="ps-tg-val">${pct(p)}</div><div class="ps-tg-g">${g}</div></div>`;
    }).join('')}</div>
    ${group('主胜比分', po.homeScores, 'home')}
    ${group('平局比分', po.drawScores, 'draw')}
    ${group('客胜比分', po.awayScores, 'away')}"""

new = """    ${group('主胜比分', po.homeScores, 'home')}
    ${group('平局比分', po.drawScores, 'draw')}
    ${group('客胜比分', po.awayScores, 'away')}
    <div class="ps-tg-title">总进球分布</div>
    <div class="ps-tg-row">${po.totalGoals.map(([g,p])=>{
      const h = Math.round(Math.min(100, Math.max(4, p*100*4)));
      return `<div class="ps-tg-col"><div class="ps-tg-bar" style="height:${h}%"></div><div class="ps-tg-val">${pct(p)}</div><div class="ps-tg-g">${g}</div></div>`;
    }).join('')}</div>"""

if old not in html:
    print("ERROR: target block not found")
    sys.exit(1)

html = html.replace(old, new, 1)

# Also adjust CSS: move border-bottom to border-top for the tg-row, tweak margin
old_css = ".ps-tg-row{display:flex;align-items:flex-end;gap:5px;height:70px;padding:6px 4px 0;margin-bottom:12px;border-bottom:1px solid #e8ecf1;}"
new_css = ".ps-tg-row{display:flex;align-items:flex-end;gap:5px;height:70px;padding:6px 4px 0;margin-top:8px;border-top:1px solid #e8ecf1;}"
if old_css in html:
    html = html.replace(old_css, new_css, 1)
    print("Adjusted tg-row CSS (top border)")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(html)

print("OK - total goals moved below score distribution")
