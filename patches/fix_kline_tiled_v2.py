#!/usr/bin/env python3
"""fix_kline_tiled_v2.py - K线从Tab切换改为全部纵向铺开对比。
目标文件: live-scores-preview-v6.html
"""
import sys, os, shutil, datetime, re

TARGET = sys.argv[1] if len(sys.argv) > 1 else "live-scores-preview-v6.html"
if not os.path.exists(TARGET):
    print(f"ERROR: {TARGET} not found"); sys.exit(1)

bak = f"{TARGET}.bak.kltile_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy2(TARGET, bak)
print(f"Backup: {bak}")

h = open(TARGET, encoding="utf-8").read()
orig_len = len(h)
changes = []

# ============================================================
# 1. 替换K线区域HTML模板（单个canvas → 多canvas容器）
# ============================================================
old_html = '''  // K线蜡烛图区域
  html += `<div class="kline-section" id="kline-section-${fid}">
    <div class="kline-header">
      <span class="kline-title">📈 赔率分歧K线</span>
      <div id="kline-types-${fid}" style="display:flex;gap:4px;flex-wrap:wrap;"></div>
      <div id="kline-wins-${fid}" style="display:none;"></div>
    </div>
    <div class="kline-canvas-wrap">
      <canvas id="kline-canvas-${fid}" height="180"></canvas>
    </div>
    <div class="kline-legend" id="kline-legend-${fid}"></div>
  </div>`;'''

new_html = '''  // K线蜡烛图区域 - 全部纵向铺开
  html += `<div class="kline-section" id="kline-section-${fid}">
    <div class="kline-header">
      <span class="kline-title">📈 赔率分歧K线（全机构对比）</span>
    </div>
    <div id="kline-charts-${fid}" class="kline-charts-container"></div>
  </div>`;'''

if old_html in h:
    h = h.replace(old_html, new_html)
    changes.append("K-line HTML template replaced")
else:
    print("ERROR: K-line HTML template not found"); sys.exit(1)

# ============================================================
# 2. 替换 loadKlineData 函数
# ============================================================
old_load = '''async function loadKlineData(fid) {
  const section = document.getElementById(`kline-section-${fid}`);
  if (!section) return;
  const canvas = document.getElementById(`kline-canvas-${fid}`);
  if (!canvas) return;

  // 显示loading
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.parentElement.clientWidth || 600;
  ctx.fillStyle = '#1a1f2e';
  ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle = '#5a6a7a';
  ctx.font = '12px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('加载K线数据...', canvas.width/2, canvas.height/2);

  try {
    const resp = await fetch(`/api/v1/matches/${fid}/kline`);
    const data = await resp.json();
    if (data.status !== 'ok' || !data.candles || Object.keys(data.candles).length === 0) {
      ctx.fillStyle = '#1a1f2e'; ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.fillStyle = '#5a6a7a'; ctx.fillText('暂无K线数据', canvas.width/2, canvas.height/2);
      return;
    }
    klineState[fid] = {
      data: data,
      currentType: Object.keys(data.candles)[0],
    };
    renderKlineControls(fid);
    drawKline(fid);
  } catch(e) {
    ctx.fillStyle = '#1a1f2e'; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle = '#ef5350'; ctx.fillText('K线加载失败', canvas.width/2, canvas.height/2);
  }
}'''

new_load = '''async function loadKlineData(fid) {
  const container = document.getElementById(`kline-charts-${fid}`);
  if (!container) return;
  container.innerHTML = '<div class="kline-loading">加载K线数据...</div>';

  try {
    const resp = await fetch(`/api/v1/matches/${fid}/kline`);
    const data = await resp.json();
    if (data.status !== 'ok' || !data.candles || Object.keys(data.candles).length === 0) {
      container.innerHTML = '<div class="kline-empty">暂无K线数据</div>';
      return;
    }
    klineState[fid] = { data: data };
    renderKlineCharts(fid);
  } catch(e) {
    container.innerHTML = '<div class="kline-empty">K线加载失败</div>';
  }
}'''

if old_load in h:
    h = h.replace(old_load, new_load)
    changes.append("loadKlineData replaced")
else:
    print("ERROR: loadKlineData not found"); sys.exit(1)

# ============================================================
# 3. 替换 renderKlineControls + switchKlineType + drawKline + renderKlineLegend
#    为新的 renderKlineCharts + drawKlineChart + renderKlineLegendFor
# ============================================================
# 找边界：从 "function renderKlineControls" 到 resize listener 之前
old_block_start = 'function renderKlineControls(fid) {'
old_block_end_marker = '// 窗口resize时重绘当前可见K线'

rs = h.find(old_block_start)
re_marker = h.find(old_block_end_marker)
if rs == -1 or re_marker == -1 or rs > re_marker:
    print(f"ERROR: cannot find block bounds: rs={rs}, re={re_marker}"); sys.exit(1)

