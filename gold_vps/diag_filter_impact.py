#!/usr/bin/env python3
"""诊断盘口解析即时分歧数据是否因脏数据过滤而丢失"""
import subprocess, json

def psql(sql):
    r = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "ruipan", "-t", "-A", "-c", sql],
        capture_output=True, text=True
    )
    return r.stdout.strip()

# 1. 找一场进行中和一场完场的比赛
print("=" * 60)
print("【今日比赛状态】")
rows = psql("""
    SELECT match_id, home_team, away_team, status, home_score, away_score
    FROM matches 
    WHERE match_time >= CURRENT_DATE AND match_time < CURRENT_DATE + interval '1 day'
    ORDER BY CASE WHEN status IN ('live','in_progress','halftime') THEN 0 
                  WHEN status='scheduled' THEN 1 ELSE 2 END
    LIMIT 10
""")
for line in rows.split("\n"):
    if line:
        parts = line.split("|")
        print(f"  {parts[0]} {parts[1]} vs {parts[2]} [{parts[3]}] {parts[4]}-{parts[5]}")

# 2. 对完场比赛，检查live亚盘数据在过滤前后各剩多少
print("\n" + "=" * 60)
print("【完场比赛亚盘live数据 - 过滤前后对比】")
finished_ids = psql("""
    SELECT match_id FROM matches 
    WHERE match_time >= CURRENT_DATE AND match_time < CURRENT_DATE + interval '1 day'
    AND status = 'finished'
    LIMIT 3
""").split("\n")

for mid in finished_ids[:3]:
    if not mid.strip():
        continue
    mid = mid.strip()
    print(f"\n--- 比赛 {mid} ---")
    
    # 不过滤的总数
    all_live = psql(f"""
        SELECT bookmaker, handicap, home_odds, away_odds
        FROM odds_asia WHERE match_id='{mid}' AND odds_type='live'
        ORDER BY bookmaker
    """)
    print(f"  全部live记录 ({len([l for l in all_live.split(chr(10)) if l])} 条):")
    for line in all_live.split("\n"):
        if line:
            print(f"    {line}")
    
    # 过滤后（水位0.5~2.0）
    filtered = psql(f"""
        SELECT bookmaker, handicap, home_odds, away_odds
        FROM odds_asia WHERE match_id='{mid}' AND odds_type='live'
        AND home_odds BETWEEN 0.5 AND 2.0 AND away_odds BETWEEN 0.5 AND 2.0
        ORDER BY bookmaker
    """)
    print(f"  过滤后live记录 ({len([l for l in filtered.split(chr(10)) if l])} 条):")
    for line in filtered.split("\n"):
        if line:
            print(f"    {line}")

# 3. 检查进行中比赛（如果有）
print("\n" + "=" * 60)
print("【进行中比赛亚盘live数据 - 检查水位是否正常】")
live_ids = psql("""
    SELECT match_id FROM matches 
    WHERE match_time >= CURRENT_DATE - interval '1 day' 
    AND match_time < CURRENT_DATE + interval '1 day'
    AND status IN ('live','in_progress','halftime')
    LIMIT 3
""").split("\n")

for mid in live_ids:
    if not mid.strip():
        continue
    mid = mid.strip()
    print(f"\n--- 比赛 {mid} ---")
    
    asia = psql(f"""
        SELECT bookmaker, odds_type, handicap, home_odds, away_odds
        FROM odds_asia WHERE match_id='{mid}'
        ORDER BY bookmaker, odds_type
    """)
    for line in asia.split("\n"):
        if line:
            parts = line.split("|")
            ho = float(parts[3]) if parts[3] else 0
            ao = float(parts[4]) if parts[4] else 0
            flag = ""
            if parts[1] == 'live' and (ho < 0.5 or ho > 2.0 or ao < 0.5 or ao > 2.0):
                flag = " ⚠️ 被过滤"
            print(f"    {line}{flag}")

# 4. 检查欧赔过滤是否太严
print("\n" + "=" * 60)
print("【欧赔过滤检查 - LEAST(home_win,draw,away_win) > 3.0 的记录】")
euro_live = psql("""
    SELECT oe.match_id, oe.bookmaker, oe.home_win, oe.draw, oe.away_win
    FROM odds_euro oe
    JOIN matches m ON oe.match_id = m.match_id
    WHERE m.match_time >= CURRENT_DATE AND m.match_time < CURRENT_DATE + interval '1 day'
    AND oe.odds_type = 'live'
    AND LEAST(oe.home_win, oe.draw, oe.away_win) > 3.0
    LIMIT 20
""")
if euro_live:
    print("  以下live欧赔最低赔率>3.0会被过滤:")
    for line in euro_live.split("\n"):
        if line:
            print(f"    {line}")
else:
    print("  无被过滤的live欧赔记录")

# 5. 检查亚盘水位>2.0的记录（可能是正常高水）
print("\n【亚盘live水位>2.0的记录 - 可能误杀正常高水】")
asia_high = psql("""
    SELECT oa.match_id, oa.bookmaker, oa.handicap, oa.home_odds, oa.away_odds
    FROM odds_asia oa
    JOIN matches m ON oa.match_id = m.match_id
    WHERE m.match_time >= CURRENT_DATE AND m.match_time < CURRENT_DATE + interval '1 day'
    AND oa.odds_type = 'live'
    AND (oa.home_odds > 2.0 OR oa.away_odds > 2.0)
    LIMIT 20
""")
if asia_high:
    for line in asia_high.split("\n"):
        if line:
            print(f"    {line}")
else:
    print("  无水位>2.0的live记录")
