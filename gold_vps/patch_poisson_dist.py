#!/usr/bin/env python3
"""把列表页泊松区块改为完整比分分布：13主胜+5平局+13客胜，纯客观概率，不做Top5推荐。
同时清理debug日志。数据来源不变（盘口解析Tab，analysis API）。
"""
FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    html = f.read()

import re

# ---------- 1. 替换 poissonCalc，让它返回完整比分矩阵 ----------
new_calc = r"""function poissonCalc(oh, od, oa) {
  const rh=1/oh, rd=1/od, ra=1/oa, rt=rh+rd+ra;
  const th=rh/rt, td=rd/rt, ta=ra/rt;
  let bestLH=1.3, bestLA=1.3, bestErr=Infinity;
  for (let lh=0.5; lh<=3.5; lh+=0.05)
    for (let la=0.5; la<=3.5; la+=0.05) {
      const {ph,pd,pa}=_scoreProbs(lh,la,6);
      const e=(ph-th)**2+(pd-td)**2+(pa-ta)**2;
      if (e<bestErr){bestErr=e;bestLH=lh;bestLA=la;}
    }
  for (let lh=bestLH-0.1; lh<=bestLH+0.1; lh+=0.01)
    for (let la=bestLA-0.1; la<=bestLA+0.1; la+=0.01) {
      if(lh<0.3||lh>3.5||la<0.3||la>3.5)continue;
      const {ph,pd,pa}=_scoreProbs(lh,la,6);
      const e=(ph-th)**2+(pd-td)**2+(pa-ta)**2;
      if (e<bestErr){bestErr=e;bestLH=lh;bestLA=la;}
    }
  const {ph,pd,pa,cells}=_scoreProbs(bestLH,bestLA,7);
  // 构建比分矩阵
  const matrix={};
  cells.forEach(([h,a,p])=>{ matrix[h+'_'+a]=p; });
  // 固定比分
  const FH=[[1,0],[2,0],[2,1],[3,0],[3,1],[3,2],[4,0],[4,1],[4,2],[5,0],[5,1],[5,2]];
  const FD=[[0,0],[1,1],[2,2],[3,3]];
  const FA=[[0,1],[0,2],[0,3],[1,2],[1,3],[2,3],[0,4],[1,4],[2,4],[0,5],[1,5],[2,5]];
  const getP=sa=>matrix[sa[0]+'_'+sa[1]]||0;
  const homeScores=FH.map(s=>[s,getP(s)]);
  const drawScores=FD.map(s=>[s,getP(s)]);
  const awayScores=FA.map(s=>[s,getP(s)]);
  const listed=homeScores.reduce((s,x)=>s+x[1],0)+drawScores.reduce((s,x)=>s+x[1],0)+awayScores.reduce((s,x)=>s+x[1],0);
  const other=Math.max(0,1-listed);
  const hT=homeScores.reduce((s,x)=>s+x[1],0);
  const dT=drawScores.reduce((s,x)=>s+x[1],0);
  const aT=awayScores.reduce((s,x)=>s+x[1],0);
  const cT=hT+dT+aT;
  let hO,dO,aO;
  if(cT>0){ hO=other*(hT/cT); dO=other*(dT/cT); aO=other*(aT/cT); }
  else { hO=dO=aO=other/3; }
  homeScores.push(['other',hO]);
  drawScores.push(['other',dO]);
  awayScores.push(['other',aO]);
  return { lh:bestLH, la:bestLA, p1x2:[ph,pd,pa], homeScores, drawScores, awayScores };
}"""

pattern_calc = re.compile(r'function poissonCalc\(oh, od, oa\) \{.*?\n\}', re.DOTALL)
m = pattern_calc.search(html)
if not m:
    print("ERROR: cannot find poissonCalc")
    exit(1)
html = html[:m.start()] + new_calc + html[m.end():]
print("Replaced poissonCalc (now returns full score distribution)")

