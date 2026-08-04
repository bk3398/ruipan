#!/usr/bin/env python3
"""Test ALL 4 endpoints that loadOddsData calls via Promise.all."""
import json, urllib.request

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "diag/6.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            return r.status, body
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode()[:300]
        except: pass
        return e.code, body
    except Exception as e:
        return None, str(e)

data = json.loads(fetch("http://localhost:8000/api/v1/matches/today")[1])
matches = data.get("data", [])
print(f"Today: {len(matches)} matches\n")

endpoints = [
    ("odds-timeline", "/api/v1/matches/{fid}/odds-timeline"),
    ("analysis",      "/api/v1/matches/{fid}/analysis"),
    ("fundamental",   "/api/v1/matches/{fid}/fundamental"),
    ("odds-quick",    "/api/v1/matches/{fid}/odds-quick"),
]

# Test first 10 matches
for m in matches[:10]:
    fid = m.get("fixture_id")
    ht = m.get("home_team","?")
    at = m.get("away_team","?")
    st = m.get("status","?")
    print(f"--- {fid}: {ht} vs {at} [{st}] ---")
    for name, path in endpoints:
        code, body = fetch(f"http://localhost:8000{path.format(fid=fid)}")
        if code == 200:
            try:
                d = json.loads(body)
                if isinstance(d, dict):
                    # brief summary
                    bk_count = len(d.get("bookmakers", {}))
                    data_keys = list(d.get("data", {}).keys()) if isinstance(d.get("data"), dict) else f"list[{len(d.get('data',[]))}]"
                    print(f"  {name:15s} [{code}] keys={list(d.keys())[:6]} bk={bk_count} data={data_keys}")
                else:
                    print(f"  {name:15s} [{code}] {type(d).__name__} len={len(d) if hasattr(d,'__len__') else '?'}")
            except:
                print(f"  {name:15s} [{code}] JSON parse error, body={body[:100]}")
        else:
            print(f"  {name:15s} [{code}] ERROR: {body[:150]}")
    print()
