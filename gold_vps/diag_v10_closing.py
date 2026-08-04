#!/usr/bin/env python3
"""诊断封盘脏数据：查看完场比赛最后几条live赔率记录"""
import urllib.request, json, psycopg2

BASE = "http://127.0.0.1:8000"

def fetch(path):
    with urllib.request.urlopen(BASE + path, timeout=8) as r:
        return json.loads(r.read())

# 找咸史泰斯 vs 天狼星
matches = fetch("/api/v1/matches/today").get("data", [])
target = None
for m in matches:
    home = m.get("home_team", "")
    away = m.get("away_team", "")
    if "咸史" in home or "天狼" in away or "史泰斯" in home:
        target = m
        break

if not target:
    # 找第一个finished且有asia数据的
    for m in matches:
        if m.get("status") == "finished":
            target = m
            break

fid = target.get("fixture_id") or target.get("match_id")
print(f"比赛: {fid} {target.get('home_team')} vs {target.get('away_team')}")
print(f"状态: {target.get('status')}, 比分: {target.get('home_score')}-{target.get('away_score')}")
print(f"比赛时间: {target.get('match_time')}")

# 获取odds-timeline
tl = fetch(f"/api/v1/matches/{fid}/odds-timeline")
asia = tl.get("data", {}).get("asian", {})
euro = tl.get("data", {}).get("euro", {})

print(f"\n亚盘公司数: {len(asia)}")
print(f"欧赔公司数: {len(euro)}")

# 看每家公司的initial和live数据
for bk_name in list(asia.keys())[:3]:
    bk = asia[bk_name]
    print(f"\n{'='*50}")
    print(f"博彩公司: {bk_name}")
    print(f"  phases: {list(bk.keys())}")
    
    ini = bk.get("initial", {})
    liv = bk.get("live", {})
    print(f"  initial: handicap={ini.get('handicap')}, upper={ini.get('upper')}, lower={ini.get('lower')}")
    print(f"  live:    handicap={liv.get('handicap')}, upper={liv.get('upper')}, lower={liv.get('lower')}")
    
    # 检查live数据是否异常
    u = liv.get("upper")
    l = liv.get("lower")
    h = liv.get("handicap")
    if u is not None and (u < 0.3 or u > 5):
        print(f"  ⚠️ live upper水位异常: {u}")
    if l is not None and (l < 0.3 or l > 5):
        print(f"  ⚠️ live lower水位异常: {l}")

# 直接查DB：看这场比赛最后几条odds_asia记录
print(f"\n{'='*50}")
print("【DB原始记录 - 最后10条亚盘】")
import psycopg2
conn = psycopg2.connect("postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan")
cur = conn.cursor()

# 先找match_id
cur.execute("SELECT match_id FROM matches WHERE id = %s OR match_id = %s", (str(fid), str(fid)))
row = cur.fetchone()
mid = row[0] if row else str(fid)
print(f"DB match_id: {mid}")

cur.execute("""
    SELECT bookmaker, handicap, home_odds, away_odds, odds_type, recorded_at 
    FROM odds_asia 
    WHERE match_id = %s 
    ORDER BY recorded_at DESC 
    LIMIT 15
""", (mid,))
rows = cur.fetchall()
print(f"最后15条亚盘记录:")
for r in rows:
    print(f"  {r[5]} | {r[0]:15s} | hcp={r[1]:6} | home={r[2]:8} | away={r[3]:8} | {r[4]}")

# 看initial记录
print(f"\n【初盘记录】")
cur.execute("""
    SELECT bookmaker, handicap, home_odds, away_odds, odds_type, recorded_at 
    FROM odds_asia 
    WHERE match_id = %s AND odds_type = 'initial'
    ORDER BY recorded_at ASC
    LIMIT 5
""", (mid,))
for r in cur.fetchall():
    print(f"  {r[5]} | {r[0]:15s} | hcp={r[1]:6} | home={r[2]:8} | away={r[3]:8} | {r[4]}")

# 统计live记录中异常数据比例
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE home_odds < 0.3 OR home_odds > 5 OR away_odds < 0.3 OR away_odds > 5) as abnormal,
        COUNT(*) FILTER (WHERE home_odds >= 0.3 AND home_odds <= 5 AND away_odds >= 0.3 AND away_odds <= 5) as valid
    FROM odds_asia 
    WHERE match_id = %s AND odds_type = 'live'
""", (mid,))
r = cur.fetchone()
print(f"\nLive数据统计: 总{r[0]}条, 异常{r[1]}条, 有效{r[2]}条")

# 取最后一条有效live数据（按bookmaker分组）
print(f"\n【每家公司最后一条有效live数据】")
cur.execute("""
    SELECT DISTINCT ON (bookmaker) 
        bookmaker, handicap, home_odds, away_odds, recorded_at
    FROM odds_asia
    WHERE match_id = %s AND odds_type = 'live'
        AND home_odds >= 0.3 AND home_odds <= 5
        AND away_odds >= 0.3 AND away_odds <= 5
    ORDER BY bookmaker, recorded_at DESC
""", (mid,))
for r in cur.fetchall():
    print(f"  {r[4]} | {r[0]:15s} | hcp={r[1]:6} | home={r[2]:8} | away={r[3]:8}")

cur.close()
conn.close()