# ---------- 2. 替换 poissonBlockHTML，渲染13+5+13 ----------
new_block = r"""function poissonBlockHTML(po, src, oh, od, oa) {
  const [ph,pd,pa]=po.p1x2;
  const pct=v=>(v*100).toFixed(1)+'%';
  const label = src>=3 ? '皇冠/澳彩/威廉均值' : (src+'家均值');

  function scoreCell(item){
    if(item[0]==='other'){
      return `<div class="ps-cell ps-other"><div class="ps-score">其他</div><div class="ps-prob">${pct(item[1])}</div></div>`;
    }
    const [h,a]=item[0];
    return `<div class="ps-cell"><div class="ps-score">${h}:${a}</div><div class="ps-prob">${pct(item[1])}</div></div>`;
  }
  function group(title, arr, color){
    let cells=arr.map(scoreCell).join('');
    const total=arr.reduce((s,x)=>s+x[1],0);
    return `<div class="ps-group">
      <div class="ps-group-title" style="color:${color}">${title} <span class="ps-group-total">${pct(total)}</span></div>
      <div class="ps-grid">${cells}</div>
    </div>`;
  }

  return `<div class="ps-box" style="margin-top:10px;padding:8px;background:rgba(0,230,118,0.03);border:1px solid rgba(0,230,118,0.15);border-radius:8px;">
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
    <div style="font-size:0.55rem;color:var(--text-muted);text-align:center;margin-bottom:8px;">λ主=${po.lh.toFixed(2)} λ客=${po.la.toFixed(2)} | 欧赔 ${oh.toFixed(2)}/${od.toFixed(2)}/${oa.toFixed(2)}</div>
    ${group('主胜比分', po.homeScores, '#00e676')}
    ${group('平局比分', po.drawScores, '#ffd700')}
    ${group('客胜比分', po.awayScores, '#448aff')}
  </div>`;
}"""

pattern_block = re.compile(r'function poissonBlockHTML\(.*?\) \{.*?\n\}', re.DOTALL)
m2 = pattern_block.search(html)
if not m2:
    print("ERROR: cannot find poissonBlockHTML")
    exit(1)
html = html[:m2.start()] + new_block + html[m2.end():]
print("Replaced poissonBlockHTML (13+5+13 distribution)")

# ---------- 3. 更新调用点，传入欧赔均值，清理debug ----------
# renderAnalysisTab
html = html.replace(
    "if (po) { html += poissonBlockHTML(po, _pH.length); console.log('[poisson] block added'); }",
    "if (po) { html += poissonBlockHTML(po, _pH.length, avg(_pH), avg(_pD), avg(_pA)); }"
)
html = html.replace(
    "if (po) html += poissonBlockHTML(po, _pH.length);",
    "if (po) html += poissonBlockHTML(po, _pH.length, avg(_pH), avg(_pD), avg(_pA));"
)
# 清理调试日志
html = html.replace("  console.log('[poisson] bk keys:', Object.keys(bks), 'pH:', _pH, 'pD:', _pD, 'pA:', _pA);\n", "")
html = html.replace("    console.log('[poisson] calc result:', po);\n", "")
print("Updated calls + cleaned debug logs")

# ---------- 4. 添加泊松比分分布CSS ----------
ps_css = """
.ps-box{font-size:0.6rem;}
.ps-group{margin-bottom:6px;}
.ps-group-title{font-size:0.55rem;font-weight:600;margin-bottom:3px;display:flex;justify-content:space-between;align-items:center;}
.ps-group-total{color:var(--text-muted);font-weight:400;}
.ps-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;}
.ps-cell{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:4px;padding:3px 2px;text-align:center;}
.ps-cell.ps-other{background:rgba(255,255,255,0.06);}
.ps-score{font-size:0.6rem;font-weight:600;color:var(--text-primary);}
.ps-prob{font-size:0.45rem;color:var(--text-secondary);}
"""
if '.ps-grid' not in html:
    html = html.replace('</style>', ps_css + '</style>', 1)
    print("Added ps-* CSS")
else:
    print("ps-* CSS already exists")

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(html)
print("OK - poisson now shows 13 home + 5 draw + 13 away score distribution")
