#!/usr/bin/env python3
"""
Fix _build_section v10: independent EMA per team/metric, then combine.

For each team, compute EMA independently on their OWN match dates:
  - gf EMA, ga EMA, pts EMA
Each EMA is continuous on that team's schedule.

Then merge on unified timeline using latest EMA values:
  home_strength[d] = h_gf_ema[d] + a_ga_ema[d]
  away_strength[d] = a_gf_ema[d] + h_ga_ema[d]

No forced pairing, no cumulative average, no double-EMA.
"""
import shutil, datetime, sys, re

APP = "/opt/ruipan/app.py"
BAK = APP + ".bak." + datetime.datetime.now().strftime("%Y%m%d_%H%M")

shutil.copy2(APP, BAK)
print(f"[OK] Backup: {BAK}")

with open(APP, "r") as f:
    code = f.read()

NEW_FUNC = '''        def _build_section(h_ms, a_ms):
            # Sort each team by date
            h_sorted = sorted(h_ms, key=lambda m: m["date"])
            a_sorted = sorted(a_ms, key=lambda m: m["date"])

            # Extract raw series on each team's own schedule
            h_dates = [m["date"] for m in h_sorted]
            a_dates = [m["date"] for m in a_sorted]
            h_gf_raw = [m["gf"] for m in h_sorted]
            h_ga_raw = [m["ga"] for m in h_sorted]
            h_pts_raw = [m["pts"] for m in h_sorted]
            h_res_raw = [m["result"] for m in h_sorted]
            a_gf_raw = [m["gf"] for m in a_sorted]
            a_ga_raw = [m["ga"] for m in a_sorted]
            a_pts_raw = [m["pts"] for m in a_sorted]
            a_res_raw = [m["result"] for m in a_sorted]

            # EMA independently for each metric
            h_gf_ema = _ema(h_gf_raw)
            h_ga_ema = _ema(h_ga_raw)
            h_pts_ema = _ema(h_pts_raw)
            a_gf_ema = _ema(a_gf_raw)
            a_ga_ema = _ema(a_ga_raw)
            a_pts_ema = _ema(a_pts_raw)

            # Build date->EMA lookup (last EMA value at that date)
            def _series_map(dates, vals):
                m = {}
                for d, v in zip(dates, vals):
                    m[d] = v
                return m

            h_gf_m = _series_map(h_dates, h_gf_ema)
            h_ga_m = _series_map(h_dates, h_ga_ema)
            h_pts_m = _series_map(h_dates, h_pts_ema)
            h_res_m = _series_map(h_dates, h_res_raw)
            a_gf_m = _series_map(a_dates, a_gf_ema)
            a_ga_m = _series_map(a_dates, a_ga_ema)
            a_pts_m = _series_map(a_dates, a_pts_ema)
            a_res_m = _series_map(a_dates, a_res_raw)

            # Unified timeline
            all_dates = sorted(set(h_dates) | set(a_dates))

            dates = []; hr = []; ar = []
            h_str = []; a_str = []
            h_pts_out = []; a_pts_out = []

            # Walk timeline, carry latest EMA forward
            h_gf_cur = h_ga_cur = h_pts_cur = 0.0
            a_gf_cur = a_ga_cur = a_pts_cur = 0.0
            h_res_cur = a_res_cur = ""

            for d in all_dates:
                if d in h_gf_m:
                    h_gf_cur = h_gf_m[d]
                    h_ga_cur = h_ga_m[d]
                    h_pts_cur = h_pts_m[d]
                    h_res_cur = h_res_m[d]
                if d in a_gf_m:
                    a_gf_cur = a_gf_m[d]
                    a_ga_cur = a_ga_m[d]
                    a_pts_cur = a_pts_m[d]
                    a_res_cur = a_res_m[d]

                dates.append(d)
                hr.append(h_res_cur); ar.append(a_res_cur)
                # Combine latest EMA values from both teams
                h_str.append(round(h_gf_cur + a_ga_cur, 3))
                a_str.append(round(a_gf_cur + h_ga_cur, 3))
                h_pts_out.append(round(h_pts_cur, 3))
                a_pts_out.append(round(a_pts_cur, 3))

            return {
                "kline_strength": _kl(h_str, dates, hr),
                "kline_pts": _kl(h_pts_out, dates, hr),
                "away_strength": _kl(a_str, dates, ar),
                "away_pts": _kl(a_pts_out, dates, ar),
            }'''

pattern = r'        def _build_section\(h_ms, a_ms\):.*?(?=\n        h_all = _get_matches)'
match = re.search(pattern, code, re.DOTALL)
if not match:
    print("[FAIL] Could not find _build_section function")
    sys.exit(1)

print(f"[OK] Found old _build_section ({len(match.group(0))} chars)")
code = code[:match.start()] + NEW_FUNC + code[match.end():]

with open(APP, "w") as f:
    f.write(code)

print("[OK] Replaced with: independent EMA per team, merge on timeline")
print("[DONE] Restart app.py to apply")
