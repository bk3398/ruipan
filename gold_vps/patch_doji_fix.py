#!/usr/bin/env python3
"""
前端补丁：K线十字星修复
━━━━━━━━━━━━━━━━━━━━━━
问题：o=h=l=c=0时影线零长度，只剩水平细线，看起来不像十字星
修复：doji蜡烛画真正的十字形——水平横线 + 垂直短线（至少3px上下）
"""
import re, shutil, os

HTML = "/opt/ruipan/static/live-scores-preview-v6.html"
BAK = HTML + ".bak_doji"

def main():
    if not os.path.exists(HTML):
        print(f"❌ 找不到 {HTML}")
        return

    shutil.copy2(HTML, BAK)
    print(f"✅ 备份 → {BAK}")

    with open(HTML, 'r', encoding='utf-8') as f:
        html = f.read()

    # 定位doji渲染块并替换
    old_doji = """    if (isDoji) {
      // 十字线：无变化时画水平横线（开盘=收盘位置）
      const yC = yOf(c.close);
      ctx.strokeStyle=color;ctx.lineWidth=1.5;
      ctx.beginPath();
      ctx.moveTo(x - candleW/2, yC);
      ctx.lineTo(x + candleW/2, yC);
      ctx.stroke();
    } else {"""

    new_doji = """    if (isDoji) {
      // 十字星：水平横线 + 垂直短线（即使h=l也画最小3px竖线形成十字形）
      const yC = yOf(c.close);
      ctx.strokeStyle=color;ctx.lineWidth=1;
      // 垂直部分：至少6px高（上下各3px）
      const minWick = 3;
      const yH = yOf(c.high);
      const yL = yOf(c.low);
      let wickTop = Math.min(yH, yC) - minWick;
      let wickBot = Math.max(yL, yC) + minWick;
      // 不超出chart范围
      wickTop = Math.max(wickTop, padT);
      wickBot = Math.min(wickBot, padT + chartH);
      ctx.beginPath();
      ctx.moveTo(x, wickTop);
      ctx.lineTo(x, wickBot);
      ctx.stroke();
      // 水平横线
      ctx.lineWidth=1.5;
      ctx.beginPath();
      ctx.moveTo(x - candleW/2, yC);
      ctx.lineTo(x + candleW/2, yC);
      ctx.stroke();
    } else {"""

    if old_doji in html:
        html = html.replace(old_doji, new_doji, 1)
        print("✅ doji渲染块已替换为真正十字形")
    else:
        # 尝试宽松匹配
        pattern = r'if \(isDoji\) \{[^}]*// 十字线[^}]*const yC = yOf\(c\.close\);[^}]*ctx\.strokeStyle=color;ctx\.lineWidth=1\.5;[^}]*ctx\.beginPath\(\);[^}]*ctx\.moveTo\(x - candleW/2, yC\);[^}]*ctx\.lineTo\(x \+ candleW/2, yC\);[^}]*ctx\.stroke\(\);[^}]*\} else \{'
        m = re.search(pattern, html, re.DOTALL)
        if m:
            html = html[:m.start()] + new_doji + html[m.end():]
            print("✅ doji渲染块已替换（正则匹配）")
        else:
            print("❌ 找不到doji渲染块，请检查HTML")
            return

    with open(HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print("✅ 写入完成")

if __name__ == "__main__":
    main()
