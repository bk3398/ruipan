#!/usr/bin/env python3
"""在renderAnalysisTab的el.innerHTML前插入泊松代码。"""
import sys

FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到renderAnalysisTab函数内、最后一个 el.innerHTML = html; 的行号
# 特征：前一行是 html += '</tbody></table></div>';
# renderAnalysisTab在2044行附近，它的el.innerHTML大约在2171行
target_idx = None
for i in range(len(lines)-1):
    if "el.innerHTML = html;" in lines[i] and "</tbody></table></div>" in lines[i-1]:
        # 检查这个是否在renderAnalysisTab内（搜索前200行有无函数定义）
        window_start = max(0, i-200)
        window = ''.join(lines[window_start:i])
        if 'function renderAnalysisTab' in window:
            target_idx = i
            break

if target_idx is None:
    print("ERROR: cannot find renderAnalysisTab el.innerHTML")
    sys.exit(1)

print(f"Found target at line {target_idx+1}")

# 检查是否已有泊松代码
check_window = ''.join(lines[max(0,target_idx-15):target_idx])
if 'poissonCalc' in check_window:
    print("Already patched, skipping")
    sys.exit(0)

poisson_code = """  // ===== 泊松模型：皇冠/澳彩/威廉希尔初盘欧赔均值 =====
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

"""

lines.insert(target_idx, poisson_code)

with open(FILE, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("OK - poisson inserted into renderAnalysisTab")
