#!/usr/bin/env python3
"""
前端补丁：在盘口解析Tab表格后添加K线蜡烛图区域
纯Canvas绘制，4种K线类型切换，10/30/60/120分钟窗口切换
用法: python3 patch_frontend_kline.py
"""
import re, shutil, os

HTML_PATH = '/opt/ruipan/static/live-scores-preview-v6.html'
BACKUP = HTML_PATH + '.bak_kline'

# 备份
if not os.path.exists(BACKUP):
    shutil.copy2(HTML_PATH, BACKUP)
    print(f"✅ 备份 → {BACKUP}")

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

if 'kline-canvas' in html:
    print("⚠️ K线图已存在，跳过")
    exit(0)

# ============================================================
# 1. CSS 样式（在 </style> 前插入）
# ============================================================
KLINE_CSS = """
/* ===== K线蜡烛图 ===== */
.kline-section{margin-top:10px;border-top:1px solid var(--border-color);padding-top:8px;}
.kline-header{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px;}
.kline-title{font-size:0.7rem;font-weight:600;color:var(--text-secondary);}
.kline-type-btn{font-size:0.55rem;padding:3px 8px;border-radius:4px;border:1px solid var(--border-color);background:var(--bg-card);color:var(--text-secondary);cursor:pointer;transition:all .15s;}
.kline-type-btn.active{background:var(--accent-cyan);color:#000;border-color:var(--accent-cyan);font-weight:600;}
.kline-win-btn{font-size:0.5rem;padding:2px 6px;border-radius:3px;border:1px solid var(--border-color);background:transparent;color:var(--text-muted);cursor:pointer;}
.kline-win-btn.active{background:var(--bg-hover);color:var(--text-primary);font-weight:600;}
.kline-canvas-wrap{position:relative;width:100%;overflow-x:auto;}
.kline-canvas-wrap canvas{display:block;}
.kline-legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px;font-size:0.5rem;color:var(--text-muted);}
.kline-legend span{display:inline-flex;align-items:center;gap:3px;}
.kline-legend .dot{width:8px;height:8px;border-radius:50%;display:inline-block;}
.kline-pattern{display:inline-block;font-size:0.5rem;padding:2px 6px;border-radius:3px;margin-left:4px;font-weight:600;}
.kline-empty{text-align:center;padding:20px;color:var(--text-muted);font-size:0.6rem;}
.kline-loading{text-align:center;padding:12px;color:var(--text-muted);font-size:0.6rem;}
"""

html = html.replace('</style>', KLINE_CSS + '\n</style>', 1)

# ============================================================
# 2. 在 renderAnalysisTab 的 html += '</tbody></table></div>'; 后追加K线容器
# ============================================================
OLD_ANALYSIS_END = "  html += '</tbody></table></div>';\n  el.innerHTML = html;\n}"