new_block = '''function renderKlineCharts(fid) {
  const st = klineState[fid];
  if (!st) return;
  const container = document.getElementById(`kline-charts-${fid}`);
  if (!container) return;
  const candles = st.data.candles;
  const availableTypes = KLINE_TYPES_ALL.filter(t =>
    candles[t.key] && candles[t.key].some(c => c.window_minutes===0 && (c.open||c.high||c.low||c.close))
  );
  if (availableTypes.length === 0) {
    container.innerHTML = '<div class="kline-empty">暂无K线数据</div>';
    return;
  }
  let html = '';
  availableTypes.forEach(t => {
    html += `<div class="kline-chart-item">
      <div class="kline-chart-label">${t.label}</div>
      <div class="kline-canvas-wrap">
        <canvas id="kline-canvas-${fid}-${t.key}" height="160"></canvas>
      </div>
      <div class="kline-legend" id="kline-legend-${fid}-${t.key}"></div>
    </div>`;
  });
  container.innerHTML = html;
  // 逐个绘制
  availableTypes.forEach(t => drawKlineChart(fid, t.key));
}

function drawKlineChart(fid, typeKey) {
  const st = klineState[fid];
  if (!st) return;
  const canvas = document.getElementById(`kline-canvas-${fid}-${typeKey}`);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const allCandles = st.data.candles[typeKey] || [];
  const candles = allCandles.filter(c => c.window_minutes === 0 && (c.open||c.high||c.low||c.close)).sort((a,b) => new Date(a.bucket_time) - new Date(b.bucket_time));
  const W = canvas.parentElement.clientWidth || 600;
  const H = 160;
  canvas.width = W; canvas.height = H;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0,0,W,H);
  if (candles.length === 0) {
    ctx.fillStyle = '#999'; ctx.font='12px sans-serif'; ctx.textAlign='center';
    ctx.fillText('\\u6682\\u65e0K\\u7ebf\\u6570\\u636e', W/2, H/2);
    return;
  }
  const padL=42, padR=8, padT=10, padB=20;
  const chartH = H - padT - padB;
  const candleW=6, candleGap=3, step=candleW+candleGap;
  const bodies = candles.map(c => Math.abs(c.close - c.open));
  const bodyMax = Math.max(...bodies, 0.001);
  const wickCap = bodyMax * 1.5;
  let minV=Infinity, maxV=-Infinity;
  candles.forEach(c => {
    const bTop = Math.max(c.open, c.close);
    const bBot = Math.min(c.open, c.close);
    c._clipH = Math.min(c.high, bTop + wickCap);
    c._clipL = Math.max(c.low, bBot - wickCap);
    minV = Math.min(minV, c._clipL);
    maxV = Math.max(maxV, c._clipH);
  });
  const range = maxV - minV || 0.01;
  const yPad = range * 0.08;
  minV -= yPad; maxV += yPad;
  const yRange = maxV - minV;
  const yOf = v => padT + chartH - ((v - minV) / yRange) * chartH;
  ctx.strokeStyle = '#e8e8e8'; ctx.lineWidth=1;
  for(let i=0;i<=4;i++){
    const y=padT+chartH*i/4;
    ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(Math.min(W-padR, padL+candles.length*step),y);ctx.stroke();
    ctx.fillStyle='#888';ctx.font='9px monospace';ctx.textAlign='right';
    ctx.fillText((maxV-yRange*i/4).toFixed(3), padL-4, y+3);
  }
  if(minV<0 && maxV>0){
    const yz=yOf(0);
    ctx.strokeStyle='#bbb';ctx.setLineDash([3,3]);
    ctx.beginPath();ctx.moveTo(padL,yz);ctx.lineTo(Math.min(W-padR, padL+candles.length*step),yz);ctx.stroke();
    ctx.setLineDash([]);
  }
  candles.forEach((c,i) => {
    const x = padL + step*i + candleW/2;
    const isDoji = Math.abs(c.close - c.open) < 0.0001;
    const isUp = c.close >= c.open;
    const color = isUp ? '#d32f2f' : '#1565c0';
    ctx.strokeStyle=color;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,yOf(c._clipH));ctx.lineTo(x,yOf(c._clipL));ctx.stroke();
    if (isDoji) {
      const yC = yOf(c.close); ctx.lineWidth=1.5;
      ctx.beginPath();ctx.moveTo(x-candleW/2,yC);ctx.lineTo(x+candleW/2,yC);ctx.stroke();
    } else {
      const yO=yOf(c.open), yC=yOf(c.close);
      ctx.fillStyle=color;
      ctx.fillRect(x-candleW/2, Math.min(yO,yC), candleW, Math.max(1,Math.abs(yC-yO)));
    }
  });
  const maxLabels = Math.floor((W - padL - padR) / 44);
  const labelStep = Math.max(1, Math.ceil(candles.length / maxLabels));
  ctx.font='8px monospace';ctx.textAlign='center';
  let lastDay = '', lastBw = -1;
  candles.forEach((c,i) => {
    const isLast = (i === candles.length - 1);
    if (i % labelStep !== 0 && !isLast) return;
    const x = padL + step*i + candleW/2;
    if (x > W - padR - 20) return;
    const bj = new Date(new Date(c.bucket_time).getTime() + 8*3600000);
    const dayStr = String(bj.getUTCMonth()+1).padStart(2,'0')+'/'+String(bj.getUTCDate()).padStart(2,'0');
    const timeStr = String(bj.getUTCHours()).padStart(2,'0')+':'+String(bj.getUTCMinutes()).padStart(2,'0');
    const bw = c.bucket_width_minutes || 0;
    const dayChg = (dayStr !== lastDay);
    const phaseChg = (lastBw >= 0 && bw !== lastBw);
    let lbl, col;
    if (dayChg) { lbl=dayStr; col='#555'; }
    else if (phaseChg) { lbl=dayStr; col='#777'; }
    else { lbl=timeStr; col='#999'; }
    ctx.fillStyle=col; ctx.fillText(lbl, x, H-6);
    lastDay=dayStr; lastBw=bw;
  });
  renderKlineLegendFor(fid, typeKey, st);
}

function renderKlineLegendFor(fid, typeKey, st) {
  const legendEl = document.getElementById(`kline-legend-${fid}-${typeKey}`);
  if (!legendEl) return;
  const patterns = (st.data.patterns && st.data.patterns[typeKey]) || [];
  const tagColors = st.data.tag_colors || {};
  const ktypeInfo = st.data.kline_types && st.data.kline_types[typeKey];
  const count = ktypeInfo ? ktypeInfo.candle_count : 0;

  let html = `<span><span class="dot" style="background:#d32f2f"></span>分歧收窄</span>
    <span><span class="dot" style="background:#1565c0"></span>分歧扩大</span>
    <span style="color:var(--text-muted);">共${count}根</span>`;

  patterns.forEach(p => {
    (p.tags||[]).forEach(tag => {
      const color = tagColors[tag] || '#78909c';
      html += `<span class="kline-pattern" style="background:${color}20;color:${color};border:1px solid ${color}40;">${tag}</span>`;
    });
  });

  legendEl.innerHTML = html;
}

'''

