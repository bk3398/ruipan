#!/usr/bin/env python3
"""
白名单扩展补丁 — 2026-08-09 v3
基于 bfdata 实际被排除联赛精确补充。
用法: python3 patch_league_whitelist.py
"""
import re

SCRAPER_PATH = '/opt/ruipan/scraper/scraper.py'

# 基于诊断结果精确补充（名称来自 bfdata 实际数据）
# 注意: 不含球会友谊(被"友谊"关键词排除)、女足/青年/预备队(已有排除关键词)
ADD_LEAGUES = {
    # ═══ T1 顶级联赛/重要杯赛 ═══
    '英联杯': 1,           # EFL Cup 29场
    '中北美杯': 1,          # CONCACAF Cup 7场
    '乌克超': 1,
    '斯伐超': 1,
    '克亚甲': 1,           # Croatia 1.HNL (bfdata用"克亚甲")
    '乌拉甲秋': 1,         # Uruguayan Primera autumn variant
    '波兰超': 1,
    '玻利甲': 1,
    '厄瓜甲': 1,
    '哥斯甲春': 1,
    '哈萨克超': 1,         # bfdata用"哈萨克超"
    '白俄超': 1,
    '土超': 1,             # Turkish Super Lig
    '以超': 1,
    '希腊超': 1,
    '塞尔超': 1,
    '黑山超': 1,
    '立陶甲': 1,
    '拉脱超': 1,
    '爱沙超': 1,
    '格鲁甲': 1,
    '匈甲': 1,             # Hungarian NB1 (顶级)

    # ═══ T2 次级联赛/杯赛/俱乐部友谊赛 ═══
    '球会友谊': 2,         # 俱乐部友谊赛 86场(有盘口价值)
    '球會友誼': 2,         # 繁体
    '俱乐部友谊': 2,
    '球會友誼賽': 2,
    '英议联': 2,           # National League
    '英议南': 2,
    '英议北': 2,
    '捷丁': 2,
    '阿乙曼特秋': 2,
    '威冠北': 2,
    '捷丙': 2,
    '葡乙': 2,
    '土甲': 2,             # Turkish 1.Lig (second tier)
    '巴丁': 2,
    '巴丙': 2,
    '日地区联': 2,
    '芬K联': 2,
    '马维超': 2,
    '德地区南': 2,
    '德地区西': 2,
    '爱沙乙': 2,
    '澳威北超': 2,
    '澳南甲': 2,
    '澳南乙': 2,
    '澳西甲': 2,
    '澳昆甲3': 2,
    '新西中联': 2,
    '新西北联': 2,
    '新西南联': 2,
    '加尔联': 2,
    '捷乙': 2,
    '波兰甲': 2,
    '波兰乙': 2,
    '斯伐甲': 2,
    '乌克甲': 2,
    '乌克杯': 2,
    '希腊甲': 2,
    '塞尔甲': 2,
    '黑山甲': 2,
    '立陶乙': 2,
    '拉脱甲': 2,
    '格鲁乙': 2,
    '白俄甲': 2,
    '白俄乙': 2,
    '哈萨克甲': 2,
    '土乙': 2,
    '土杯': 2,
    '希腊杯': 2,
    '波兰杯': 2,
    '捷克杯': 2,
    '克亚乙': 2,
    '玻利乙': 2,
    '厄瓜乙': 2,
    '哥斯乙': 2,
    '乌拉乙秋': 2,
    '德地区北': 2,
    '德地区东': 2,
    '德地区巴': 2,
    '以甲': 2,
    '以乙': 2,
    '以色列杯': 2,
    '阿尔巴超': 1,
    '阿尔巴甲': 2,
    '科索沃超': 1,
    '北马其超': 1,
    '冰联杯': 2,
    '冰超': 1,            # 可能已有
    '芬甲': 2,            # 可能已有
}


def patch():
    with open(SCRAPER_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    existing = set(re.findall(r"'([^']+)':\s*[12],", content))
    to_add = {k: v for k, v in ADD_LEAGUES.items() if k not in existing}

    if not to_add:
        print("所有联赛已在白名单中，无需补丁。")
        return

    t1 = {k: v for k, v in to_add.items() if v == 1}
    t2 = {k: v for k, v in to_add.items() if v == 2}
    print(f"新增 T1 ({len(t1)}): {list(t1.keys())}")
    print(f"新增 T2 ({len(t2)}): {list(t2.keys())}")

    t1_str = '\n'.join(f"    '{k}': {v}," for k, v in sorted(t1.items()))
    t2_str = '\n'.join(f"    '{k}': {v}," for k, v in sorted(t2.items()))

    # 在 "# T2" 前插入T1
    t2_marker = "    # T2"
    if t2_marker in content and t1_str:
        content = content.replace(t2_marker, t1_str + '\n' + t2_marker, 1)

    # 找 LEAGUE_TIER 闭合括号，在其前插入T2
    tier_start = content.find('LEAGUE_TIER = {')
    brace_count = 0
    i = tier_start + len('LEAGUE_TIER = ')
    while i < len(content):
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                break
        i += 1

    if t2_str:
        content = content[:i] + t2_str + '\n' + content[i:]

    with open(SCRAPER_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    # 验证
    with open(SCRAPER_PATH, 'r', encoding='utf-8') as f:
        verify = f.read()
    now_existing = set(re.findall(r"'([^']+)':\s*[12],", verify))
    still_missing = [k for k in to_add if k not in now_existing]
    if still_missing:
        print(f"\n⚠️ 仍有 {len(still_missing)} 个未写入: {still_missing}")
    else:
        print(f"\n✅ 补丁成功！新增 {len(to_add)} 个联赛到白名单")
        print(f"   文件: {SCRAPER_PATH}")


if __name__ == '__main__':
    patch()
