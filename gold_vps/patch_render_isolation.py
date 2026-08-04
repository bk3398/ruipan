#!/usr/bin/env python3
"""
patch_render_isolation.py
修复列表页盘口解析Tab空白：将loadOddsData中5个render函数改为独立try-catch，
Promise.all改为allSettled，单个接口/渲染失败不影响其他Tab。
"""
import re, shutil, os, datetime

HTML_PATH = "/opt/ruipan/static/live-scores-preview-v6.html"
BACKUP_PATH = HTML_PATH + f".bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

# 1. Backup
shutil.copy2(HTML_PATH, BACKUP_PATH)
print(f"备份: {BACKUP_PATH}")

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

original_len = len(html)

# 2. Replace Promise.all with Promise.allSettled + safe JSON parsing
old_promise = """const [tlResp, anResp, fundResp, oqResp] = await Promise.all([
      fetch(`/api/v1/matches/${fid}/odds-timeline`),
      fetch(`/api/v1/matches/${fid}/analysis`),
      fetch(`/api/v1/matches/${fid}/fundamental`),
      fetch(`/api/v1/matches/${fid}/odds-quick`)
    ]);
    const tlData = await tlResp.json();
    const anData = await anResp.json();
    const fundData = await fundResp.json();
    const oqData = await oqResp.json();"""

new_promise = """const results = await Promise.allSettled([
      fetch(`/api/v1/matches/${fid}/odds-timeline`).then(r=>r.json()).catch(()=>null),
      fetch(`/api/v1/matches/${fid}/analysis`).then(r=>r.json()).catch(()=>null),
      fetch(`/api/v1/matches/${fid}/fundamental`).then(r=>r.json()).catch(()=>null),
      fetch(`/api/v1/matches/${fid}/odds-quick`).then(r=>r.json()).catch(()=>null)
    ]);
    const tlData = results[0].status === 'fulfilled' ? results[0].value : null;
    const anData = results[1].status === 'fulfilled' ? results[1].value : null;
    const fundData = results[2].status === 'fulfilled' ? results[2].value : null;
    const oqData = results[3].status === 'fulfilled' ? results[3].value : null;
    if (!tlData) console.error('odds-timeline failed for', fid);
    if (!anData) console.error('analysis failed for', fid);
    if (!fundData) console.error('fundamental failed for', fid);
    if (!oqData) console.error('odds-quick failed for', fid);"""

if old_promise in html:
    html = html.replace(old_promise, new_promise)
    print("✅ Promise.all → allSettled + safe parse")
else:
    print("⚠️ Promise.all pattern not found, trying flexible match...")
    # Try regex
    pattern = r'const \[tlResp, anResp, fundResp, oqResp\] = await Promise\.all\(\[.*?\]\);\s*const tlData = await tlResp\.json\(\);\s*const anData = await anResp\.json\(\);\s*const fundData = await fundResp\.json\(\);\s*const oqData = await oqResp\.json\(\);'
    if re.search(pattern, html, re.DOTALL):
        html = re.sub(pattern, new_promise, html, flags=re.DOTALL)
        print("✅ Promise.all replaced via regex")
    else:
        print("❌ Could not find Promise.all pattern!")

# 3. Replace sequential render calls with independent try-catch
old_renders = """renderAsianTable(fid, tlData, isMatchLive, hasStarted, isFinished);
    renderEuroTable(fid, tlData, isMatchLive, hasStarted, isFinished);
    renderAnalysisTab(fid, anData, isMatchLive, hasStarted);
    renderFundamentalTab(fid, fundData, match);
    renderOddsQuickTab(fid, oqData, match, tlData);"""

new_renders = """try { if(tlData) renderAsianTable(fid, tlData, isMatchLive, hasStarted, isFinished); else {const el=document.getElementById('tab-asian-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#999;text-align:center">暂无数据</div>';} } catch(e) { console.error('renderAsianTable error:', e); const el=document.getElementById('tab-asian-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#f66;text-align:center">渲染异常</div>'; }
    try { if(tlData) renderEuroTable(fid, tlData, isMatchLive, hasStarted, isFinished); else {const el=document.getElementById('tab-euro-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#999;text-align:center">暂无数据</div>';} } catch(e) { console.error('renderEuroTable error:', e); const el=document.getElementById('tab-euro-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#f66;text-align:center">渲染异常</div>'; }
    try { if(anData) renderAnalysisTab(fid, anData, isMatchLive, hasStarted); else {const el=document.getElementById('tab-analysis-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#999;text-align:center">暂无数据</div>';} } catch(e) { console.error('renderAnalysisTab error:', e); const el=document.getElementById('tab-analysis-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#f66;text-align:center">渲染异常: '+e.message+'</div>'; }
    try { if(fundData) renderFundamentalTab(fid, fundData, match); else {const el=document.getElementById('tab-fund-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#999;text-align:center">暂无数据</div>';} } catch(e) { console.error('renderFundamentalTab error:', e); const el=document.getElementById('tab-fund-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#f66;text-align:center">渲染异常</div>'; }
    try { if(oqData) renderOddsQuickTab(fid, oqData, match, tlData); else {const el=document.getElementById('tab-quick-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#999;text-align:center">暂无数据</div>';} } catch(e) { console.error('renderOddsQuickTab error:', e); const el=document.getElementById('tab-quick-'+fid);if(el)el.innerHTML='<div style="padding:16px;color:#f66;text-align:center">渲染异常</div>'; }"""

if old_renders in html:
    html = html.replace(old_renders, new_renders)
    print("✅ 5个render函数改为独立try-catch")
else:
    print("⚠️ Render calls pattern not found exactly, trying flexible...")
    # Try to find and replace the render block
    pattern = r'renderAsianTable\(fid.*?renderOddsQuickTab\(fid, oqData, match, tlData\);'
    if re.search(pattern, html, re.DOTALL):
        html = re.sub(pattern, new_renders, html, flags=re.DOTALL)
        print("✅ Render calls replaced via regex")
    else:
        print("❌ Could not find render calls pattern!")

# 4. Also check if tab-analysis element ID uses different naming
# Search for how the tab container is created
tab_id_patterns = re.findall(r"""id=["']tab-[^"']*["']""", html)
unique_tab_ids = set(tab_id_patterns)
print(f"\n页面中所有tab元素ID模式: {unique_tab_ids}")

# 5. Write
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

new_len = len(html)
print(f"\n文件大小: {original_len} → {new_len} bytes (diff: {new_len-original_len})")
print("✅ 补丁应用完成！刷新页面试试（Ctrl+Shift+R 强制刷新清缓存）")
print(f"💾 原文件备份: {BACKUP_PATH}")
