#!/usr/bin/env python3
"""在renderEuroTable的el.innerHTML前插入泊松区块。
数据来源：euro对象中的crown/macau/williamhill初盘欧赔。
"""
FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到renderEuroTable函数中的 el.innerHTML = html;
# 特征：前一行是 html += '</tbody></table></div>';
# 且在renderEuroTable函数内
target_idx = None
for i in range(len(lines)-1):
    if "el.innerHTML = html;" in lines[i] and "</tbody></table></div>" in lines[i-1]:
        window_start = max(0, i-100)
        window = ''.join(lines[window_start:i])
        if 'function renderEuroTable' in window:
            target_idx = i
            break

if target_idx is None:
    print("ERROR: cannot find renderEuroTable el.innerHTML")
    exit(1)

print(f"Found renderEuroTable el.innerHTML at line {target_idx+1}")

# 检查是否已有泊松
check = ''.join(lines[max(0,target_idx-20):target_idx])
if 'poissonCalc' in check:
    print("Already patched, skipping")
    exit(0)

poisson_code = """
  // ===== 泊松模型：皇冠/澳彩/威廉希尔初盘欧赔均值 =====
  try {
    const PB = ['crown','macau','williamhill'];
    let _pH=[],_pD=[],_pA=[];
    PB.forEach(bk => {
      const d = euro[bk];
      if (d && d.initial && d.initial.h && d.initial.d && d.initial.a) {
        _pH.push(+d.initial.h); _pD.push(+d.initial.d); _pA.push(+d.initial.a);
      }
    });
    if (_pH.length >= 1) {
      const avg=a=>a.reduce((s,x)=>s+x,0)/a.length;
      const po=poissonCalc(avg(_pH),avg(_pD),avg(_pA));
      if (po) html += poissonBlockHTML(po, _pH.length);
    }
  } catch(e){ console.warn('poisson euro err',e); }

"""

lines.insert(target_idx, poisson_code)

with open(FILE, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("OK - poisson inserted into renderEuroTable")
