#!/usr/bin/env python3
"""调整Tab顺序和名称：战力速览-亚洲盘口-欧洲赔率-盘口解析-泊松比分
   只改按钮区域，不碰content div（content由JS按ID填充，DOM顺序不影响显示）。
   默认active改为fundamental。"""
import shutil, re

HTML = '/opt/ruipan/static/live-scores-preview-v6.html'

# 优先从.bak_taborder恢复（Tab调整前的版本）
BAK = HTML + '.bak_taborder'
import os
if os.path.exists(BAK):
    shutil.copy2(BAK, HTML)
    print(f"✅ 从备份恢复 → {BAK}")
else:
    print("⚠️  未找到备份，基于当前文件修改")

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

if OLD_TABS in html:
    html = html.replace(OLD_TABS, NEW_TABS, 1)
    print("✅ Tab按钮顺序+名称已调整")
else:
    # 可能已经是新顺序或格式不同
    if "战力速览" in html and "亚洲盘口" in html:
        print("⚠️  按钮已是新顺序，检查content结构...")
    else:
        print("❌ 未找到原始Tab按钮区域")
        exit(1)

# 把content div的active从asian改到fundamental
# 原始: <div id="tab-asian-${fid}" class="tab-content active">
#       <div id="tab-fundamental-${fid}" class="tab-content">
old_asian_active = '<div id="tab-asian-${fid}" class="tab-content active">'
new_asian_normal = '<div id="tab-asian-${fid}" class="tab-content">'
old_fund_normal = '<div id="tab-fundamental-${fid}" class="tab-content">'
new_fund_active = '<div id="tab-fundamental-${fid}" class="tab-content active">'

if old_asian_active in html:
    html = html.replace(old_asian_active, new_asian_normal, 1)
    print("✅ asian content取消active")
if old_fund_normal in html:
    html = html.replace(old_fund_normal, new_fund_active, 1)
    print("✅ fundamental content设为active")

# 验证结构完整性：每个tab-content div都要有闭合
# 检查5个tab div存在
for tid in ['asian','euro','analysis','fundamental','oddsquick']:
    opening = f'<div id="tab-{tid}-${{fid}}" class="tab-content'
    if opening not in html:
        print(f"❌ tab-{tid} 开始标签缺失！")
        exit(1)
print("✅ 5个tab-content div开始标签完整")

# 检查renderOddsPanel函数结尾的</div>数量（应该有5个tab div+1个panel div闭合）
panel_start = html.find('<div class="panel-tabs">')
# 找到 renderOddsPanel 的 return ` 开始
return_start = html.rfind('return `', 0, panel_start)
# 找到函数结束（`;}  ）
func_end = html.find('`;\n}', panel_start)
panel_section = html[return_start:func_end+3]
open_divs = panel_section.count('<div')
close_divs = panel_section.count('</div>')
print(f"📊 renderOddsPanel中 <div>={open_divs} </div>={close_divs}")
if open_divs != close_divs:
    print("❌ div不匹配！结构损坏")
    exit(1)

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# 最终验证按钮顺序
btn_sec = html[html.find('<div class="panel-tabs">'):html.find('<div class="panel-tabs">')+600]
btns = re.findall(r"switchTab\(\$\{fid\},'(\w+)'", btn_sec)
labels = re.findall(r'>([^<]+)</button>', btn_sec)
print(f"\n📊 按钮顺序: {list(zip(labels, btns))}")
assert btns == ['fundamental','asian','euro','analysis','oddsquick']
assert labels == ['战力速览','亚洲盘口','欧洲赔率','盘口解析','泊松比分']
print("\n✅ 全部验证通过！")
