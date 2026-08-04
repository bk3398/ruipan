#!/usr/bin/env python3
"""
Fix: 胜率大量缺失
方案: 多层次回退查找
  Level 1: 精确匹配 hdp×water×divg, 样本>=3
  Level 2: 聚合 hdp×water (忽略divg), 样本>=5
  Level 3: 聚合 hdp only (忽略water+divg), 样本>=5
  都不满足返回null
同时将精确匹配阈值从5降到3
"""
import shutil, os, sys
from datetime import datetime

html_path = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

print(f"File size before: {len(content.encode('utf-8'))} bytes")

# The old lookupWR function (L2048-L2071)
old_func = """function lookupWR(phase, hdp, water, divg){
  const lookup = BACKTEST_WINRATE_LOOKUP[phase];
  if(!lookup) return null;
  const hn = hdpNameV3(hdp);
  const wb = waterBinV3(water);
  const db = divgBinV3(divg);
  const key = hn + '×' + wb + '×' + db;
  const entry = lookup[key];
  if(!entry) return null;
  // 仅返回样本量>=5的数据
  if(entry.sample < 5) return null;
  // 转换为页面格式 {wr, n}
  return {
    wr: entry.win_rate_upper * 100,
    n: entry.sample,
    w: entry.upper_win,
    l: entry.upper_lose,
    p: entry.upper_push,
    avg_profit: entry.avg_profit,
    // 下盘数据
    wr_lower: entry.win_rate_lower * 100,
    avg_profit_lower: entry.avg_profit_lower,
  };
}"""

new_func = """function lookupWR(phase, hdp, water, divg){
  const lookup = BACKTEST_WINRATE_LOOKUP[phase];
  if(!lookup) return null;
  const hn = hdpNameV3(hdp);
  const wb = waterBinV3(water);
  const db = divgBinV3(divg);

  // 格式化entry为页面格式
  const fmtEntry = (e) => ({
    wr: e.win_rate_upper * 100,
    n: e.sample,
    w: e.upper_win,
    l: e.upper_lose,
    p: e.upper_push,
    avg_profit: e.avg_profit,
    wr_lower: e.win_rate_lower * 100,
    avg_profit_lower: e.avg_profit_lower,
  });

  // 聚合多条entry
  const aggEntries = (entries) => {
    let s=0,w=0,l=0,p=0,ap=0,apl=0,wrl=0;
    entries.forEach(e => {
      s += e.sample;
      w += e.upper_win || 0;
      l += e.upper_lose || 0;
      p += e.upper_push || 0;
      ap += (e.avg_profit||0) * e.sample;
      apl += (e.avg_profit_lower||0) * e.sample;
      wrl += (e.win_rate_lower||0) * e.sample;
    });
    if(s === 0) return null;
    return {
      win_rate_upper: w / s,
      win_rate_lower: wrl / s,
      sample: s,
      upper_win: w, upper_lose: l, upper_push: p,
      avg_profit: ap / s,
      avg_profit_lower: apl / s,
    };
  };

  // Level 1: 精确匹配 hdp×water×divg, 样本>=3
  const key = hn + '×' + wb + '×' + db;
  const entry = lookup[key];
  if(entry && entry.sample >= 3) return fmtEntry(entry);

  // Level 2: 聚合 hdp×water (忽略divg), 样本>=5
  const l2Entries = [];
  for(const k in lookup) {
    const parts = k.split('×');
    if(parts.length === 3 && parts[0] === hn && parts[1] === wb) {
      l2Entries.push(lookup[k]);
    }
  }
  if(l2Entries.length > 0) {
    const agg2 = aggEntries(l2Entries);
    if(agg2 && agg2.sample >= 5) return fmtEntry(agg2);
  }

  // Level 3: 聚合 hdp only (忽略water+divg), 样本>=5
  const l3Entries = [];
  for(const k in lookup) {
    const parts = k.split('×');
    if(parts.length === 3 && parts[0] === hn) {
      l3Entries.push(lookup[k]);
    }
  }
  if(l3Entries.length > 0) {
    const agg3 = aggEntries(l3Entries);
    if(agg3 && agg3.sample >= 5) return fmtEntry(agg3);
  }

  return null;
}"""

if old_func in content:
    content = content.replace(old_func, new_func)
    print("✅ Replaced lookupWR with multi-level fallback version")
else:
    print("❌ Could not find old lookupWR function")
    # Try to find it with looser matching
    import re
    pattern = r'function lookupWR\(phase, hdp, water, divg\)\{.*?\n\}'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        print(f"Found via regex at position {match.start()}-{match.end()}")
        print(f"Matched text: {match.group()[:200]}...")
        content = content[:match.start()] + new_func + content[match.end():]
        print("✅ Replaced via regex")
    else:
        print("Could not find lookupWR at all")
        sys.exit(1)

# Backup and write
bak = f"{html_path}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy2(html_path, bak)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

new_size = len(content.encode('utf-8'))
print(f"Backup: {bak}")
print(f"File size: {os.path.getsize(bak)} → {new_size} bytes (diff: {new_size - os.path.getsize(bak)})")

# Verify
with open(html_path, 'r') as f:
    verify = f.read()
if 'Level 1: 精确匹配' in verify and 'Level 2: 聚合' in verify and 'Level 3: 聚合' in verify:
    print("✅ Verification passed: all 3 levels present")
else:
    print("⚠️ Verification issue")

print("\nDone! Hard refresh: Ctrl+Shift+R")
