#!/usr/bin/env python3
"""All-in-one VPS patch deployer (no git required).
1. match_sync: protect finished/cancelled from bfdata overwrite
2. app.py: null league table fields default to 0
3. app.py: add /api/v1/live endpoint (direct bfdata)
4. frontend: live polling + goal flash/sound
"""
import os, sys, re, py_compile

APP = "/opt/ruipan/app.py"
SYNC = "/opt/ruipan/scraper/match_sync.py"
HTML = "/opt/ruipan/static/live-scores-preview-v6.html"

def patch_match_sync():
    if not os.path.exists(SYNC):
        print("[SKIP] match_sync.py not found")
        return
    with open(SYNC, "r", encoding="utf-8") as f:
        code = f.read()
    if "Don't overwrite finished" in code:
        print("[OK] match_sync already patched")
        return
    OLD = """                if existing:
                    if (existing['status'] != status or"""
    NEW = """                if existing:
                    # Don't overwrite finished/cancelled back to scheduled
                    if existing['status'] in ('finished', 'cancelled') and status in ('scheduled', 'not_started'):
                        continue
                    if (existing['status'] != status or"""
    if OLD not in code:
        print("[WARN] match_sync anchor not found, trying alternate")
        # Try a simpler anchor
        OLD2 = "if existing:\n"
        if OLD2 in code:
            NEW2 = OLD2 + "                    if existing['status'] in ('finished', 'cancelled') and status in ('scheduled', 'not_started'):\n                        continue\n"
            code = code.replace(OLD2, NEW2, 1)
        else:
            print("[ERROR] cannot patch match_sync")
            return
    else:
        code = code.replace(OLD, NEW, 1)
    with open(SYNC, "w", encoding="utf-8") as f:
        f.write(code)
    py_compile.compile(SYNC, doraise=True)
    print("[OK] match_sync.py: finished protected")

def patch_fastpath_nulls():
    with open(APP, "r", encoding="utf-8") as f:
        code = f.read()
    if "Ensure no null numeric fields" in code:
        print("[OK] fastpath nulls already patched")
        return
    OLD = """        for tn in (home_team, away_team):
            ov = (ts.get(tn) or {}).get("overall")
            if not ov:
                continue
            for r in lt:
                if r["team"] == tn:
                    for k in ("played", "won", "drawn", "lost", "gf", "ga", "gd", "points"):
                        if r.get(k) is None and k in ov:
                            r[k] = ov[k]
                    break"""
    NEW = """        for r in lt:
            for k in ("played", "won", "drawn", "lost", "gf", "ga", "gd", "points"):
                if r.get(k) is None:
                    r[k] = 0
        for tn in (home_team, away_team):
            ov = (ts.get(tn) or {}).get("overall")
            if not ov:
                continue
            for r in lt:
                if r["team"] == tn:
                    for k in ("played", "won", "drawn", "lost", "gf", "ga", "gd", "points"):
                        if k in ov:
                            r[k] = ov[k]
                    break"""
    if OLD not in code:
        print("[WARN] fastpath anchor not found, skipping (may already be patched differently)")
        return
    code = code.replace(OLD, NEW, 1)
    with open(APP, "w", encoding="utf-8") as f:
        f.write(code)
    py_compile.compile(APP, doraise=True)
    print("[OK] app.py: null fields default to 0")

