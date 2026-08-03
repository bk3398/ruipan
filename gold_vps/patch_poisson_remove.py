#!/usr/bin/env python3
"""从renderAnalysisTab中删除泊松区块（泊松已有独立的'泊松欧赔'Tab）。
同时删除已无用的POISSON辅助函数段（_pmf/_scoreProbs/poissonCalc/poissonBlockHTML），
因为renderOddsQuickTab用的是后端返回的poisson数据，不依赖这些前端函数。
"""
FILE = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1. 找到并删除 renderAnalysisTab 中的泊松块
# 特征：从 "  // ===== 泊松模型" 注释开始，到 catch 行结束，在 el.innerHTML = html; 之前
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if '// ===== 泊松模型' in line and start_idx is None:
        # 确认在 renderAnalysisTab 内（向后找 el.innerHTML）
        for j in range(i, min(i+30, len(lines))):
            if 'el.innerHTML = html;' in lines[j]:
                start_idx = i
                # 找到 catch 行结尾
                for k in range(i, j):
                    if 'catch(e)' in lines[k] or 'console.warn' in lines[k]:
                        end_idx = k
                break
        if start_idx is not None:
            break

if start_idx is not None and end_idx is not None:
    print(f"Removing poisson block from renderAnalysisTab: lines {start_idx+1}-{end_idx+1}")
    del lines[start_idx:end_idx+1]
else:
    print("WARN: poisson block in renderAnalysisTab not found or already removed")

# 2. 删除 POISSON 辅助函数段（从 // ===================== POISSON =====================
#    到下一个 // ==== 或 function render）
ps_start = None
ps_end = None
for i, line in enumerate(lines):
    if '// ===================== POISSON =====================' in line:
        ps_start = i
        # 找到段尾：下一个 // ==== 注释或空行后的function
        for j in range(i+1, min(i+200, len(lines))):
            if lines[j].startswith('// ====') and 'POISSON' not in lines[j]:
                ps_end = j
                break
            if lines[j].startswith('function render') and j > i+5:
                ps_end = j
                break
        break

if ps_start is not None and ps_end is not None:
    print(f"Removing POISSON helper functions: lines {ps_start+1}-{ps_end}")
    del lines[ps_start:ps_end]
else:
    print("WARN: POISSON helper section not found")

# 3. 清理残留的空行（连续3个以上空行压缩为2个）
text = ''.join(lines)
while '\n\n\n\n' in text:
    text = text.replace('\n\n\n\n', '\n\n\n')

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(text)
print("OK - poisson removed from analysis tab, helpers cleaned up")
