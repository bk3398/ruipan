#!/usr/bin/env python3
"""调整Tab顺序和名称：战力速览-亚洲盘口-欧洲赔率-盘口解析-泊松比分
   默认激活Tab改为战力速览(fundamental)"""
import shutil, re

HTML = '/opt/ruipan/static/live-scores-preview-v6.html'
BAK = HTML + '.bak_taborder'

shutil.copy2(HTML, BAK)
print(f"✅ 备份 → {BAK}")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

OLD_TABS = """    <div class="panel-tabs">
      <button class="panel-tab active" onclick="switchTab(${fid},'asian',this)">亚盘</button>
      <button class="panel-tab" onclick="switchTab(${fid},'euro',this)">欧赔</button>
      <button class="panel-tab" onclick="switchTab(${fid},'analysis',this)">盘口解析</button>
      <button class="panel-tab" onclick="switchTab(${fid},'fundamental',this)">战力速览</button>
      <button class="panel-tab" onclick="switchTab(${fid},'oddsquick',this)">泊松欧赔</button>
    </div>"""

NEW_TABS = """    <div class="panel-tabs">
      <button class="panel-tab active" onclick="switchTab(${fid},'fundamental',this)">战力速览</button>
      <button class="panel-tab" onclick="switchTab(${fid},'asian',this)">亚洲盘口</button>
      <button class="panel-tab" onclick="switchTab(${fid},'euro',this)">欧洲赔率</button>
      <button class="panel-tab" onclick="switchTab(${fid},'analysis',this)">盘口解析</button>
      <button class="panel-tab" onclick="switchTab(${fid},'oddsquick',this)">泊松比分</button>
    </div>"""

if OLD_TABS not in html:
    print("❌ 未找到原始Tab按钮区域（可能已调整过？）")
    exit(1)

html = html.replace(OLD_TABS, NEW_TABS, 1)
print("✅ Tab按钮顺序+名称已调整")

# 提取并重排tab-content divs
tab_ids = ['asian', 'euro', 'analysis', 'fundamental', 'oddsquick']
panel_start = html.find('<div class="panel-tabs">')

content_blocks = {}
for tid in tab_ids:
    pattern = f'<div id="tab-{tid}-${{fid}}" class="tab-content'
    idx = html.find(pattern, panel_start)
    if idx == -1:
        print(f"❌ 找不到 tab-{tid}")
        exit(1)
    close_idx = html.find('</div>', idx) + len('</div>')
    content_blocks[tid] = html[idx:close_idx]

new_order = ['fundamental', 'asian', 'euro', 'analysis', 'oddsquick']

first_pattern = f'<div id="tab-{tab_ids[0]}-${{fid}}" class="tab-content'
first_start = html.find(first_pattern, panel_start)
last_pattern = f'<div id="tab-{tab_ids[-1]}-${{fid}}" class="tab-content'
last_start = html.find(last_pattern, panel_start)
last_close = html.find('</div>', last_start) + len('</div>')

new_blocks = []
for tid in new_order:
    block = content_blocks[tid]
    if tid == 'fundamental':
        if 'class="tab-content active"' not in block:
            block = block.replace('class="tab-content"', 'class="tab-content active"', 1)
    else:
        block = block.replace('class="tab-content active"', 'class="tab-content"')
    new_blocks.append(block)

html = html[:first_start] + '\n    '.join(new_blocks) + html[last_close:]
print("✅ Tab content div顺序已调整，fundamental设为默认active")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# 验证
with open(HTML, 'r') as f:
    v = f.read()

btn_sec = v[v.find('<div class="panel-tabs">'):v.find('<div class="panel-tabs">')+600]
btns = re.findall(r"switchTab\(\$\{fid\},'(\w+)'", btn_sec)
labels = re.findall(r'>([^<]+)</button>', btn_sec)
print(f"\n📊 按钮顺序: {list(zip(labels, btns))}")
assert btns == new_order, f"顺序错误: {btns}"
assert labels == ['战力速览','亚洲盘口','欧洲赔率','盘口解析','泊松比分']

content_sec = v[first_start:last_start+500]
div_ids = re.findall(r'id="tab-(\w+)-\$\{fid\}"', content_sec)
active_count = content_sec.count('tab-content active')
print(f"📊 Content顺序: {div_ids}, active块数: {active_count}")
assert div_ids == new_order
assert active_count == 1

print("\n✅ 全部验证通过！")
