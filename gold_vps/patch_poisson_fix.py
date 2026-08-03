#!/usr/bin/env python3
"""修复：把泊松代码从错误函数移到renderAnalysisTab正确位置。"""
import sys, re

FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    html = f.read()

# 1) 移除错误插入的泊松代码块（在亚盘表格函数里的那段）
WRONG_BLOCK = """  // ===== 泊松模型：皇冠/澳彩/威廉希尔初盘欧赔均值 =====
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

if WRONG_BLOCK in html:
    html = html.replace(WRONG_BLOCK, "  el.innerHTML = html;", 1)
    print("Removed wrong block")
else:
    print("WARN: wrong block not found, may already be clean")

# 2) 在renderAnalysisTab函数的正确位置插入
# 这个函数以 winRateCell 结尾，el.innerHTML = html;
# 用 "el.innerHTML = html;\n}\n\n// ===================== HELPERS" 精确定位
CORRECT_ANCHOR = "  el.innerHTML = html;\n}\n\n// ===================== HELPERS ====================="

POISSON_INSERT = """  // ===== 泊松模型：皇冠/澳彩/威廉希尔初盘欧赔均值 =====
  try {
    const PB = ['crown','macau','williamhill'];
    let _pH=[],_pD=[],_pA=[];
    PB.forEach(bk => {
      const ph = bks[bk] && bks[bk].phases && bks[bk].phases.initial;
      if (ph && ph.euro && ph.euro.home_win && ph.euro.draw && ph.euro.away_win) {
        _pH.push(+ph.euro.home_win); _pD.push(+ph.euro.draw); _pA.push(+ph.euro.away_win);
      }
    });
    if (_pH.length >= 1) {
      const avg=a=>a.reduce((s,x)=>s+x,0)/a.length;
      const po=poissonCalc(avg(_pH),avg(_pD),avg(_pA));
      if (po) html += poissonBlockHTML(po, _pH.length);
    }
  } catch(e){ console.warn('poisson err',e); }

  el.innerHTML = html;
}

// ===================== HELPERS ====================="""

if CORRECT_ANCHOR in html:
    html = html.replace(CORRECT_ANCHOR, POISSON_INSERT, 1)
    print("Inserted poisson into renderAnalysisTab")
else:
    print("ERROR: correct anchor not found")
    sys.exit(1)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(html)
print("OK - fixed")
