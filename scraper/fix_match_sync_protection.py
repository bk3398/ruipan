#!/usr/bin/env python3
"""Fix match_sync: don't overwrite finished/cancelled with scheduled from bfdata."""
APP = "/opt/ruipan/scraper/match_sync.py"
with open(APP, "r", encoding="utf-8") as f:
    code = f.read()

OLD = """                if existing:
                    if (existing['status'] != status or
                        existing['home_score'] != m['home_score'] or
                        existing['away_score'] != m['away_score']):
                        await conn.execute(
                            \"\"\"UPDATE matches SET league=$2, home_team=$3, away_team=$4,
                               match_time=$5, status=$6, home_score=$7, away_score=$8,
                               home_ht_score=$9, away_ht_score=$10,
                               season=COALESCE($11, season)
                               WHERE match_id=$1\"\"\",
                            sid, league, home, away, match_time, status,
                            m['home_score'], m['away_score'],
                            m.get('home_ht_score'), m.get('away_ht_score'),
                            season
                        )
                        update_count += 1"""

NEW = """                if existing:
                    # Don't overwrite finished/cancelled back to scheduled/live
                    # bfdata may still return old matches with status_code=-1
                    if existing['status'] in ('finished', 'cancelled') and status in ('scheduled', 'not_started'):
                        continue
                    if (existing['status'] != status or
                        existing['home_score'] != m['home_score'] or
                        existing['away_score'] != m['away_score']):
                        await conn.execute(
                            \"\"\"UPDATE matches SET league=$2, home_team=$3, away_team=$4,
                               match_time=$5, status=$6, home_score=$7, away_score=$8,
                               home_ht_score=$9, away_ht_score=$10,
                               season=COALESCE($11, season)
                               WHERE match_id=$1\"\"\",
                            sid, league, home, away, match_time, status,
                            m['home_score'], m['away_score'],
                            m.get('home_ht_score'), m.get('away_ht_score'),
                            season
                        )
                        update_count += 1"""

if OLD not in code:
    if "Don't overwrite finished" in code:
        print("Already patched")
    else:
        print("ERROR: anchor not found in match_sync.py")
        import sys; sys.exit(1)
else:
    code = code.replace(OLD, NEW, 1)
    with open(APP, "w", encoding="utf-8") as f:
        f.write(code)
    print("Patched match_sync.py: finished/cancelled protected from overwrite")

import py_compile
py_compile.compile(APP, doraise=True)
print("Syntax OK")
