#!/usr/bin/env python3
"""为列表页(live-scores-preview-v6.html)盘口解析添加泊松模型。
前端直接用API已返回的crown/macau/williamhill初盘欧赔计算，与竞彩攻略页算法一致。
"""
import sys

FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    html = f.read()

# 1) 在 el.innerHTML = html; 之前插入泊松区块渲染
ANCHOR = "  html += '</tbody></table></div>';\n  el.innerHTML = html;"

POISSON_BLOCK = """  html += '</tbody></table></div>';

  // ===== 泊松模型：皇冠/澳彩/威廉希尔初盘欧赔均值 =====
  try {
    const PB = ['crown','macau','williamhill'];
    let _pH=[],_pD=[],_pA=[],_hdp=null;
    PB.forEach(bk => {
      const ph = bks[bk] && bks[bk].phases && bks[bk].phases.initial;
      if (ph && ph.euro && ph.euro.home_win && ph.euro.draw && ph.euro.away_win) {
        _pH.push(+ph.euro.home_win); _pD.push(+ph.euro.draw); _pA.push(+ph.euro.away_win);
        if (_hdp==null && ph.asia && ph.asia.handicap!=null) _hdp=+ph.asia.handicap;
      }
    });
    if (_pH.length >= 1) {
      const avg=a=>a.reduce((s,x)=>s+x,0)/a.length;
      const po=poissonCalc(avg(_pH),avg(_pD),avg(_pA));
      if (po) html += poissonBlockHTML(po, _pH.length);
    }
  } catch(e){ console.warn('poisson err',e); }

  el.innerHTML = html;"""

if ANCHOR not in html:
    print("ERROR: anchor not found (already patched?)")
    sys.exit(1)

html = html.replace(ANCHOR, POISSON_BLOCK, 1)

# 2) 在 renderAnalysisTab 函数结束后插入泊松计算与渲染辅助函数
HELPERS_ANCHOR = "// ===================== HELPERS ====================="

HELPERS = r"""
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
  cells.sort((a,b)=>b[2]-a[2]);
  return { lh:bestLH, la:bestLA, p1x2:[ph,pd,pa], top:cells.slice(0,5) };
}
function poissonBlockHTML(po, src) {
  const [ph,pd,pa]=po.p1x2;
  const pct=v=>(v*100).toFixed(1)+'%';
  let scores='';
  po.top.forEach(([h,a,p])=>{
    scores+=`<div style="display:inline-block;background:rgba(68,138,255,0.08);border:1px solid rgba(68,138,255,0.2);border-radius:6px;padding:4px 8px;margin:2px;text-align:center;min-width:48px;">
      <div style="font-size:0.75rem;font-weight:700;">${h}:${a}</div>
      <div style="font-size:0.5rem;color:#4dd0e1;">${pct(p)}</div>
    </div>`;
  });
  const label = src>=3 ? '皇冠/澳彩/威廉均值' : (src+'家均值');
  return `<div style="margin-top:10px;padding:8px;background:rgba(0,230,118,0.03);border:1px solid rgba(0,230,118,0.15);border-radius:8px;">
    <div style="font-size:0.6rem;color:#4dd0e1;margin-bottom:6px;">🎯 泊松模型 <span style="color:var(--text-muted);font-weight:400;">· ${label}</span></div>
    <div style="display:flex;gap:4px;margin-bottom:6px;">
      <div style="flex:1;background:rgba(0,230,118,0.08);border:1px solid rgba(0,230,118,0.2);border-radius:6px;padding:5px;text-align:center;">
        <div style="font-size:0.5rem;color:var(--text-secondary);">主胜</div>
        <div style="font-size:0.9rem;font-weight:700;color:#00e676;">${pct(ph)}</div>
      </div>
      <div style="flex:1;background:rgba(255,215,0,0.08);border:1px solid rgba(255,215,0,0.2);border-radius:6px;padding:5px;text-align:center;">
        <div style="font-size:0.5rem;color:var(--text-secondary);">平局</div>
        <div style="font-size:0.9rem;font-weight:700;color:#ffd700;">${pct(pd)}</div>
      </div>
      <div style="flex:1;background:rgba(68,138,255,0.08);border:1px solid rgba(68,138,255,0.2);border-radius:6px;padding:5px;text-align:center;">
        <div style="font-size:0.5rem;color:var(--text-secondary);">客胜</div>
        <div style="font-size:0.9rem;font-weight:700;color:#448aff;">${pct(pa)}</div>
      </div>
    </div>
    <div style="font-size:0.5rem;color:var(--text-muted);text-align:center;margin-bottom:4px;">λ主=${po.lh.toFixed(2)} λ客=${po.la.toFixed(2)}</div>
    <div style="text-align:center;">${scores}</div>
  </div>`;
}

// ===================== HELPERS ====================="""

if HELPERS_ANCHOR not in html:
    print("ERROR: helpers anchor not found")
    sys.exit(1)

html = html.replace(HELPERS_ANCHOR, HELPERS, 1)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(html)

print("OK - poisson patched into list page")