LIVE_ENDPOINT = r'''
# -- Live scores endpoint (direct bfdata, no DB) --
import re as _re_live
from urllib import request as _urlreq_live
_LIVE_URL = "https://live.titan007.com/VbsXml/bfdata_ut.js?r=007"
_LIVE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_LIVE_CACHE = {"ts": 0.0, "data": None}
_LIVE_TTL = 8

def _fetch_live_bfdata():
    now = time.time()
    if _LIVE_CACHE["data"] is not None and now - _LIVE_CACHE["ts"] < _LIVE_TTL:
        return _LIVE_CACHE["data"]
    try:
        req = _urlreq_live.Request(_LIVE_URL, headers={"User-Agent": _LIVE_UA, "Referer": "https://live.titan007.com/"})
        with _urlreq_live.urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return _LIVE_CACHE["data"]
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
            mr = int(fs[40]) if len(fs) > 40 and fs[40].isdigit() else 0
            if sc == 1: minute = mr
            elif sc == 2: minute = 45
            elif sc == 3: minute = 45 + mr
            elif sc == 4: minute = 90 + mr
            elif sc == 5: minute = 105 + mr
            elif sc == 7: minute = 120
            else: minute = 0
            minute = min(minute, 130)
            hs = int(fs[15]) if len(fs) > 15 and fs[15].lstrip("-").isdigit() else 0
            aw = int(fs[16]) if len(fs) > 16 and fs[16].lstrip("-").isdigit() else 0
            hth = int(fs[17]) if len(fs) > 17 and fs[17].lstrip("-").isdigit() else None
            hta = int(fs[18]) if len(fs) > 18 and fs[18].lstrip("-").isdigit() else None
            result.append({"schedule_id": sid, "status_code": sc, "status": "live",
                           "minute": minute, "home_score": hs, "away_score": aw,
                           "home_ht_score": hth, "away_ht_score": hta})
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

def patch_live_endpoint():
    with open(APP, "r", encoding="utf-8") as f:
        code = f.read()
    if "/api/v1/live" in code:
        print("[OK] live endpoint already exists")
        return
    m = re.search(r'(@app\.(get|post)\()', code)
    if not m:
        print("[ERROR] cannot find route anchor in app.py")
        return
    code = code[:m.start()] + LIVE_ENDPOINT + "\n" + code[m.start():]
    with open(APP, "w", encoding="utf-8") as f:
        f.write(code)
    py_compile.compile(APP, doraise=True)
    print("[OK] app.py: /api/v1/live endpoint added")

LIVE_CSS = """
@keyframes goalFlash{0%{background:rgba(255,215,0,.6)}50%{background:rgba(255,215,0,.3)}100%{background:transparent}}
.match-row.goal-flash{animation:goalFlash 2s ease-out}
.score-cell.goal-scored{color:#ff6b00!important;font-weight:800;transform:scale(1.3);display:inline-block}
"""

LIVE_JS = r"""
// Live polling + goal alerts
var _livePrev={},_liveTimer=null,_liveCtx=null,_liveSnd=true;
function _liveBeep(){if(!_liveSnd)return;try{if(!_liveCtx)_liveCtx=new(window.AudioContext||window.webkitAudioContext)();var c=_liveCtx;[{f:880,t:0,d:.15},{f:1100,t:.18,d:.2}].forEach(function(n){var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.frequency.value=n.f;o.type="sine";g.gain.setValueAtTime(.3,c.currentTime+n.t);g.gain.exponentialRampToValueAtTime(.001,c.currentTime+n.t+n.d);o.start(c.currentTime+n.t);o.stop(c.currentTime+n.t+n.d)})}catch(e){}}
function _findLiveMatch(sid){for(var i=0;i<matchData.length;i++){var m=matchData[i];if(String(m.fixture_id)===String(sid)||String(m.schedule_id)===String(sid))return m}return null}
function pollLive(){fetch("/api/v1/live",{cache:"no-store"}).then(function(r){return r.json()}).then(function(data){if(data.status!=="ok"||!data.data)return;var changed=false,goals=[];data.data.forEach(function(lm){var m=_findLiveMatch(lm.schedule_id);if(!m)return;var k=lm.schedule_id,prev=_livePrev[k],cur=lm.home_score+"-"+lm.away_score;if(prev&&prev!==cur)goals.push({fid:m.fixture_id});_livePrev[k]=cur;if(m.status!=="live"){m.status="live";changed=true}if(m.minute!==lm.minute){m.minute=lm.minute;changed=true}if(m.home_score!==lm.home_score){m.home_score=lm.home_score;changed=true}if(m.away_score!==lm.away_score){m.away_score=lm.away_score;changed=true}if(lm.home_ht_score!=null)m.home_ht_score=lm.home_ht_score;if(lm.away_ht_score!=null)m.away_ht_score=lm.away_ht_score});if(changed){renderMatches();var s={total:matchData.length,live:0,not_started:0,finished:0};matchData.forEach(function(m){s[m.status]=(s[m.status]||0)+1});var el;if(el=document.getElementById("sumTotal"))el.textContent=s.total;if(el=document.getElementById("sumLive"))el.textContent=s.live;if(el=document.getElementById("sumWaiting"))el.textContent=s.not_started;if(el=document.getElementById("sumDone"))el.textContent=s.finished}goals.forEach(function(g){var row=document.querySelector('tr[data-fid="'+g.fid+'"]');if(row){row.classList.remove("goal-flash");void row.offsetWidth;row.classList.add("goal-flash")}_liveBeep()})}).catch(function(){})}
function startLivePoll(){if(_liveTimer)clearInterval(_liveTimer);pollLive();_liveTimer=setInterval(pollLive,20000);(function(){var rb=document.querySelector(".refresh-btn")||document.getElementById("refreshBtn");if(rb&&!document.getElementById("sndBtn")){var b=document.createElement("button");b.id="sndBtn";b.className=rb.className;b.style.cssText="margin-left:8px;font-size:1rem;cursor:pointer";b.textContent=String.fromCharCode(0xD83D,0xDD0A);b.onclick=function(){_liveSnd=!_liveSnd;b.textContent=_liveSnd?String.fromCharCode(0xD83D,0xDD0A):String.fromCharCode(0xD83D,0xDD07)};rb.parentNode.insertBefore(b,rb.nextSibling)}})()}
startLivePoll();
"""

def patch_frontend():
    with open(HTML, "r", encoding="utf-8") as f:
        src = f.read()
    if "pollLive" in src:
        print("[OK] frontend live polling already present")
        return
    if "</style>" in src:
        src = src.replace("</style>", LIVE_CSS + "\n</style>", 1)
    else:
        print("[WARN] no </style> found")
    script = "<script>\n" + LIVE_JS + "\n</script>\n"
    if "</body>" in src:
        src = src.replace("</body>", script + "</body>", 1)
    elif "</html>" in src:
        src = src.replace("</html>", script + "</html>", 1)
    else:
        src += "\n" + script
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(src)
    print("[OK] frontend: live polling + goal alerts added")

if __name__ == "__main__":
    # backup
    import shutil, time
    ts = time.strftime("%Y%m%d_%H%M")
    for p in (APP, SYNC, HTML):
        if os.path.exists(p):
            shutil.copy2(p, p + ".bak." + ts)
    print("Backups created with suffix .bak." + ts)
    patch_match_sync()
    patch_fastpath_nulls()
    patch_live_endpoint()
    patch_frontend()
    print("\nAll patches applied. Restart API: systemctl restart ruipan-api.service")
