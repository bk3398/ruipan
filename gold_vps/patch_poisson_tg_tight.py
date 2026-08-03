#!/usr/bin/env python3
"""
Tighten total goals bar chart: bars adjacent with tiny gap,
percentage label on top of each bar, goal label below.
"""
import sys

PATH = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(PATH, "r", encoding="utf-8") as f:
    html = f.read()

# --- Replace CSS ---
old_css = """.ps-tg-title{font-size:12px;font-weight:600;color:var(--text-primary);margin-bottom:6px;}
.ps-tg-row{display:flex;align-items:flex-end;gap:5px;height:70px;padding:6px 4px 0;margin-top:8px;border-top:1px solid #e8ecf1;}
.ps-tg-col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;}
.ps-tg-bar{width:70%;max-width:28px;min-height:3px;background:linear-gradient(180deg,#0891b2,#06b6d4);border-radius:3px 3px 0 0;transition:height .3s ease;}
.ps-tg-val{font-size:9px;color:var(--text-secondary);margin-top:2px;line-height:1;}
.ps-tg-g{font-size:10px;font-weight:600;color:var(--text-muted);margin-top:1px;}"""

new_css = """.ps-tg-title{font-size:12px;font-weight:600;color:var(--text-primary);margin:10px 0 4px;}
.ps-tg-row{display:flex;align-items:stretch;gap:2px;height:90px;padding:14px 0 0;margin-top:8px;border-top:1px solid #e8ecf1;}
.ps-tg-col{flex:1;display:flex;flex-direction:column;align-items:stretch;justify-content:flex-end;position:relative;min-width:0;}
.ps-tg-bar-wrap{display:flex;align-items:flex-end;justify-content:center;flex:1;position:relative;}
.ps-tg-bar{width:100%;min-height:3px;background:linear-gradient(180deg,#22d3ee,#0891b2);border-radius:2px 2px 0 0;transition:height .3s ease;}
.ps-tg-val{position:absolute;top:-14px;left:50%;transform:translateX(-50%);font-size:10px;font-weight:600;color:#0891b2;line-height:1;white-space:nowrap;}
.ps-tg-g{font-size:10px;font-weight:600;color:var(--text-muted);text-align:center;margin-top:3px;}"""

if old_css not in html:
    print("ERROR: old tg CSS not found")
    sys.exit(1)
html = html.replace(old_css, new_css, 1)
print("Replaced tg CSS")

# --- Replace render template for columns ---
old_tpl = """    <div class="ps-tg-row">${po.totalGoals.map(([g,p])=>{
      const h = Math.round(Math.min(100, Math.max(4, p*100*4)));
      return `<div class="ps-tg-col"><div class="ps-tg-bar" style="height:${h}%"></div><div class="ps-tg-val">${pct(p)}</div><div class="ps-tg-g">${g}</div></div>`;
    }).join('')}</div>"""

new_tpl = """    <div class="ps-tg-row">${po.totalGoals.map(([g,p])=>{
      const h = Math.round(Math.min(100, Math.max(4, p*100*4)));
      const gl = g==='7+' ? '7+' : g+'球';
      return `<div class="ps-tg-col"><div class="ps-tg-bar-wrap"><div class="ps-tg-val">${pct(p)}</div><div class="ps-tg-bar" style="height:${h}%"></div></div><div class="ps-tg-g">${gl}</div></div>`;
    }).join('')}</div>"""

if old_tpl not in html:
    print("ERROR: old tg render template not found")
    sys.exit(1)
html = html.replace(old_tpl, new_tpl, 1)
print("Replaced tg render template")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(html)

print("OK - tight bar chart applied")
