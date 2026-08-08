#!/usr/bin/env python3
"""修复K线图位置：从亚盘Tab移到盘口解析Tab"""
import shutil, os

HTML = '/opt/ruipan/static/live-scores-preview-v6.html'
BAK = HTML + '.bak_kline_move'

# 备份
shutil.copy2(HTML, BAK)
print(f"✅ 备份 → {BAK}")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# 要从renderAsianTable中移除的K线块
KLINE_BLOCK = """
  // K线蜡烛图区域
  html += `<div class="kline-section" id="kline-section-${fid}">
    <div class="kline-header">
      <span class="kline-title">📈 赔率分歧K线</span>
      <div id="kline-types-${fid}" style="display:flex;gap:4px;flex-wrap:wrap;"></div>
      <div id="kline-wins-${fid}" style="display:flex;gap:3px;margin-left:auto;"></div>
    </div>
    <div class="kline-canvas-wrap">
      <canvas id="kline-canvas-${fid}" height="180"></canvas>
    </div>
    <div class="kline-legend" id="kline-legend-${fid}"></div>
  </div>`;

  el.innerHTML = html;

  // 异步加载K线数据
  loadKlineData(fid);
}"""

# 亚盘函数的正确结尾（K线注入后的当前状态）
ASIA_CURRENT_END = """  html += '</tbody></table></div>';
""" + KLINE_BLOCK

# 亚盘函数应恢复为的结尾
ASIA_FIXED_END = """  html += '</tbody></table></div>';
  el.innerHTML = html;
}"""

# 盘口解析函数当前结尾
ANALYSIS_CURRENT_END = """  html += '</tbody></table></div>';
  el.innerHTML = html;
}

// ===================== HELPERS ====================="""

# 盘口解析函数新结尾（追加K线）
ANALYSIS_NEW_END = """  html += '</tbody></table></div>';

  // K线蜡烛图区域
  html += `<div class="kline-section" id="kline-section-${fid}">
    <div class="kline-header">
      <span class="kline-title">📈 赔率分歧K线</span>
      <div id="kline-types-${fid}" style="display:flex;gap:4px;flex-wrap:wrap;"></div>
      <div id="kline-wins-${fid}" style="display:flex;gap:3px;margin-left:auto;"></div>
    </div>
    <div class="kline-canvas-wrap">
      <canvas id="kline-canvas-${fid}" height="180"></canvas>
    </div>
    <div class="kline-legend" id="kline-legend-${fid}"></div>
  </div>`;

  el.innerHTML = html;

  // 异步加载K线数据
  loadKlineData(fid);
}

// ===================== HELPERS ====================="""

# Step 1: 修复亚盘函数——移除K线块，恢复正常结尾
if ASIA_CURRENT_END in html:
    html = html.replace(ASIA_CURRENT_END, ASIA_FIXED_END, 1)
    print("✅ Step 1: 从renderAsianTable移除K线块")
else:
    print("⚠️  Step 1: 未找到亚盘K线块（可能已修复？）")
    # 尝试检测K线块是否在其他位置
    if 'kline-section' in html:
        # 找到kline-section在哪个函数中
        idx = html.find('kline-section')
        context = html[max(0,idx-500):idx+100]
        if 'renderAsianTable' in context or 'ASIAN ODDS' in context[max(0,context.find('kline-section')-10000):]:
            print("   K线块仍在亚盘区域，尝试宽松匹配...")

# Step 2: 在盘口解析函数末尾添加K线块
if ANALYSIS_CURRENT_END in html:
    html = html.replace(ANALYSIS_CURRENT_END, ANALYSIS_NEW_END, 1)
    print("✅ Step 2: K线块注入renderAnalysisTab末尾")
else:
    print("❌ Step 2: 未找到盘口解析结尾标记")
    # 调试：搜索实际内容
    import re
    matches = [(m.start(), html[max(0,m.start()-80):m.end()+80]) for m in re.finditer(r"html \+= '</tbody></table></div>';", html)]
    print(f"   找到 {len(matches)} 处 '</tbody></table></div>' 标记")
    for i, (pos, ctx) in enumerate(matches):
        print(f"   #{i} at pos {pos}: ...{ctx[-60:]}...")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# 验证
with open(HTML, 'r', encoding='utf-8') as f:
    verify = f.read()

asia_idx = verify.find('function renderAsianTable')
analysis_idx = verify.find('function renderAnalysisTab')
kline_idx = verify.find('kline-section')
helpers_idx = verify.find('// ===================== HELPERS')

print(f"\n📊 验证:")
print(f"   renderAsianTable at: {asia_idx}")
print(f"   renderAnalysisTab at: {analysis_idx}")
print(f"   kline-section at: {kline_idx}")
print(f"   HELPERS at: {helpers_idx}")

if asia_idx < kline_idx < analysis_idx:
    print("   ❌ K线仍在亚盘和盘口解析之间（可能在全局区域）")
elif analysis_idx < kline_idx < helpers_idx:
    print("   ✅ K线在renderAnalysisTab函数内")
else:
    print(f"   ⚠️  K线位置需确认（analysis={analysis_idx}, kline={kline_idx}, helpers={helpers_idx}）")

# 检查loadKlineData调用数量
count = verify.count('loadKlineData(fid)')
print(f"   loadKlineData调用次数: {count}（应为1）")
print(f"\n✅ 修复完成: {HTML}")
