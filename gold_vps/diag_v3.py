#!/usr/bin/env python3
"""Diagnose analysis tab v3: test actual API paths + DB odds for today's matches."""
import json, urllib.request, datetime
import psycopg2

TODAY = datetime.date.today().isoformat()
print(f"=== 今天: {TODAY} ===\n")

def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "diag/3.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode()[:500]
        except: pass
        return e.code, body
    except Exception as e:
        return None, str(e)

# 1. Get today's matches via actual API
print("=== /api/v1/matches/today ===")
code, body = fetch("http://localhost:8000/api/v1/matches/today")
print(f"  status: {code}, len: {len(body)}")
matches = []
if code == 200:
    d = json.loads(body)
    if isinstance(d, dict):
        print("  top keys:", list(d.keys()))
        # find the list
        for k in ['data','matches','items','results']:
            if k in d and isinstance(d[k], list):
                matches = d[k]
                break
        if not matches:
            # maybe first list value
            for v in d.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    matches = v
                    break
    elif isinstance(d, list):
        matches = d
    print(f"  matches count: {len(matches)}")
    if matches:
        print("  first match keys:", list(matches[0].keys()))
        for m in matches[:8]:
            mid = m.get('match_id') or m.get('fixture_id') or m.get('id')
            ht = m.get('home_team','?')
            at = m.get('away_team','?')
            st = m.get('status','?')
            mt = m.get('match_time','?')
            print(f"    id={mid}  {ht} vs {at}  status={st} time={mt}")
else:
    print("  body:", body[:300])

# 2. For first 3 matches, test analysis + odds-timeline
if matches:
    for m in matches[:3]:
        mid = str(m.get('match_id') or m.get('fixture_id') or m.get('id'))
        ht = m.get('home_team','?')
        at = m.get('away_team','?')
        print(f"\n--- {mid}: {ht} vs {at} ---")
        
        # analysis
        code, body = fetch(f"http://localhost:8000/api/v1/matches/{mid}/analysis")
        print(f"  analysis [{code}]:")
        if code == 200:
            ad = json.loads(body)
            if isinstance(ad, dict):
                print(f"    keys: {list(ad.keys())}")
                bk = ad.get('bookmakers', {})
                print(f"    bookmakers count: {len(bk)}")
                if bk:
                    for bkname, bkdata in list(bk.items())[:3]:
                        phases = bkdata.get('phases', {}) if isinstance(bkdata, dict) else {}
                        print(f"      {bkname}: phases={list(phases.keys())}")
                else:
                    print(f"    raw (first 500): {body[:500]}")
            else:
                print(f"    type: {type(ad)}, val: {str(ad)[:300]}")
        else:
            print(f"    error: {body[:300]}")
        
        # odds-timeline
        code2, body2 = fetch(f"http://localhost:8000/api/v1/matches/{mid}/odds-timeline")
        print(f"  odds-timeline [{code2}]:")
        if code2 == 200:
            od = json.loads(body2)
            if isinstance(od, dict):
                print(f"    keys: {list(od.keys())}")
                for k in ['euro','asia','euro_odds','asia_odds','timeline']:
                    if k in od:
                        v = od[k]
                        if isinstance(v, list):
                            print(f"    {k}: {len(v)} records")
                            if v: print(f"      sample: {json.dumps(v[0], ensure_ascii=False)[:200]}")
                        elif isinstance(v, dict):
                            print(f"    {k}: dict keys={list(v.keys())[:10]}")
                        else:
                            print(f"    {k}: {str(v)[:100]}")
            elif isinstance(od, list):
                print(f"    list of {len(od)} items")
                if od: print(f"      sample: {json.dumps(od[0], ensure_ascii=False)[:200]}")
        else:
            print(f"    error: {body2[:300]}")

# 3. Check DB directly for today's match odds
print("\n=== DB: 今日比赛赔率数据 ===")
try:
    conn = psycopg2.connect("postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan")
    cur = conn.cursor()
    # Get today's match_ids
    cur.execute("SELECT match_id, home_team, away_team, status, match_time FROM matches WHERE match_time::date = %s ORDER BY match_time LIMIT 10;", (TODAY,))
    today_matches = cur.fetchall()
    print(f"  今日比赛 {len(today_matches)} 场（前10）:")
    for mid, ht, at, st, mt in today_matches:
        # count odds
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT bookmaker), MIN(recorded_at), MAX(recorded_at) FROM odds_euro WHERE match_id = %s;", (mid,))
        ec = cur.fetchone()
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT bookmaker), MIN(recorded_at), MAX(recorded_at) FROM odds_asia WHERE match_id = %s;", (mid,))
        ac = cur.fetchone()
        print(f"    {mid}: {ht} vs {at} [{st}] {mt}")
        print(f"      euro: {ec[0]} rows, {ec[1]} bookmakers, {ec[2]} ~ {ec[3]}")
        print(f"      asia: {ac[0]} rows, {ac[1]} bookmakers, {ac[2]} ~ {ac[3]}")
    
    # Check sample odds for first match
    if today_matches:
        first_mid = today_matches[0][0]
        print(f"\n  样本: odds_euro WHERE match_id='{first_mid}'")
        cur.execute("SELECT bookmaker, odds_type, home_win, draw, away_win, recorded_at FROM odds_euro WHERE match_id = %s ORDER BY recorded_at LIMIT 5;", (first_mid,))
        for row in cur.fetchall():
            print(f"    {row}")
        print(f"  样本: odds_asia WHERE match_id='{first_mid}'")
        cur.execute("SELECT bookmaker, odds_type, handicap, home_odds, away_odds, recorded_at FROM odds_asia WHERE match_id = %s ORDER BY recorded_at LIMIT 5;", (first_mid,))
        for row in cur.fetchall():
            print(f"    {row}")
        
        # Check what odds_types exist
        cur.execute("SELECT DISTINCT odds_type FROM odds_euro WHERE match_id = %s;", (first_mid,))
        print(f"  odds_euro types: {[r[0] for r in cur.fetchall()]}")
        cur.execute("SELECT DISTINCT odds_type FROM odds_asia WHERE match_id = %s;", (first_mid,))
        print(f"  odds_asia types: {[r[0] for r in cur.fetchall()]}")
    
    cur.close(); conn.close()
except Exception as e:
    print("DB error:", e)
    import traceback; traceback.print_exc()
