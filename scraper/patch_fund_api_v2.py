#!/usr/bin/env python3
"""Insert fast-path block into app.py fundamental endpoint.
If team_fundamentals JSONB exists, build response from it (milliseconds).
Otherwise fall through to existing DB-query logic unchanged."""
import re

APP = "/opt/ruipan/app.py"
with open(APP, "r", encoding="utf-8") as f:
    code = f.read()

# Insertion anchor: the line after match_info dict closes, before "# === 1. H2H"
ANCHOR = '    # === 1. H2H'
if ANCHOR not in code:
    raise SystemExit("ERROR: anchor not found")

FAST_PATH = '''    # ---- FAST PATH: read from team_fundamentals JSONB (sub-ms) ----
    fund_row = None
    try:
        fund_row = await db_pool.fetchrow(
            "SELECT data FROM team_fundamentals WHERE match_id = $1",
            int(fixture_id))
    except Exception:
        pass
    if fund_row and fund_row["data"]:
        import json as _json
        fd = fund_row["data"]
        if isinstance(fd, str):
            fd = _json.loads(fd)

        def _gs(m, k, d=0):
            v = m.get(k)
            return int(v) if v is not None else d

        # H2H
        h2h_matches = []
        hs = {"home_wins": 0, "draws": 0, "away_wins": 0,
              "total_goals_home": 0, "total_goals_away": 0}
        for m in (fd.get("h2h") or [])[:20]:
            sh = m.get("home_score"); sa = m.get("away_score")
            if sh is None or sa is None:
                continue
            sh = int(sh); sa = int(sa)
            mh = m.get("home_team", ""); ma = m.get("away_team", "")
            res = "home_win" if sh > sa else ("draw" if sh == sa else "away_win")
            if mh == home_team:
                hs["total_goals_home"] += sh; hs["total_goals_away"] += sa
                if res == "home_win": hs["home_wins"] += 1
                elif res == "draw": hs["draws"] += 1
                else: hs["away_wins"] += 1
            else:
                hs["total_goals_home"] += sa; hs["total_goals_away"] += sh
                if res == "home_win": hs["away_wins"] += 1
                elif res == "draw": hs["draws"] += 1
                else: hs["home_wins"] += 1
            h2h_matches.append({"date": (m.get("date") or "")[:10],
                                "home": mh, "away": ma,
                                "score_h": sh, "score_a": sa, "result": res})
        h2h = {"matches": h2h_matches, "summary": hs}

        def _map_form(recent, side_rec, team, is_home):
            recs = []; w = d = l = gf = ga = 0
            for m in (recent or [])[:20]:
                sh = m.get("home_score"); sa = m.get("away_score")
                if sh is None or sa is None:
                    continue
                sh = int(sh); sa = int(sa)
                ih = (m.get("home_team", "") == team)
                sf = sh if ih else sa; sv = sa if ih else sh
                if sf > sv: r = "W"; w += 1
                elif sf == sv: r = "D"; d += 1
                else: r = "L"; l += 1
                gf += sf; ga += sv
                recs.append({"date": (m.get("date") or "")[:10],
                             "opponent": m.get("away_team" if ih else "home_team", ""),
                             "is_home": ih, "score_for": sf,
                             "score_against": sv, "result": r})
            tot = len(recs)
            summ = {"wins": w, "draws": d, "losses": l,
                    "goals_for_avg": round(gf / tot, 2) if tot else 0,
                    "goals_against_avg": round(ga / tot, 2) if tot else 0}
            sw = sd = sl = sgf = sga = 0
            for m in (side_rec or [])[:20]:
                sh = m.get("home_score"); sa = m.get("away_score")
                if sh is None or sa is None:
                    continue
                sh = int(sh); sa = int(sa)
                sf2 = sh if is_home else sa; sa2 = sa if is_home else sh
                if sf2 > sa2: sw += 1
                elif sf2 == sa2: sd += 1
                else: sl += 1
                sgf += sf2; sga += sa2
            st = len(side_rec or [])
            sl2 = "home_record" if is_home else "away_record"
            spec = {"wins": sw, "draws": sd, "losses": sl,
                    "goals_for_avg": round(sgf / st, 2) if st else 0,
                    "goals_against_avg": round(sga / st, 2) if st else 0}
            def _pts(mm):
                return 2 if mm["result"] == "W" else (1 if mm["result"] == "D" else 0)
            r5 = recs[:5]; p5 = recs[5:10]
            if len(r5) >= 3 and len(p5) >= 3:
                pr = sum(_pts(x) for x in r5) / len(r5)
                pp = sum(_pts(x) for x in p5) / len(p5)
                trend = "up" if pr > pp + 0.15 else ("down" if pr < pp - 0.15 else "stable")
            else:
                trend = "stable"
            return {"recent_matches": recs, "summary": summ, sl2: spec, "trend": trend}

        hf = _map_form(fd.get("home_recent"), fd.get("home_home_recent"), home_team, True)
        af = _map_form(fd.get("away_recent"), fd.get("away_away_recent"), away_team, False)

        # League table
        lt = []
        ts = fd.get("team_stats") or {}
        for t in (fd.get("league_table") or []):
            if not isinstance(t, dict):
                continue
            lt.append({"position": int(t.get("position") or 0),
                       "team": t.get("team", ""),
                       "played": t.get("played"), "won": t.get("won"),
                       "drawn": t.get("drawn"), "lost": t.get("lost"),
                       "gf": t.get("gf"), "ga": t.get("ga"),
                       "gd": t.get("gd"), "points": t.get("points"),
                       "points_3pt": t.get("points_3pt") or t.get("points_titan007")})
        for tn in (home_team, away_team):
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
                                r.get("gf") or 0), reverse=True)
        for i, r in enumerate(lt, 1):
            r["position"] = i
        hp = next((i for i, t in enumerate(lt) if t["team"] == home_team), -1)
        ap = next((i for i, t in enumerate(lt) if t["team"] == away_team), -1)
        if lt:
            mx = max(10, hp + 1 if hp >= 0 else 0, ap + 1 if ap >= 0 else 0)
            lt = lt[:mx]

        # EMA in-memory
        EA = 2.0 / 11.0
        def _ema(vals):
            o = []; c = None
            for v in vals:
                c = v if c is None else EA * v + (1 - EA) * c
                o.append(round(c, 3))
            return o
        def _kl(vs, ev, ds, rs):
            o = []
            for i in range(len(vs)):
                cl = vs[i]; op = cl if i == 0 else ev[i - 1]
                ws = max(0, i - 1); we = min(len(vs), i + 2)
                hi = max(vs[ws:we]); lo = min(vs[ws:we])
                hi = max(hi, op, cl); lo = min(lo, op, cl)
                o.append({"date": ds[i], "open": round(op, 3), "close": round(cl, 3),
                          "high": round(hi, 3), "low": round(lo, 3), "result": rs[i]})
            return o
        def _ema_block(recent_key, side_key, team, is_home):
            def _tolist(lst, sfilter=None):
                ms = []
                for m in (lst or [])[:20]:
                    sh = m.get("home_score"); sa = m.get("away_score")
                    if sh is None or sa is None:
                        continue
                    sh = int(sh); sa = int(sa)
                    mh = m.get("home_team", ""); ma = m.get("away_team", "")
                    if sfilter == "home" and mh != team: continue
                    if sfilter == "away" and ma != team: continue
                    ih = (mh == team); sf = sh if ih else sa; sv = sa if ih else sh
                    pts = 2 if sf > sv else (1 if sf == sv else 0)
                    ms.append({"date": (m.get("date") or "")[5:10].replace("-", "/"),
                               "pts": pts, "gf": sf, "ga": sv,
                               "result": "W" if pts == 2 else ("D" if pts == 1 else "L")})
                ms.reverse()
                return ms
            def _bld(ms):
                if not ms:
                    return {"ema_pts": [], "ema_gf": [], "ema_ga": [],
                            "kline_pts": [], "kline_gf": [], "kline_ga": [],
                            "dates": [], "results": []}
                ps = [m["pts"] for m in ms]; gs = [m["gf"] for m in ms]
                gas = [m["ga"] for m in ms]; ds = [m["date"] for m in ms]
                rs = [m["result"] for m in ms]
                ep = _ema(ps); eg = _ema(gs); ea = _ema(gas)
                return {"ema_pts": ep, "ema_gf": eg, "ema_ga": ea,
                        "kline_pts": _kl(ps, ep, ds, rs),
                        "kline_gf": _kl(gs, eg, ds, rs),
                        "kline_ga": _kl(gas, ea, ds, rs),
                        "dates": ds, "results": rs}
            rk = "home_recent" if is_home else "away_recent"
            sk = "home_home_recent" if is_home else "away_away_recent"
            sf2 = "home" if is_home else "away"
            return {"overall": _bld(_tolist(fd.get(rk))),
                    "side": _bld(_tolist(fd.get(sk), sf2))}

        return {"status": "ok",
                "fixture_id": int(fixture_id) if fixture_id.isdigit() else fixture_id,
                "match_info": match_info, "h2h": h2h,
                "home_team_form": hf, "away_team_form": af,
                "league_table": lt,
                "ema_data": {"home": _ema_block("", "", home_team, True),
                             "away": _ema_block("", "", away_team, False)},
                "data_source": "team_fundamentals"}

'''

if FAST_PATH.split('\n')[1].strip() in code:
    raise SystemExit("ERROR: fast-path already inserted")

new_code = code.replace(ANCHOR, FAST_PATH + ANCHOR, 1)

with open(APP, "w", encoding="utf-8") as f:
    f.write(new_code)

print(f"Inserted fast-path block ({len(FAST_PATH)} chars) before H2H section")
import py_compile
py_compile.compile(APP, doraise=True)
print("Syntax OK")