h = h[:rs] + new_block + h[re_marker:]
changes.append("renderKlineControls+switchKlineType+drawKline+renderKlineLegend replaced with tiled version")

# ============================================================
# 4. 替换resize事件监听
# ============================================================
old_resize = '''// 窗口resize时重绘当前可见K线
window.addEventListener('resize', () => {
  Object.keys(klineState).forEach(fid => {
    const section = document.getElementById(`kline-section-${fid}`);
    if (section && section.offsetParent !== null) {
      drawKline(fid);
    }
  });
});'''

new_resize = '''// 窗口resize时重绘当前可见K线
window.addEventListener('resize', () => {
  Object.keys(klineState).forEach(fid => {
    const section = document.getElementById(`kline-section-${fid}`);
    if (section && section.offsetParent !== null) {
      const st = klineState[fid];
      if (st && st.data && st.data.candles) {
        KLINE_TYPES_ALL.forEach(t => {
          if (st.data.candles[t.key]) drawKlineChart(fid, t.key);
        });
      }
    }
  });
});'''

if old_resize in h:
    h = h.replace(old_resize, new_resize)
    changes.append("resize listener updated")
else:
    print("WARN: resize listener not found exactly, skipping")

# ============================================================
# 5. 新增CSS样式
# ============================================================
old_css = '.kline-loading{text-align:center;padding:12px;color:var(--text-muted);font-size:0.6rem;}'
new_css = '''].kline-loading{text-align:center;padding:12px;color:var(--text-muted);font-size:0.6rem;}
.kline-charts-container{display:flex;flex-direction:column;gap:12px;}
.kline-chart-item{border:1px solid var(--border-color);border-radius:6px;padding:8px;background:rgba(255,255,255,0.02);}
.kline-chart-label{font-size:0.65rem;font-weight:600;color:var(--text-secondary);margin-bottom:4px;padding-left:2px;}'''

if old_css in h:
    h = h.replace(old_css, new_css)
    changes.append("CSS added for tiled charts")
else:
    print("WARN: CSS anchor not found, trying alternate...")

# ============================================================
# 写入并验证
# ============================================================
open(TARGET, "w", encoding="utf-8").write(h)

v = open(TARGET, encoding="utf-8").read()
print("\n=== VERIFICATION ===")
print(f"File size: {orig_len} -> {len(v)} (delta {len(v)-orig_len})")
print(f"renderKlineCharts: {v.count('renderKlineCharts')}")
print(f"drawKlineChart: {v.count('drawKlineChart')}")
print(f"drawKline (old, should be 0): {v.count('function drawKline(')}")
print(f"switchKlineType (should be 0): {v.count('function switchKlineType')}")
print(f"renderKlineControls (should be 0): {v.count('function renderKlineControls')}")
print(f"renderKlineLegendFor: {v.count('renderKlineLegendFor')}")
old_canvas_id = 'kline-canvas-${fid}"'
print(f"kline-canvas single (old, should be 0): {v.count(old_canvas_id)}")
print(f"kline-charts-container: {v.count('kline-charts-container')}")
print(f"kline-chart-item: {v.count('kline-chart-item')}")

# Count functions to ensure none lost
func_count = len(re.findall(r'function\s+\w+', v))
print(f"Total function count: {func_count}")

for c in changes:
    print(f"  ✅ {c}")
print("\nDone.")
