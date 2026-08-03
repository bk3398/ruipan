#!/usr/bin/env python3
"""把列表页 poissonBlockHTML 替换为与 jczq 竞彩攻略页完全一致的格式：
- 三个概率盒子（主胜/平局/客胜）
- lambda行附带欧赔值
- 最可能比分使用 score-grid / score-cell CSS class（需确保CSS存在）
同时清理 renderAnalysisTab 泊松块中的 console.log 调试日志。
"""
FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    html = f.read()

# ---------- 1. 替换 poissonBlockHTML 函数 ----------
import re
# 匹配从 function poissonBlockHTML 到其结束（下一个 function 或 POISSON 段尾注释）
new_fn = r"""function poissonBlockHTML(po, src, oh, od, oa) {
  const [ph,pd,pa]=po.p1x2;
  const pct=v=>(v*100).toFixed(1)+'%';
  let scores='';
  po.top.forEach(([h,a,p])=>{
    scores+=`<div class="score-cell">
  <div class="score-val">${h}:${a}</div>
  <div class="score-prob">${pct(p)}</div>
</div>`;
  });
  const label = src>=3 ? '皇冠/澳彩/威廉均值' : (src+'家均值');
  return `<div class="section" style="margin-top:10px;padding:8px;background:rgba(0,230,118,0.03);border:1px solid rgba(0,230,118,0.15);border-radius:8px;">
    <div style="font-size:0.6rem;color:#4dd0e1;margin-bottom:6px;">🎯 泊松模型 <span style="color:var(--text-muted);font-weight:400;">· ${label}</span></div>
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
    <div style="font-size:0.55rem;color:var(--text-muted);text-align:center;margin-bottom:6px;">λ主=${po.lh.toFixed(2)} λ客=${po.la.toFixed(2)} | 欧赔 ${oh.toFixed(2)}/${od.toFixed(2)}/${oa.toFixed(2)}</div>
    <div style="font-size:0.6rem;color:#4dd0e1;margin-bottom:4px;">最可能比分</div>
    <div class="score-grid">${scores}</div>
  </div>`;
}"""

pattern = re.compile(r'function poissonBlockHTML\(po, src\) \{.*?\n\}', re.DOTALL)
m = pattern.search(html)
if not m:
    print("ERROR: cannot find poissonBlockHTML function")
    exit(1)
html = html[:m.start()] + new_fn + html[m.end():]
print("Replaced poissonBlockHTML function")

# ---------- 2. 更新两个调用点，传入欧赔均值 ----------
# renderAnalysisTab 调用
old_call1 = "if (po) { html += poissonBlockHTML(po, _pH.length); console.log('[poisson] block added'); }"
new_call1 = "if (po) { html += poissonBlockHTML(po, _pH.length, avg(_pH), avg(_pD), avg(_pA)); }"
if old_call1 in html:
    html = html.replace(old_call1, new_call1)
    print("Updated renderAnalysisTab call + removed debug log")
else:
    # 尝试不带 console.log 的版本
    old_call1b = "if (po) html += poissonBlockHTML(po, _pH.length);"
    if old_call1b in html:
        html = html.replace(old_call1b, "if (po) html += poissonBlockHTML(po, _pH.length, avg(_pH), avg(_pD), avg(_pA));")
        print("Updated renderAnalysisTab call (no debug log found)")
    else:
        print("WARN: renderAnalysisTab call not matched, trying fuzzy")

# renderEuroTable 调用（如果 patch_poisson_euro 已执行）
old_call2 = "if (po) html += poissonBlockHTML(po, _pH.length);"
new_call2 = "if (po) html += poissonBlockHTML(po, _pH.length, avg(_pH), avg(_pD), avg(_pA));"
if old_call2 in html:
    html = html.replace(old_call2, new_call2)
    print("Updated renderEuroTable call")

# 清理残留的 console.log poisson 调试行
for dbg in ["console.log('[poisson] calc result:', po);",
            "console.log('[poisson]",
            "bk keys:",
            "pH:",
            "pD:",
            "pA:"]:
    pass  # 只清理完整语句
html = html.replace("  console.log('[poisson] bk keys:', Object.keys(bks), 'pH:', _pH, 'pD:', _pD, 'pA:', _pA);\n", "")
html = html.replace("    console.log('[poisson] calc result:', po);\n", "")
html = html.replace(" console.log('[poisson] block added');", "")
print("Cleaned debug console.log lines")

# ---------- 3. 确保 score-grid / score-cell CSS 存在 ----------
if '.score-grid' not in html:
    css = """
.score-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin-bottom:4px;}
.score-cell{background:rgba(68,138,255,0.08);border:1px solid rgba(68,138,255,0.2);border-radius:6px;padding:4px;text-align:center;}
.score-val{font-size:0.85rem;font-weight:700;color:#e0e0e0;}
.score-prob{font-size:0.55rem;color:#4dd0e1;}
"""
    html = html.replace('</style>', css + '</style>', 1)
    print("Added score-grid/score-cell CSS")
else:
    print("score-grid CSS already exists")

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(html)
print("OK - poisson format unified with jczq")
