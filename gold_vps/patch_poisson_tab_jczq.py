#!/usr/bin/env python3
"""把列表页第5个Tab（泊松欧赔）改为完整泊松比分分布：
13主胜比分 + 5平局比分 + 13客胜比分，纯客观概率，无高亮推荐。
数据：前端从 tlData.data.euro 取 crown/macau/williamhill 初盘，本地计算。
同时清理盘口解析Tab误插的泊松块和debug日志。
"""
FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

text = ''.join(lines)

# ========== 1. loadOddsData 把 tlData 传给 renderOddsQuickTab ==========
old_call = "renderOddsQuickTab(fid, oqData, match);"
new_call = "renderOddsQuickTab(fid, oqData, match, tlData);"
if old_call in text:
    text = text.replace(old_call, new_call)
    print("Updated loadOddsData call to pass tlData")

# ========== 2. 删除 renderAnalysisTab 中的泊松块 ==========
out = []
i = 0
removed_analysis = False
while i < len(lines):
    if '// ===== 泊松模型' in lines[i] and not removed_analysis:
        window_start = max(0, i-200)
        window = ''.join(lines[window_start:i])
        if 'function renderAnalysisTab' in window:
            j = i
            while j < len(lines) and 'el.innerHTML = html;' not in lines[j]:
                j += 1
            print(f"Removed analysis poisson block: lines {i+1}-{j}")
            i = j
            removed_analysis = True
            continue
    out.append(lines[i])
    i += 1
lines = out
text = ''.join(lines)

# ========== 3. 删除旧 POISSON 辅助函数段 ==========
ps_start = None
ps_end = None
for i, line in enumerate(lines):
    if '// ===================== POISSON =====================' in line:
        ps_start = i
        for j in range(i+1, min(i+200, len(lines))):
            if lines[j].startswith('// ====') and 'POISSON' not in lines[j]:
                ps_end = j
                break
        break
if ps_start is not None and ps_end is not None:
    print(f"Removed old POISSON helpers: lines {ps_start+1}-{ps_end}")
    del lines[ps_start:ps_end]
    text = ''.join(lines)

# ========== 4. 替换 renderOddsQuickTab ==========
func_start = None
func_end = None
for i, line in enumerate(lines):
    if 'function renderOddsQuickTab(' in line:
        func_start = i
        brace = 0
        found_open = False
        for j in range(i, len(lines)):
            brace += lines[j].count('{')
            brace -= lines[j].count('}')
            if '{' in lines[j]:
                found_open = True
            if found_open and brace <= 0:
                func_end = j + 1
                break
        break

if func_start is None:
    print("ERROR: cannot find renderOddsQuickTab")
    exit(1)
print(f"Replacing renderOddsQuickTab: lines {func_start+1}-{func_end}")

new_func = r'''function renderOddsQuickTab(fid, oqData, match, tlData) {
  const el = document.getElementById(`tab-oddsquick-${fid}`);
  if (!el) return;

  let pH=[],pD=[],pA=[];
  try {
    const euro = (tlData && tlData.data && tlData.data.euro) || {};
    ['crown','macau','williamhill'].forEach(bk => {
      const d = euro[bk];
      if (d && d.initial && d.initial.h && d.initial.d && d.initial.a) {
        pH.push(+d.initial.h); pD.push(+d.initial.d); pA.push(+d.initial.a);
      }
    });
  } catch(e) {}

  if (pH.length < 1) {
    el.innerHTML = '<div class="empty-state" style="padding:20px;"><span style="color:var(--text-muted);">暂无皇冠/澳彩/威廉希尔初盘数据</span></div>';
    return;
  }

  const avg = a => a.reduce((s,x)=>s+x,0)/a.length;
  const oh=avg(pH), od=avg(pD), oa=avg(pA);
  const po = poissonCalc(oh, od, oa);
  if (!po) {
    el.innerHTML = '<div class="empty-state" style="padding:20px;"><span style="color:var(--text-muted);">泊松计算失败</span></div>';
    return;
  }

  const pct = v => (v*100).toFixed(1)+'%';
  const [ph,pd,pa] = po.p1x2;
  function scoreCells(arr) {
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
  }

  let html = `<div class="ps-box" style="margin-top:4px;padding:8px;">
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
  </div>`;

  el.innerHTML = html;
}

// ===================== POISSON =====================
function _pmf(k, lam) {
  if (lam <= 0) return k === 0 ? 1 : 0;
  let p = Math.exp(-lam), s = p;
  for (let i = 1; i <= k; i++) { p *= lam / i; s += p; }
  return p;
}
function _scoreProbs(lh, la, maxG) {
  let ph=0,pd=0,pa=0;
  const cells=[];
  for (let h=0;h<=maxG;h++) for (let a=0;a<=maxG;a++){
    const p=_pmf(h,lh)*_pmf(a,la);
    cells.push([h,a,p]);
    if(h>a)ph+=p; else if(h===a)pd+=p; else pa+=p;
  }
  return {ph,pd,pa,cells};
}
function poissonCalc(oh, od, oa) {
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
  const matrix={};
  cells.forEach(([h,a,p])=>{ matrix[h+'_'+a]=p; });
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
}
'''

lines = lines[:func_start] + [new_func] + lines[func_end:]
text = ''.join(lines)
print("Replaced renderOddsQuickTab with 13+5+13 poisson distribution")

# ========== 5. 清理 debug 日志 ==========
for dbg in [
    "  console.log('[poisson]', fid, 'bk keys:', Object.keys(bks), 'pH:', _pH, 'pD:', _pD, 'pA:', _pA);\n",
    "    console.log('[poisson] calc result:', po);\n",
    " console.log('[poisson] block added');",
    "      console.log('[poisson] no euro data from any of crown/macau/williamhill');\n",
]:
    if dbg in text:
        text = text.replace(dbg, '')
        print(f"Cleaned debug line")

# ========== 6. 添加 ps-* CSS（覆盖旧的，确保无高亮） ==========
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
# 删除旧的 ps-* CSS（如果patch_poisson_dist已添加）
import re
text = re.sub(r'\n\.ps-box\{.*?\.ps-prob\{[^}]*\}\n*', '\n', text, flags=re.DOTALL)
text = text.replace('</style>', ps_css + '</style>', 1)
print("Added/updated ps-* CSS")

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(text)
print("OK - poisson tab = 13 home + 5 draw + 13 away distribution")
