#!/usr/bin/env python3
"""
Polish poisson tab visuals:
- Replace .ps-* CSS with light-theme card style
- Refactor renderOddsQuickTab inline styles to CSS classes
- Subtle heatmap background on score cells (no max highlight, no recommendation)
"""
import re, sys

PATH = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ---------- 1. Replace .ps-* CSS block ----------
old_css = """.ps-box{font-size:0.6rem;}
.ps-group{margin-bottom:6px;}
.ps-group-title{font-size:0.55rem;font-weight:600;margin-bottom:3px;display:flex;justify-content:space-between;align-items:center;}
.ps-group-total{color:var(--text-muted);font-weight:400;}
.ps-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;}
.ps-cell{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:4px;padding:3px 2px;text-align:center;}
.ps-cell.ps-other{background:rgba(255,255,255,0.06);}
.ps-score{font-size:0.6rem;font-weight:600;color:var(--text-primary);}
.ps-prob{font-size:0.45rem;color:var(--text-secondary);}"""

new_css = """.ps-box{font-size:13px;background:linear-gradient(180deg,#fafbfc 0%,#f5f7fa 100%);border:1px solid #e8ecf1;border-radius:10px;padding:12px;}
.ps-title{font-size:13px;font-weight:700;color:#0891b2;margin-bottom:10px;display:flex;align-items:center;gap:6px;}
.ps-prob-row{display:flex;gap:8px;margin-bottom:10px;}
.ps-prob-card{flex:1;border-radius:8px;padding:8px 6px;text-align:center;border:1px solid transparent;transition:transform .15s ease;}
.ps-prob-card:hover{transform:translateY(-1px);}
.ps-prob-card.home{background:rgba(39,174,96,0.08);border-color:rgba(39,174,96,0.2);}
.ps-prob-card.draw{background:rgba(240,165,0,0.08);border-color:rgba(240,165,0,0.2);}
.ps-prob-card.away{background:rgba(52,152,219,0.08);border-color:rgba(52,152,219,0.2);}
.ps-prob-label{font-size:11px;color:var(--text-secondary);margin-bottom:2px;}
.ps-prob-value{font-size:18px;font-weight:700;line-height:1.1;}
.ps-prob-card.home .ps-prob-value{color:#27ae60;}
.ps-prob-card.draw .ps-prob-value{color:#d4a017;}
.ps-prob-card.away .ps-prob-value{color:#2980b9;}
.ps-meta{font-size:11px;color:var(--text-muted);text-align:center;padding:6px 0 10px;border-top:1px dashed #e0e5eb;margin-bottom:10px;}
.ps-group{margin-bottom:10px;}
.ps-group:last-child{margin-bottom:0;}
.ps-group-title{font-size:12px;font-weight:600;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;padding:4px 8px;border-radius:5px;}
.ps-group.home .ps-group-title{background:rgba(39,174,96,0.08);color:#1e8449;}
.ps-group.draw .ps-group-title{background:rgba(240,165,0,0.08);color:#b7950b;}
.ps-group.away .ps-group-title{background:rgba(52,152,219,0.08);color:#2471a3;}
.ps-group-total{font-weight:500;color:var(--text-muted);font-size:11px;}
.ps-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;}
.ps-cell{border-radius:6px;padding:5px 2px;text-align:center;border:1px solid transparent;transition:all .15s ease;}
.ps-cell:hover{transform:translateY(-1px);box-shadow:0 2px 6px rgba(0,0,0,0.06);}
.ps-score{font-size:12px;font-weight:600;color:var(--text-primary);line-height:1.2;}
.ps-prob{font-size:10px;color:var(--text-secondary);margin-top:1px;line-height:1.2;}
.ps-cell.ps-other{opacity:0.7;}"""

if old_css in html:
    html = html.replace(old_css, new_css, 1)
    print("Replaced .ps-* CSS block")
else:
    print("WARNING: old CSS block not found, trying regex...")
    pat = re.compile(r'\.ps-box\{.*?\.ps-prob\{[^}]*\}', re.DOTALL)
    html, n = pat.subn(new_css, html)
    if n:
        print(f"Replaced CSS via regex ({n} match)")
    else:
        print("ERROR: could not find CSS block")
        sys.exit(1)

# ---------- 2. Replace renderOddsQuickTab HTML template ----------
# Replace from 'let html =' to 'el.innerHTML = html;' inside renderOddsQuickTab
old_render = """  let html = `<div class="ps-box" style="margin-top:4px;padding:8px;">
    <div style="font-size:0.6rem;color:#4dd0e1;margin-bottom:6px;">🎯 泊松模型</div>
    <div style="display:flex;gap:4px;margin-bottom:8px;">
      <div style="flex:1;background:rgba(0,230,118,0.08);border:1px solid rgba(0,230,118,0.2);border-radius:6px;padding:6px;text-align:center;">
        <div style="font-size:0.55rem;color:var(--text-secondary);">主胜</div>
        <div style="font-size:1rem;font-weight:700;color:#00e676;">${pct(ph)}</div>
      </div>
      <div style="flex:1;background:rgba(255,215,0,0.08);border:1px solid rgba(255,215,0,0.2);border-radius:6px;padding:6px;text-align:center;">
        <div style="font-size:0.55rem;color:var(--text-secondary);">平局</div>
        <div style="font-size:1rem;font-weight:700;color:#ffd700;">${pct(pd)}</div>
      </div>
      <div style="flex:1;background:rgba(68,138,255,0.08);border:1px solid rgba(68,138,255,0.2);border-radius:6px;padding:6px;text-align:center;">
        <div style="font-size:0.55rem;color:var(--text-secondary);">客胜</div>
        <div style="font-size:1rem;font-weight:700;color:#448aff;">${pct(pa)}</div>
      </div>
    </div>
    <div style="font-size:0.55rem;color:var(--text-muted);text-align:center;margin-bottom:8px;">λ主=${po.lh.toFixed(2)} λ客=${po.la.toFixed(2)} | 欧赔 ${oh.toFixed(2)}/${od.toFixed(2)}/${oa.toFixed(2)}</div>
    ${group('主胜比分', po.homeScores, '#00e676')}
    ${group('平局比分', po.drawScores, '#ffd700')}
    ${group('客胜比分', po.awayScores, '#448aff')}
  </div>`;"""

