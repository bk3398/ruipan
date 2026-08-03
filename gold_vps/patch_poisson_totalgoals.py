#!/usr/bin/env python3
"""
Add total goals distribution bar to poisson tab.
- poissonCalc returns totalGoals array
- renderOddsQuickTab inserts total goals bar after meta line
- CSS for .ps-tg-*
"""
import re, sys

PATH = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ---------- 1. Add totalGoals to poissonCalc return ----------
old_ret = "  return { lh:bestLH, la:bestLA, p1x2:[ph,pd,pa], homeScores, drawScores, awayScores };"
new_ret = """  // total goals distribution
  const totalGoals = [];
  for (let t=0; t<=7; t++) {
    let s=0;
    cells.forEach(([h,a,p])=>{ if(h+a===t) s+=p; });
    totalGoals.push([t, s]);
  }
  let tgOther = 1 - totalGoals.reduce((s,x)=>s+x[1],0);
  if (tgOther > 0.0001) totalGoals.push(['7+', tgOther]);
  return { lh:bestLH, la:bestLA, p1x2:[ph,pd,pa], homeScores, drawScores, awayScores, totalGoals };"""

if old_ret in html:
    html = html.replace(old_ret, new_ret, 1)
    print("Added totalGoals to poissonCalc return")
else:
    print("ERROR: poissonCalc return line not found")
    sys.exit(1)

# ---------- 2. Insert total goals bar in render template ----------
old_meta = """    <div class="ps-meta">λ主 ${po.lh.toFixed(2)} · λ客 ${po.la.toFixed(2)} &nbsp;|&nbsp; 欧赔 ${oh.toFixed(2)} / ${od.toFixed(2)} / ${oa.toFixed(2)}</div>
    ${group('主胜比分', po.homeScores, 'home')}"""

new_meta = """    <div class="ps-meta">λ主 ${po.lh.toFixed(2)} · λ客 ${po.la.toFixed(2)} &nbsp;|&nbsp; 欧赔 ${oh.toFixed(2)} / ${od.toFixed(2)} / ${oa.toFixed(2)}</div>
    <div class="ps-tg-title">总进球分布</div>
    <div class="ps-tg-row">${po.totalGoals.map(([g,p])=>{
      const h = Math.round(Math.min(100, Math.max(4, p*100*4)));
      return `<div class="ps-tg-col"><div class="ps-tg-bar" style="height:${h}%"></div><div class="ps-tg-val">${pct(p)}</div><div class="ps-tg-g">${g}</div></div>`;
    }).join('')}</div>
    ${group('主胜比分', po.homeScores, 'home')}"""

if old_meta in html:
    html = html.replace(old_meta, new_meta, 1)
    print("Inserted total goals bar in render")
else:
    print("ERROR: meta line not found")
    sys.exit(1)

# ---------- 3. Add CSS (before .ps-group) ----------
tg_css = """.ps-tg-title{font-size:12px;font-weight:600;color:var(--text-primary);margin-bottom:6px;}
.ps-tg-row{display:flex;align-items:flex-end;gap:5px;height:70px;padding:6px 4px 0;margin-bottom:12px;border-bottom:1px solid #e8ecf1;}
.ps-tg-col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;}
.ps-tg-bar{width:70%;max-width:28px;min-height:3px;background:linear-gradient(180deg,#0891b2,#06b6d4);border-radius:3px 3px 0 0;transition:height .3s ease;}
.ps-tg-val{font-size:9px;color:var(--text-secondary);margin-top:2px;line-height:1;}
.ps-tg-g{font-size:10px;font-weight:600;color:var(--text-muted);margin-top:1px;}
.ps-group{margin-bottom:10px;}"""

if ".ps-tg-title{" in html:
    print("CSS already present, skipping")
else:
    old_group_css = ".ps-group{margin-bottom:10px;}"
    if old_group_css in html:
        html = html.replace(old_group_css, tg_css, 1)
        print("Added total goals CSS")
    else:
        print("ERROR: .ps-group CSS anchor not found")
        sys.exit(1)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(html)

print("OK - total goals distribution added")
