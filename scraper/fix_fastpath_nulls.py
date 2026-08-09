#!/usr/bin/env python3
"""Fix fast-path: replace null league_table numeric fields with 0."""
APP = "/opt/ruipan/app.py"
with open(APP, "r", encoding="utf-8") as f:
    code = f.read()

# The fast-path builds league_table rows with t.get("played") etc which can be None.
# Fix: after building lt, ensure all numeric fields default to 0.
OLD = """        for tn in (home_team, away_team):
            ov = (ts.get(tn) or {}).get("overall")
            if not ov:
                continue
            for r in lt:
                if r["team"] == tn:
                    for k in ("played", "won", "drawn", "lost", "gf", "ga", "gd", "points"):
                        if r.get(k) is None and k in ov:
                            r[k] = ov[k]
                    break
        lt.sort(key=lambda r: (r.get("points") or 0, r.get("gd") or 0,
                                r.get("gf") or 0), reverse=True)"""

NEW = """        # Ensure no null numeric fields (frontend does arithmetic on them)
        for r in lt:
            for k in ("played", "won", "drawn", "lost", "gf", "ga", "gd", "points"):
                if r.get(k) is None:
                    r[k] = 0
        # Override match teams with real team_stats
        for tn in (home_team, away_team):
            ov = (ts.get(tn) or {}).get("overall")
            if not ov:
                continue
            for r in lt:
                if r["team"] == tn:
                    for k in ("played", "won", "drawn", "lost", "gf", "ga", "gd", "points"):
                        if k in ov:
                            r[k] = ov[k]
                    break
        lt.sort(key=lambda r: (r.get("points") or 0, r.get("gd") or 0,
                                r.get("gf") or 0), reverse=True)"""

if OLD not in code:
    # Try alternate: maybe the null default line already exists
    if "Ensure no null numeric fields" in code:
        print("Already patched")
    else:
        print("ERROR: anchor not found")
        import sys; sys.exit(1)
else:
    code = code.replace(OLD, NEW, 1)
    with open(APP, "w", encoding="utf-8") as f:
        f.write(code)
    print("Patched: null numeric fields now default to 0")

import py_compile
py_compile.compile(APP, doraise=True)
print("Syntax OK")
