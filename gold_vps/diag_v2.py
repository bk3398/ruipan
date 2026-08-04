#!/usr/bin/env python3
"""Diagnose analysis tab no data - v2: explore all API routes + all relevant tables."""
import json, urllib.request, sys, datetime
import psycopg2

TODAY = datetime.date.today().isoformat()
print(f"=== 今天: {TODAY} ===\n")

def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "diag/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300] if e.fp else ""
    except Exception as e:
        return None, str(e)

# 1. Check API root and common endpoints
print("=== API 端点探测 ===")
endpoints = [
    "http://localhost:8000/",
    "http://localhost:8000/api",
    "http://localhost:8000/api/v1",
    "http://localhost:8000/docs",
    "http://localhost:8000/openapi.json",
    f"http://localhost:8000/api/v1/matches?date={TODAY}",
    f"http://localhost:8000/api/matches?date={TODAY}",
    f"http://localhost:8000/matches?date={TODAY}",
]
for ep in endpoints:
    code, body = fetch(ep)
    preview = body[:120].replace("\n"," ") if body else ""
    print(f"  [{code}] {ep}")
    if preview:
        print(f"        -> {preview}")

# 2. Try to get openapi routes
print("\n=== OpenAPI 路由列表 ===")
code, body = fetch("http://localhost:8000/openapi.json")
if code == 200:
    try:
        spec = json.loads(body)
        paths = list(spec.get("paths", {}).keys())
        for p in sorted(paths):
            methods = list(spec["paths"][p].keys())
            print(f"  {','.join(m.upper() for m in methods):20s} {p}")
    except Exception as e:
        print("  parse error:", e)
else:
    print("  openapi.json not available, code=", code)

# 3. Database: list all tables and row counts
print("\n=== 数据库所有表 ===")
try:
    conn = psycopg2.connect("postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan")
    cur = conn.cursor()
    cur.execute("""SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;""")
    tables = [r[0] for r in cur.fetchall()]
    print("  tables:", tables)
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t};")
        cnt = cur.fetchone()[0]
        print(f"    {t}: {cnt} rows")
        # show columns
        cur.execute(f"""SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{t}' ORDER BY ordinal_position;""")
        cols = cur.fetchall()
        print(f"      cols: {[c[0] for c in cols]}")

    # 4. Check matches table for today
    print("\n=== matches 表今日数据 ===")
    cur.execute("""SELECT column_name, data_type FROM information_schema.columns WHERE table_name='matches' ORDER BY ordinal_position;""")
    match_cols = [r[0] for r in cur.fetchall()]
    print("  match cols:", match_cols)
    # find date column
    date_col = None
    for c in match_cols:
        if 'date' in c.lower() or 'time' in c.lower() or 'kickoff' in c.lower() or 'start' in c.lower():
            date_col = c
            break
    if date_col:
        cur.execute(f"SELECT {date_col} FROM matches ORDER BY {date_col} DESC LIMIT 5;")
        print(f"  latest {date_col} values:", [r[0] for r in cur.fetchall()])
        cur.execute(f"SELECT COUNT(*) FROM matches WHERE {date_col}::date = %s;", (TODAY,))
        print(f"  today matches count:", cur.fetchone()[0])
        cur.execute(f"SELECT COUNT(*) FROM matches WHERE {date_col}::date >= %s;", (TODAY,))
        print(f"  matches from today onward:", cur.fetchone()[0])
    else:
        print("  no date column found, trying all columns sample")
        cur.execute("SELECT * FROM matches LIMIT 1;")
        print("  sample row:", cur.fetchone())

    # 5. Check odds_euro and odds_asia for today
    print("\n=== odds 表今日数据 ===")
    for ot in ['odds_euro', 'odds_asia']:
        cur.execute(f"""SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{ot}' ORDER BY ordinal_position;""")
        ocols = [r[0] for r in cur.fetchall()]
        # find match_id/fixture_id column
        mid_col = next((c for c in ocols if 'match' in c[0].lower() or 'fixture' in c[0].lower()), None)
        print(f"  {ot} cols: {ocols}, match_id col={mid_col}")
        cur.execute(f"SELECT COUNT(*) FROM {ot};")
        print(f"  {ot} total rows:", cur.fetchone()[0])

    cur.close(); conn.close()
except Exception as e:
    print("DB error:", e)
    import traceback; traceback.print_exc()