NEW_ANALYSIS_END = """  html += '</tbody></table></div>';

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

// ===================== KLINE CHART =====================
const KLINE_TYPES_ALL = [
  {key:'div_asia_crown', label:'皇冠亚盘'},
  {key:'div_asia_macau', label:'澳彩亚盘'},
  {key:'div_cross_crown_macau', label:'跨庄分歧'},
  {key:'euro_dispersion', label:'欧赔离散'}
];
const KLINE_WINDOWS = [10, 30, 60, 120];
const klineState = {}; // fid -> {data, currentType, currentWin}

async function loadKlineData(fid) {
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
      currentWin: 30
    };
    renderKlineControls(fid);
    drawKline(fid);
  } catch(e) {
    ctx.fillStyle = '#1a1f2e'; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle = '#ef5350'; ctx.fillText('K线加载失败', canvas.width/2, canvas.height/2);
  }
}

function renderKlineControls(fid) {
  const st = klineState[fid];
  const data = st.data;
  const typesEl = document.getElementById(`kline-types-${fid}`);
  const winsEl = document.getElementById(`kline-wins-${fid}`);
  if (!typesEl || !winsEl) return;

  // 类型按钮 - 只显示有数据的类型
  typesEl.innerHTML = KLINE_TYPES_ALL
    .filter(t => data.candles[t.key] && data.candles[t.key].length > 0)
    .map(t => `<button class="kline-type-btn ${t.key===st.currentType?'active':''}"
      onclick="switchKlineType(${fid},'${t.key}')">${t.label}</button>`).join('');

  // 窗口按钮
  winsEl.innerHTML = KLINE_WINDOWS.map(w =>
    `<button class="kline-win-btn ${w===st.currentWin?'active':''}"
      onclick="switchKlineWin(${fid},${w})">${w}m</button>`
  ).join('');
}

function switchKlineType(fid, type) {
  if (!klineState[fid]) return;
  klineState[fid].currentType = type;
  renderKlineControls(fid);
  drawKline(fid);
}

function switchKlineWin(fid, win) {
  if (!klineState[fid]) return;
  klineState[fid].currentWin = win;
  renderKlineControls(fid);
  drawKline(fid);
}

function drawKline(fid) {
  const st = klineState[fid];
  if (!st) return;
  const canvas = document.getElementById(`kline-canvas-${fid}`);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const allCandles = st.data.candles[st.currentType] || [];
  const candles = allCandles.filter(c => c.window_minutes === st.currentWin)
    .sort((a,b) => new Date(a.bucket_time) - new Date(b.bucket_time));

  const W = canvas.parentElement.clientWidth || 600;
  const H = 180;
  canvas.width = W;
  canvas.height = H;

  // 背景
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0,0,W,H);

  if (candles.length === 0) {
    ctx.fillStyle = '#5a6a7a'; ctx.font='12px sans-serif'; ctx.textAlign='center';
    ctx.fillText('该窗口暂无数据', W/2, H/2);
    return;
  }

  const padL=42, padR=8, padT=12, padB=22;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  // 计算Y范围
  let minV=Infinity, maxV=-Infinity;
  candles.forEach(c => {
    minV = Math.min(minV, c.low);
    maxV = Math.max(maxV, c.high);
  });
  const range = maxV - minV || 0.01;
  const yPad = range * 0.1;
  minV -= yPad; maxV += yPad;
  const yRange = maxV - minV;

  const yOf = v => padT + chartH - ((v - minV) / yRange) * chartH;
  const candleW = Math.max(2, Math.min(12, chartW / candles.length * 0.6));
  const step = chartW / candles.length;

  // 网格线
  ctx.strokeStyle = '#1e2533'; ctx.lineWidth=1;
  for(let i=0;i<=4;i++){
    const y=padT+chartH*i/4;
    ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(W-padR,y);ctx.stroke();
    const val=maxV-yRange*i/4;
    ctx.fillStyle='#5a6a7a';ctx.font='9px monospace';ctx.textAlign='right';
    ctx.fillText(val.toFixed(3), padL-4, y+3);
  }

  // 零轴（如果范围跨0）
  if(minV<0 && maxV>0){
    const yz=yOf(0);
    ctx.strokeStyle='#3a4a5a';ctx.setLineDash([3,3]);
    ctx.beginPath();ctx.moveTo(padL,yz);ctx.lineTo(W-padR,yz);ctx.stroke();
    ctx.setLineDash([]);
  }

  // 画蜡烛
  candles.forEach((c,i) => {
    const x = padL + step*i + step/2;
    const isUp = c.close >= c.open;
    const color = isUp ? '#26a69a' : '#ef5350';

    // 影线
    ctx.strokeStyle=color;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,yOf(c.high));ctx.lineTo(x,yOf(c.low));ctx.stroke();

    // 实体
    const yO=yOf(c.open), yC=yOf(c.close);
    const top=Math.min(yO,yC), h=Math.max(1,Math.abs(yC-yO));
    ctx.fillStyle=color;
    ctx.fillRect(x-candleW/2, top, candleW, h);
  });

  // X轴时间标签（最多6个）
  ctx.fillStyle='#5a6a7a';ctx.font='8px monospace';ctx.textAlign='center';
  const labelStep=Math.max(1,Math.floor(candles.length/6));
  candles.forEach((c,i)=>{
    if(i%labelStep!==0 && i!==candles.length-1) return;
    const x=padL+step*i+step/2;
    const dt=new Date(c.bucket_time);
    // 转北京时间
    const bj=new Date(dt.getTime()+8*3600000);
    const lbl=String(bj.getUTCHours()).padStart(2,'0')+':'+String(bj.getUTCMinutes()).padStart(2,'0');
    ctx.fillText(lbl, x, H-6);
  });

  // 渲染形态标签
  renderKlineLegend(fid, st);
}

function renderKlineLegend(fid, st) {
  const legendEl = document.getElementById(`kline-legend-${fid}`);
  if (!legendEl) return;
  const patterns = (st.data.patterns && st.data.patterns[st.currentType]) || [];
  const tagColors = st.data.tag_colors || {};
  const ktypeInfo = st.data.kline_types && st.data.kline_types[st.currentType];
  const count = ktypeInfo ? ktypeInfo.candle_count : 0;

  let html = `<span><span class="dot" style="background:#26a69a"></span>分歧收窄</span>
    <span><span class="dot" style="background:#ef5350"></span>分歧扩大</span>
    <span style="color:var(--text-muted);">共${count}根</span>`;

  patterns.forEach(p => {
    (p.tags||[]).forEach(tag => {
      const color = tagColors[tag] || '#78909c';
      html += `<span class="kline-pattern" style="background:${color}20;color:${color};border:1px solid ${color}40;">${tag}</span>`;
    });
  });

  legendEl.innerHTML = html;
}

// 窗口resize时重绘当前可见K线
window.addEventListener('resize', () => {
  Object.keys(klineState).forEach(fid => {
    const section = document.getElementById(`kline-section-${fid}`);
    if (section && section.offsetParent !== null) {
      drawKline(fid);
    }
  });
});"""

if OLD_ANALYSIS_END not in html:
    print("❌ 找不到 renderAnalysisTab 结尾标记，尝试宽松匹配...")
    # Try to find the pattern more flexibly
    pattern = r"  html \+= '</tbody></table></div>';\n  el\.innerHTML = html;\n\}"
    match = re.search(pattern, html)
    if match:
        html = html[:match.start()] + NEW_ANALYSIS_END + html[match.end():]
        print("✅ 宽松匹配成功")
    else:
        print("❌ 完全找不到插入点，请手动检查")
        exit(1)
else:
    html = html.replace(OLD_ANALYSIS_END, NEW_ANALYSIS_END, 1)

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"✅ 补丁完成：{HTML_PATH}")
print("   - CSS样式已添加")
print("   - K线蜡烛图Canvas已插入盘口解析Tab")
print("   - 4种K线类型/4种时间窗口切换")
print("   - 形态标签颜色映射")
