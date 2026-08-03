#!/usr/bin/env python3
"""调试泊松：在renderAnalysisTab中加console.log，并清理renderAsianTable中的旧错误块"""
import sys

FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

# 1. 清理renderAsianTable中的旧泊松块（行1892-1911区域）
# 找到第一个泊松块（在renderAsianTable中，在el.innerHTML之前有bks引用的那个）
# 特征：前面是 html += '</tbody></table></div>'; 后面跟空行再跟泊松try，且这个泊松try在renderAsianTable函数内
# 用renderAsianTable函数范围来定位

# 找renderAsianTable函数开始
ras_start = None
for i, line in enumerate(lines):
    if 'function renderAsianTable' in line:
        ras_start = i
        break

ras_end = None
if ras_start:
    # 找这个函数的结束（下一个function或// ====）
    for i in range(ras_start+1, len(lines)):
        if lines[i].startswith('function ') or (lines[i].startswith('// ====') and 'EURO' in lines[i]):
            ras_end = i
            break

print(f"renderAsianTable: lines {ras_start+1}-{ras_end+1 if ras_end else '?'}")

# 在这个范围内找泊松块并删除
if ras_start is not None and ras_end is not None:
    poisson_start = None
    poisson_end = None
    for i in range(ras_start, ras_end):
        if '泊松模型' in lines[i] and '// =====' in lines[i]:
            poisson_start = i - 1  # 包含前面的空行
        if poisson_start and i > poisson_start and ('el.innerHTML = html;' in lines[i]):
            poisson_end = i  # 不删el.innerHTML这行
            break
    
    if poisson_start and poisson_end:
        print(f"Removing old poisson block at lines {poisson_start+1}-{poisson_end}")
        del lines[poisson_start:poisson_end]
    else:
        print("No old poisson block found in renderAsianTable (maybe already removed)")

# 2. 给renderAnalysisTab中的泊松块加调试
# 重新join
content = '\n'.join(lines)

# 在泊松try块前加console.log
old_try = """  // ===== 泊松模型：皇冠/澳彩/威廉希尔初盘欧赔均值 =====
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
  } catch(e){ console.warn('poisson err',e); }"""

new_try = """  // ===== 泊松模型：皇冠/澳彩/威廉希尔初盘欧赔均值 =====
  try {
    const PB = ['crown','macau','williamhill'];
    let _pH=[],_pD=[],_pA=[];
    PB.forEach(bk => {
      const ph = bks[bk] && bks[bk].phases && bks[bk].phases.initial;
      if (ph && ph.euro && ph.euro.home_win && ph.euro.draw && ph.euro.away_win) {
        _pH.push(+ph.euro.home_win); _pD.push(+ph.euro.draw); _pA.push(+ph.euro.away_win);
      }
    });
    console.log('[poisson]', fid, 'bk keys:', Object.keys(bks), 'pH:', _pH, 'pD:', _pD, 'pA:', _pA);
    if (_pH.length >= 1) {
      const avg=a=>a.reduce((s,x)=>s+x,0)/a.length;
      const po=poissonCalc(avg(_pH),avg(_pD),avg(_pA));
      console.log('[poisson] calc result:', po);
      if (po) { html += poissonBlockHTML(po, _pH.length); console.log('[poisson] block added'); }
    } else {
      console.log('[poisson] no euro data from any of crown/macau/williamhill');
    }
  } catch(e){ console.warn('poisson err',e); }"""

if old_try in content:
    content = content.replace(old_try, new_try, 1)
    print("Added debug logging to renderAnalysisTab poisson block")
else:
    print("WARNING: could not find poisson try block to add debug")

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

print("OK - debug patch applied")