new_render = """  // Heatmap background intensity based on probability (purely visual, no recommendation)
  const heatStyle = (prob, kind) => {
    const t = Math.min(1, Math.max(0, prob / 0.12)); // normalize ~0-12%
    const colors = {
      home: [39,174,96],   // green
      draw: [240,165,0],   // gold
      away: [52,152,219]   // blue
    };
    const [r,g,b] = colors[kind] || [150,150,150];
    const a = (0.06 + t * 0.18).toFixed(2);
    const ba = (0.15 + t * 0.35).toFixed(2);
    return `background:rgba(${r},${g},${b},${a});border-color:rgba(${r},${g},${b},${ba});`;
  };

  let html = `<div class="ps-box">
    <div class="ps-title">🎯 泊松模型</div>
    <div class="ps-prob-row">
      <div class="ps-prob-card home"><div class="ps-prob-label">主胜</div><div class="ps-prob-value">${pct(ph)}</div></div>
      <div class="ps-prob-card draw"><div class="ps-prob-label">平局</div><div class="ps-prob-value">${pct(pd)}</div></div>
      <div class="ps-prob-card away"><div class="ps-prob-label">客胜</div><div class="ps-prob-value">${pct(pa)}</div></div>
    </div>
    <div class="ps-meta">λ主 ${po.lh.toFixed(2)} · λ客 ${po.la.toFixed(2)} &nbsp;|&nbsp; 欧赔 ${oh.toFixed(2)} / ${od.toFixed(2)} / ${oa.toFixed(2)}</div>
    ${group('主胜比分', po.homeScores, 'home')}
    ${group('平局比分', po.drawScores, 'draw')}
    ${group('客胜比分', po.awayScores, 'away')}
  </div>`;"""

if old_render in html:
    html = html.replace(old_render, new_render, 1)
    print("Replaced renderOddsQuickTab HTML template")
else:
    print("WARNING: old render block not found exactly, trying flexible regex...")
    pat = re.compile(r'  let html = `.*?\$\{group\(\'客胜比分\'.*?\n  </div>`;', re.DOTALL)
    html, n = pat.subn(new_render.replace('\\', '\\\\'), html, count=1)
    if n:
        print(f"Replaced render via regex ({n} match)")
    else:
        print("ERROR: could not find render block")
        sys.exit(1)

# ---------- 3. Update group() and scoreCells() functions to use new classes ----------
old_score = """  function scoreCells(arr) {
    return arr.map(item => {
      if (item[0] === 'other') {
        return `<div class="ps-cell ps-other"><div class="ps-score">其他</div><div class="ps-prob">${pct(item[1])}</div></div>`;
      }
      const [h,a] = item[0];
      return `<div class="ps-cell"><div class="ps-score">${h}:${a}</div><div class="ps-prob">${pct(item[1])}</div></div>`;
    }).join('');
  }

  function group(title, arr, color) {
    const total = arr.reduce((s,x)=>s+x[1],0);
    return `<div class="ps-group">
      <div class="ps-group-title" style="color:${color}">${title}<span class="ps-group-total">${pct(total)}</span></div>
      <div class="ps-grid">${scoreCells(arr)}</div>
    </div>`;
  }"""

new_score = """  function scoreCells(arr, kind) {
    return arr.map(item => {
      const isOther = item[0] === 'other';
      const label = isOther ? '其他' : item[0].join(':');
      const style = heatStyle(item[1], kind);
      return `<div class="ps-cell${isOther?' ps-other':''}" style="${style}"><div class="ps-score">${label}</div><div class="ps-prob">${pct(item[1])}</div></div>`;
    }).join('');
  }

  function group(title, arr, kind) {
    const total = arr.reduce((s,x)=>s+x[1],0);
    return `<div class="ps-group ${kind}">
      <div class="ps-group-title">${title}<span class="ps-group-total">${pct(total)}</span></div>
      <div class="ps-grid">${scoreCells(arr, kind)}</div>
    </div>`;
  }"""

if old_score in html:
    html = html.replace(old_score, new_score, 1)
    print("Replaced scoreCells/group functions")
else:
    print("WARNING: old scoreCells/group not found, trying regex...")
    pat = re.compile(r'  function scoreCells\(arr\).*?\n  \}\n\n  function group\(title, arr, color\).*?\n  \}', re.DOTALL)
    html, n = pat.subn(new_score, html, count=1)
    if n:
        print(f"Replaced scoreCells/group via regex ({n} match)")
    else:
        print("ERROR: could not find scoreCells/group")
        sys.exit(1)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(html)

print("OK - poisson visual polish applied")
