#!/usr/bin/env python3
"""Diagnose why analysis tab shows no data for today's matches."""
import json, urllib.request, sys, datetime
import psycopg2

TODAY = datetime.date.today().isoformat()
print(f"=== 今天: {TODAY} ===\n")

# 1. Fetch today's matches
try:
    with urllib.request.urlopen(f"http://localhost:8000/api/v1/matches?date={TODAY}", timeout=10) as r:
        raw = r.read().decode()
    print("matches API raw (first 500):", raw[:500])
    d = json.loads(raw)
    # explore structure
    if isinstance(d, dict):
        print("top keys:", list(d.keys()))
        ms = d.get('data') or d.get('matches') or []
        if isinstance(ms, dict):
            print("data is dict, keys:", list(ms.keys())[:10])
            ms = ms.get('data') or ms.get('matches') or list(ms.values())[0] if ms else []
    else:
        ms = d
    print(f"\nmatches count: {len(ms) if isinstance(ms,list) else 'N/A'}")
    if isinstance(ms, list) and ms:
        print("first match keys:", list(ms[0].keys())[:20])
        for m in ms[:5]:
            fid = m.get('fixture_id') or m.get('match_id') or m.get('id')
            print(fid, m.get('home_team'),'vs',m.get('away_team'), m.get('status'))
        first_fid = ms[0].get('fixture_id') or ms[0].get('match_id') or ms[0].get('id')
    else:
        first_fid = None
except Exception as e:
    print("matches API error:", e)
    first_fid = None

# 2. Test analysis API for first match
if first_fid:
    print(f"\n=== analysis for fid={first_fid} ===")
    try:
        with urllib.request.urlopen(f"http://localhost:8000/api/v1/matches/{first_fid}/analysis", timeout=10) as r:
            araw = r.read().decode()
        ad = json.loads(araw)
        print("analysis top keys:", list(ad.keys()) if isinstance(ad,dict) else type(ad))
        print(json.dumps(ad, ensure_ascii=False, indent=2)[:1500])
    except Exception as e:
        print("analysis API error:", e)

# 3. Check analysis_results table structure and counts
print("\n=== analysis_results table ===")
try:
    conn = psycopg2.connect("postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan")
    cur = conn.cursor()
    cur.execute("""SELECT column_name, data_type FROM information_schema.columns WHERE table_name='analysis_results' ORDER BY ordinal_position;""")
    cols = cur.fetchall()
    print("columns:")
    for c in cols: print(" ", c)
    cur.execute("SELECT COUNT(*) FROM analysis_results;")
    print("total rows:", cur.fetchone()[0])
    # find date-like column
    date_cols = [c[0] for c in cols if 'date' in c[0].lower() or 'time' in c[0].lower() or 'at' in c[0].lower()]
    print("date-like cols:", date_cols)
    for dc in date_cols:
        cur.execute(f"SELECT {dc}::date, COUNT(*) FROM analysis_results GROUP BY 1 ORDER BY 1 DESC LIMIT 10;")
        print(f"by {dc}:")
        for row in cur.fetchall(): print(" ", row)
    cur.close(); conn.close()
except Exception as e:
    print("DB error:", e)
