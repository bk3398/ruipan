#!/usr/bin/env python3
"""诊断封盘脏数据 - 用psql命令行，不依赖psycopg2"""
import urllib.request, json, subprocess

BASE = "http://127.0.0.1:8000"

def fetch(path):
    with urllib.request.urlopen(BASE + path, timeout=8) as r:
        return json.loads(r.read())

def psql(sql):
    cmd = ["sudo", "-u", "postgres", "psql", "-d", "ruipan", "-t", "-A", "-F", "|", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        print(f"  SQL Error: {r.stderr.strip()}")
        return []
    return [line for line in r.stdout.strip().split('\n') if line]

# 获取今日比赛
matches = fetch("/api/v1/matches/today").get("data", [])
finished = [m for m in matches if m.get("status") == "finished"]
print(f"今日完场: {len(finished)} 场")

# 找有亚盘数据的完场比赛
target = None
for m in finished:
    fid = m.get("fixture_id") or m.get("match_id")
    try:
        tl = fetch(f"/api/v1/matches/{fid}/odds-timeline")
        asia = tl.get("data", {}).get("asian", {})
        if asia:
            target = m
            break
    except:
        continue

if not target:
    print("没找到有亚盘数据的完场比赛")
    exit()

fid = target.get("fixture_id") or target.get("match_id")
print(f"\n比赛: {fid} {target.get('home_team')} vs {target.get('away_team')}")
print(f"比分: {target.get('home_score')}-{target.get('away_score')}")

# 查DB match_id
rows = psql(f"SELECT match_id FROM matches WHERE id = '{fid}' OR match_id = '{fid}' LIMIT 1;")
mid = rows[0] if rows else str(fid)
print(f"DB match_id: {mid}")

# 最后15条亚盘
print(f"\n【最后15条亚盘记录】")
rows = psql(f"""
    SELECT bookmaker, handicap, home_odds, away_odds, odds_type, recorded_at 
    FROM odds_asia 
    WHERE match_id = '{mid}' 
    ORDER BY recorded_at DESC 
    LIMIT 15;
""")
for r in rows:
    print(f"  {r}")

# 异常数据统计
print(f"\n【Live数据质量统计】")
rows = psql(f"""
    SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE home_odds < 0.3 OR home_odds > 5 OR away_odds < 0.3 OR away_odds > 5) as abnormal,
        COUNT(*) FILTER (WHERE home_odds >= 0.3 AND home_odds <= 5 AND away_odds >= 0.3 AND away_odds <= 5) as valid
    FROM odds_asia 
    WHERE match_id = '{mid}' AND odds_type = 'live';
""")
if rows:
    parts = rows[0].split('|')
    print(f"  总{parts[0]}条, 异常{parts[1]}条, 有效{parts[2]}条")

# 每家公司最后一条有效live
print(f"\n【每家公司最后一条有效live】")
rows = psql(f"""
    SELECT DISTINCT ON (bookmaker) 
        bookmaker, handicap, home_odds, away_odds, recorded_at
    FROM odds_asia
    WHERE match_id = '{mid}' AND odds_type = 'live'
        AND home_odds >= 0.3 AND home_odds <= 5
        AND away_odds >= 0.3 AND away_odds <= 5
    ORDER BY bookmaker, recorded_at DESC;
""")
for r in rows:
    print(f"  {r}")

# API返回的live数据
print(f"\n【API返回的live数据】")
tl = fetch(f"/api/v1/matches/{fid}/odds-timeline")
asia = tl.get("data", {}).get("asian", {})
for bk_name in list(asia.keys())[:5]:
    bk = asia[bk_name]
    liv = bk.get("live", {})
    ini = bk.get("initial", {})
    u = liv.get("upper")
    l = liv.get("lower")
    h = liv.get("handicap")
    flag = " ⚠️异常" if (u and (u < 0.3 or u > 5)) or (l and (l < 0.3 or l > 5)) else ""
    print(f"  {bk_name}: ini(hcp={ini.get('handicap')},u={ini.get('upper')},l={ini.get('lower')}) → liv(hcp={h},u={u},l={l}){flag}")

# 欧赔也看一下
print(f"\n【API返回的欧赔live数据】")
euro = tl.get("data", {}).get("euro", {})
for bk_name in list(euro.keys())[:5]:
    bk = euro[bk_name]
    liv = bk.get("live", {})
    ini = bk.get("initial", {})
    h = liv.get("h")
    d = liv.get("d")
    a = liv.get("a")
    flag = " ⚠️异常" if (h and (h < 1 or h > 30)) or (a and (a < 1 or a > 30)) else ""
    print(f"  {bk_name}: ini({ini.get('h')},{ini.get('d')},{ini.get('a')}) → liv({h},{d},{a}){flag}")
