#!/usr/bin/env python3
"""Patch app.py to add /api/v1/live endpoint.
Direct fetch from bfdata (no DB), returns live matches with minute/score/status.
"""
import re, sys

APP = "/opt/ruipan/app.py"

LIVE_ENDPOINT = r'''
# ── Live scores endpoint (direct bfdata, no DB) ──────────────────────
import re as _re_live
from urllib import request as _urlreq_live

_LIVE_BFDATA_URL = "https://live.titan007.com/VbsXml/bfdata_ut.js?r=007"
_LIVE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_LIVE_CACHE = {"ts": 0.0, "data": None}
_LIVE_TTL = 8  # seconds

_LIVE_STATUS = {
    1: ("live", 0),   # first half
    2: ("live", 45),  # halftime, show 45
    3: ("live", 45),  # second half, add 45
    4: ("live", 90),  # extra first half
    5: ("live", 105), # extra second half
    6: ("finished", 0),
    7: ("live", 120), # penalty
}

def _fetch_live_bfdata():
    now = time.time()
    if _LIVE_CACHE["data"] is not None and now - _LIVE_CACHE["ts"] < _LIVE_TTL:
        return _LIVE_CACHE["data"]
    try:
        req = _urlreq_live.Request(_LIVE_BFDATA_URL, headers={"User-Agent": _LIVE_UA, "Referer": "https://live.titan007.com/"})
        with _urlreq_live.urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return _LIVE_CACHE["data"]  # stale cache on error
    entries = _re_live.findall(r'A\[(\d+)\]="([^"]*)"', raw)
    result = []
    for _idx, data in entries:
        fs = data.split("^")
        if len(fs) < 20:
            continue
        try:
            sc = int(fs[13]) if fs[13].lstrip("-").isdigit() else 0
            if sc < 1 or sc > 7:
                continue
            sid = fs[0]
            minute_raw = int(fs[40]) if len(fs) > 40 and fs[40].isdigit() else 0
            base = _LIVE_STATUS.get(sc, ("live", 0))
            if sc == 1:
                minute = minute_raw
            elif sc == 2:
                minute = 45
            elif sc == 3:
                minute = 45 + minute_raw
            elif sc == 4:
                minute = 90 + minute_raw
            elif sc == 5:
                minute = 105 + minute_raw
            elif sc == 7:
                minute = 120
            else:
                minute = 0
            minute = min(minute, 130)
            hs = int(fs[15]) if len(fs) > 15 and fs[15].lstrip("-").isdigit() else 0
            as_ = int(fs[16]) if len(fs) > 16 and fs[16].lstrip("-").isdigit() else 0
            ht_h = int(fs[17]) if len(fs) > 17 and fs[17].lstrip("-").isdigit() else None
            ht_a = int(fs[18]) if len(fs) > 18 and fs[18].lstrip("-").isdigit() else None
            result.append({
                "schedule_id": sid,
                "status_code": sc,
                "status": base[0],
                "minute": minute,
                "home_score": hs,
                "away_score": as_,
                "home_ht_score": ht_h,
                "away_ht_score": ht_a,
            })
        except Exception:
            continue
    _LIVE_CACHE["ts"] = now
    _LIVE_CACHE["data"] = result
    return result

@app.get("/api/v1/live")
async def live_scores():
    data = _fetch_live_bfdata()
    if data is None:
        return JSONResponse({"status": "error", "message": "bfdata fetch failed"}, status_code=502)
    return JSONResponse({"status": "ok", "count": len(data), "data": data, "ts": int(time.time())})

'''

def main():
    with open(APP, "r", encoding="utf-8") as f:
        src = f.read()

    if "/api/v1/live" in src and "_fetch_live_bfdata" in src:
        print("[SKIP] live endpoint already exists")
        return

    # Find a good insertion point: right after app = FastAPI or before first @app.get
    # Insert before the first route definition
    m = re.search(r'(@app\.(get|post)\()', src)
    if not m:
        print("[ERROR] cannot find first route in app.py")
        sys.exit(1)

    insert_pos = m.start()
    new_src = src[:insert_pos] + LIVE_ENDPOINT + "\n" + src[insert_pos:]

    with open(APP, "w", encoding="utf-8") as f:
        f.write(new_src)

    # verify syntax
    import py_compile
    try:
        py_compile.compile(APP, doraise=True)
        print(f"[OK] inserted live endpoint ({len(LIVE_ENDPOINT)} chars), syntax OK")
    except py_compile.PyCompileError as e:
        print(f"[ERROR] syntax error: {e}")
        # rollback
        with open(APP, "w", encoding="utf-8") as f:
            f.write(src)
        sys.exit(1)

if __name__ == "__main__":
    main()
