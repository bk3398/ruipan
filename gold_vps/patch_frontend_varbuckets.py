#!/usr/bin/env python3
"""
前端K线改造补丁：
1. 去掉窗口切换按钮（变频率时间桶只有一条序列）
2. 蜡烛紧凑左对齐，不拉满页面
3. 无变化节点（open==close）画十字线而非横杠
"""
import re

HTML_PATH = '/opt/ruipan/static/live-scores-preview-v6.html'

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

# 备份
bak = HTML_PATH + '.bak_varbuckets'
with open(bak, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"✅ 备份 → {bak}")

# ── 1. 去掉KLINE_WINDOWS和窗口按钮相关代码 ──

# 删除KLINE_WINDOWS常量
html = html.replace(
    "const KLINE_WINDOWS = [10, 30, 60, 120];\n",
    ""
)

# 删除renderKlineControls中的窗口按钮渲染
old_wins_render = """  // 窗口按钮
  winsEl.innerHTML = KLINE_WINDOWS.map(w =>
    `<button class="kline-win-btn ${w===st.currentWin?'active':''}"
      onclick="switchKlineWin(${fid},${w})">${w}m</button>`
  ).join('');"""
new_wins_render = "  winsEl.innerHTML = ''; // 变频率时间桶，不需要窗口切换"
html = html.replace(old_wins_render, new_wins_render)

# 删除switchKlineWin函数
old_switch_win = """function switchKlineWin(fid, win) {
  if (!klineState[fid]) return;
  klineState[fid].currentWin = win;
  renderKlineControls(fid);
  drawKline(fid);
}

"""
html = html.replace(old_switch_win, "")

# loadKlineData中去掉currentWin
html = html.replace(
    "      currentWin: 30\n",
    ""
)

# ── 2. 重写drawKline函数：紧凑左对齐 + 十字线 ──

old_draw = """function drawKline(fid) {
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
}"""

new_draw = """function drawKline(fid) {
  const st = klineState[fid];
  if (!st) return;
  const canvas = document.getElementById(`kline-canvas-${fid}`);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  // 变频率时间桶：window_minutes=0，取所有蜡烛按时间排序
  const allCandles = st.data.candles[st.currentType] || [];
  const candles = allCandles
    .filter(c => c.window_minutes === 0)
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
    ctx.fillText('暂无K线数据', W/2, H/2);
    return;
  }

  const padL=42, padR=8, padT=12, padB=22;
  const chartH = H - padT - padB;

  // 紧凑左对齐：固定蜡烛宽度+间距，不铺满
  const candleW = 6;       // 蜡烛实体宽度
  const candleGap = 3;     // 蜡烛间距
  const step = candleW + candleGap;
  const chartW = candles.length * step;

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

  // 网格线
  ctx.strokeStyle = '#1e2533'; ctx.lineWidth=1;
  for(let i=0;i<=4;i++){
    const y=padT+chartH*i/4;
    ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(Math.min(W-padR, padL+chartW),y);ctx.stroke();
    const val=maxV-yRange*i/4;
    ctx.fillStyle='#5a6a7a';ctx.font='9px monospace';ctx.textAlign='right';
    ctx.fillText(val.toFixed(3), padL-4, y+3);
  }

  // 零轴
  if(minV<0 && maxV>0){
    const yz=yOf(0);
    ctx.strokeStyle='#3a4a5a';ctx.setLineDash([3,3]);
    ctx.beginPath();ctx.moveTo(padL,yz);ctx.lineTo(Math.min(W-padR, padL+chartW),yz);ctx.stroke();
    ctx.setLineDash([]);
  }

  // 画蜡烛
  candles.forEach((c,i) => {
    const x = padL + step*i + candleW/2;
    const isDoji = Math.abs(c.close - c.open) < 0.0001;
    const isUp = c.close >= c.open;
    const color = isUp ? '#26a69a' : '#ef5350';

    // 影线（high到low）
    ctx.strokeStyle=color;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,yOf(c.high));ctx.lineTo(x,yOf(c.low));ctx.stroke();

    if (isDoji) {
      // 十字线：无变化时画水平横线（开盘=收盘位置）
      const yC = yOf(c.close);
      ctx.strokeStyle=color;ctx.lineWidth=1.5;
      ctx.beginPath();
      ctx.moveTo(x - candleW/2, yC);
      ctx.lineTo(x + candleW/2, yC);
      ctx.stroke();
    } else {
      // 实体
      const yO=yOf(c.open), yC=yOf(c.close);
      const top=Math.min(yO,yC), h=Math.max(1,Math.abs(yC-yO));
      ctx.fillStyle=color;
      ctx.fillRect(x-candleW/2, top, candleW, h);
    }
  });

  // X轴时间标签（均匀选8个）
  ctx.fillStyle='#5a6a7a';ctx.font='8px monospace';ctx.textAlign='center';
  const labelStep=Math.max(1,Math.floor(candles.length/8));
  candles.forEach((c,i)=>{
    if(i%labelStep!==0 && i!==candles.length-1) return;
    const x=padL+step*i+candleW/2;
    const dt=new Date(c.bucket_time);
    const bj=new Date(dt.getTime()+8*3600000);
    const lbl=String(bj.getUTCHours()).padStart(2,'0')+':'+String(bj.getUTCMinutes()).padStart(2,'0');
    ctx.fillText(lbl, x, H-6);
  });

  // 渲染形态标签
  renderKlineLegend(fid, st);
}"""

if old_draw in html:
    html = html.replace(old_draw, new_draw)
    print("✅ drawKline函数已替换（紧凑左对齐+十字线）")
else:
    print("❌ 未找到drawKline函数，尝试正则匹配...")
    # 用正则匹配
    pattern = r'function drawKline\(fid\) \{.*?\n\}'
    match = re.search(pattern, html, re.DOTALL)
    if match:
        html = html[:match.start()] + new_draw + html[match.end():]
        print("✅ drawKline函数已通过正则替换")
    else:
        print("❌ 完全无法匹配drawKline，手动检查！")
        import sys; sys.exit(1)

# ── 3. 去掉HTML中wins div的margin-left:auto（因为没内容了）──
html = html.replace(
    '<div id="kline-wins-${fid}" style="display:flex;gap:3px;margin-left:auto;"></div>',
    '<div id="kline-wins-${fid}" style="display:none;"></div>'
)

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)
print("✅ 写入完成")

# 验证
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    v = f.read()

checks = [
    ('KLINE_WINDOWS已删除', 'KLINE_WINDOWS' not in v),
    ('switchKlineWin已删除', 'switchKlineWin' not in v),
    ('currentWin已删除', 'currentWin' not in v),
    ('window_minutes===0过滤', 'c.window_minutes === 0' in v),
    ('固定蜡烛宽度6px', 'candleW = 6' in v),
    ('十字线逻辑', 'isDoji' in v),
    ('紧凑左对齐', 'candles.length * step' in v),
]
for name, ok in checks:
    print(f"  {'✅' if ok else '❌'} {name}")
