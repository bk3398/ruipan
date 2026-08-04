#!/usr/bin/env python3
"""
Probe titan007 odds change history endpoints.
Tests multiple URL patterns for both Asian and Euro odds change data.
Run on VPS where titan007 is directly accessible.

Usage: python3 probe_titan_history.py
"""
import subprocess
import re
import json
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def http_get(url, referer=None, timeout=10):
    headers = {
        'User-Agent': UA,
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'identity',
    }
    if referer:
        headers['Referer'] = referer
    try:
        req = urlrequest.Request(url, headers=headers)
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return resp.status, data.decode('utf-8', errors='replace'), dict(resp.headers)
    except HTTPError as e:
        return e.code, str(e), {}
    except Exception as e:
        return -1, str(e), {}

# Step 1: Get today's matches from bfdata
print("=" * 70)
print("STEP 1: Fetch today's matches from bfdata_ut.js")
print("=" * 70)

status, content, _ = http_get('https://live.titan007.com/VbsXml/bfdata_ut.js?r=007')
if status != 200:
    print(f"Failed to fetch bfdata: {status} {content[:200]}")
    exit(1)

print(f"bfdata length: {len(content)} chars")

# Parse match IDs - look for schedule IDs in the data
# bfdata format: typically A[matchId]=[...] arrays
# Let's find some valid schedule IDs
match_ids = re.findall(r'A\[(\d{6,8})\]', content)
if not match_ids:
    # Try alternative patterns
    match_ids = re.findall(r'\[(\d{7}),', content)

# Deduplicate, take first 5
match_ids = list(dict.fromkeys(match_ids))[:5]
print(f"Found match IDs: {match_ids}")

# Also extract match info for context
for mid in match_ids[:3]:
    # Find the line containing this match
    pattern = rf'A\[{mid}\]=\[([^\]]+)\]'
    m = re.search(pattern, content)
    if m:
        fields = m.group(1).split(',')
        if len(fields) >= 10:
            # Typical: scheduleId,leagueId,date,time,homeId,awayId,...
            print(f"  Match {mid}: {fields[:8]}")

# If we can't parse match IDs from bfdata, use known recent ones
if not match_ids:
    # Try fetching from the analysis page list
    print("Could not parse match IDs from bfdata, trying known IDs...")
    match_ids = ['2597871', '2597872', '2597873']

# Use first match ID for probing
test_sid = match_ids[0] if match_ids else '2597871'
print(f"\nUsing match ID {test_sid} for endpoint probe\n")

# Step 2: Probe Asian odds change endpoints
print("=" * 70)
print(f"STEP 2: Probe Asian odds history endpoints (sid={test_sid})")
print("=" * 70)

# Company IDs: 3=crown, 1=macau, 47=pinnacle
asian_companies = [('3', 'crown'), ('1', 'macau'), ('47', 'pinnacle')]

asian_url_patterns = [
    # JS data files (various known patterns)
    "https://vip.titan007.com/JSData/AsianOdds/{cid}_{sid}.js",
    "https://vip.titan007.com/JSData/OddsAsian/{cid}_{sid}.js",
    "https://vip.titan007.com/JSData/AsianHandicap/{cid}_{sid}.js",
    "https://vip.titan007.com/AsianOdds/{cid}_{sid}.js",
    "https://vip.titan007.com/data/AsianOdds/{cid}_{sid}.js",
    "https://vip.titan007.com/data/ah/{cid}_{sid}.js",
    "https://op1.titan007.com/AsianOdds/{cid}_{sid}.js",
    "https://op1.titan007.com/change/ah_{cid}_{sid}.js",
    "https://op1.titan007.com/change/{cid}_{sid}.js",
    "https://live.titan007.com/JSData/AsianOdds/{cid}_{sid}.js",
    "https://live.titan007.com/VbsXml/AsianOdds/{cid}_{sid}.js",
    "https://live.titan007.com/vbsxml/ah_{cid}_{sid}.js",
    # ASP.NET endpoints with query params
    "https://vip.titan007.com/AsianOddsHistory.aspx?id={sid}&companyID={cid}",
    "https://vip.titan007.com/AsianOdds_n.aspx?id={sid}&cid={cid}",
    # JSON API patterns
    "https://vip.titan007.com/api/odds/asian/{sid}/{cid}",
    "https://api.titan007.com/odds/asian/{sid}/{cid}",
]

for cid, cname in asian_companies:
    print(f"\n--- {cname} (companyID={cid}) ---")
    for pattern in asian_url_patterns:
        url = pattern.format(cid=cid, sid=test_sid)
        ref = f"https://vip.titan007.com/AsianOdds_n.aspx?id={test_sid}"
        status, body, headers = http_get(url, referer=ref)
        snippet = body[:300].replace('\n', ' ').replace('\r', '') if body else ''
        content_type = headers.get('Content-Type', headers.get('content-type', ''))
        if status == 200 and len(body) > 50:
            print(f"  ✅ [{status}] {url}")
            print(f"     Size: {len(body)} bytes, Type: {content_type}")
            print(f"     Preview: {snippet[:200]}")
        elif status != 404 and status != -1:
            print(f"  ⚠️  [{status}] {url} ({len(body) if body else 0} bytes)")

# Step 3: Probe Euro odds change endpoints
print("\n" + "=" * 70)
print(f"STEP 3: Probe Euro odds history endpoints (sid={test_sid})")
print("=" * 70)

euro_companies = [('545', 'crown'), ('80', 'macau'), ('177', 'pinnacle')]

euro_url_patterns = [
    "https://1x2d.titan007.com/change/{cid}_{sid}.js",
    "https://1x2d.titan007.com/data/{cid}_{sid}.js",
    "https://1x2d.titan007.com/history/{cid}_{sid}.js",
    "https://1x2d.titan007.com/chg/{cid}_{sid}.js",
    "https://1x2d.titan007.com/{cid}_{sid}.js",
    "https://op1.titan007.com/change/{cid}_{sid}.js",
    "https://op1.titan007.com/1x2/change/{cid}_{sid}.js",
    "https://op1.titan007.com/OddsChange/{cid}_{sid}.js",
    "https://op1.titan007.com/euro/change/{cid}_{sid}.js",
    "https://vip.titan007.com/JSData/1x2/{cid}_{sid}.js",
    "https://vip.titan007.com/JSData/EuroOdds/{cid}_{sid}.js",
    "https://live.titan007.com/JSData/1x2/{cid}_{sid}.js",
    "https://live.titan007.com/JSData/EuroOdds/{cid}_{sid}.js",
    "https://live.titan007.com/VbsXml/1x2/{cid}_{sid}.js",
    "https://live.titan007.com/vbsxml/euro_{cid}_{sid}.js",
    "https://op1.titan007.com/change/euro_{cid}_{sid}.js",
    # Try Oddslist detail page
    f"https://op1.titan007.com/Oddslist/{test_sid}.htm",
    f"https://op1.titan007.com/OddsDetail/{test_sid}_{cid}.htm",
]

for cid, cname in euro_companies:
    print(f"\n--- {cname} (companyID={cid}) ---")
    for pattern in euro_url_patterns:
        url = pattern.format(cid=cid, sid=test_sid)
        ref = f"https://www.titan007.com/"
        status, body, headers = http_get(url, referer=ref)
        snippet = body[:300].replace('\n', ' ').replace('\r', '') if body else ''
        content_type = headers.get('Content-Type', headers.get('content-type', ''))
        if status == 200 and len(body) > 50:
            print(f"  ✅ [{status}] {url}")
            print(f"     Size: {len(body)} bytes, Type: {content_type}")
            print(f"     Preview: {snippet[:250]}")
        elif status != 404 and status != -1:
            print(f"  ⚠️  [{status}] {url} ({len(body) if body else 0} bytes)")

# Step 4: Fetch the main AsianOdds page and look for AJAX endpoints in its JS
print("\n" + "=" * 70)
print(f"STEP 4: Analyze AsianOdds_n.aspx page for AJAX/data endpoints")
print("=" * 70)

status, html, _ = http_get(
    f"https://vip.titan007.com/AsianOdds_n.aspx?id={test_sid}",
    referer=f"https://www.titan007.com/"
)
if status == 200:
    print(f"Page size: {len(html)} bytes")
    
    # Find JS file references
    js_files = re.findall(r'src=["\']([^"\']*\.js[^"\']*)["\']', html)
    print(f"\nJS files referenced ({len(js_files)}):")
    for js in js_files[:20]:
        print(f"  {js}")
    
    # Find AJAX/fetch/XHR calls
    ajax_urls = re.findall(r'(?:url|src|href|action)\s*[:=]\s*["\']([^"\']*(?:change|history|odds|data|ajax|api)[^"\']*)["\']', html, re.IGNORECASE)
    print(f"\nPotential AJAX/data URLs ({len(ajax_urls)}):")
    for u in set(ajax_urls[:20]):
        print(f"  {u}")
    
    # Find any function that loads change data
    change_funcs = re.findall(r'function\s+(\w*(?:change|history|detail|load)\w*)\s*\(', html, re.IGNORECASE)
    print(f"\nChange/history related functions: {change_funcs}")
    
    # Look for companyID-specific data loading
    data_loads = re.findall(r'["\']([^"\']*(?:AsianOdds|1x2|change|OddsData|GetOdds)[^"\']*)["\']', html, re.IGNORECASE)
    print(f"\nData loading URLs found in page JS ({len(set(data_loads))}):")
    for u in set(data_loads[:20]):
        print(f"  {u}")
    
    # Check for inline data
    if 'game=' in html or 'var game' in html:
        print("\n✅ Page contains inline odds data (var game=...)")
    if 'wholeLastOdds' in html:
        print("✅ Page contains wholeLastOdds (live odds marker)")
    
    # Save page for analysis
    with open('/tmp/asian_odds_page.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\nFull page saved to /tmp/asian_odds_page.html")
else:
    print(f"Failed to fetch page: {status}")

# Step 5: Also check the 1x2d main JS for any change history references
print("\n" + "=" * 70)
print(f"STEP 5: Analyze 1x2d main JS for change history references")
print("=" * 70)

status, js_content, _ = http_get(f"https://1x2d.titan007.com/{test_sid}.js")
if status == 200:
    print(f"1x2d JS size: {len(js_content)} bytes")
    
    # Check if there are any change history array/function references
    if 'change' in js_content.lower():
        change_refs = re.findall(r'["\']([^"\']*change[^"\']*)["\']', js_content, re.IGNORECASE)
        print(f"Change references: {list(set(change_refs))[:10]}")
    
    # The game array entries have timestamps - check format
    game_match = re.search(r'game=Array\((.+?)\);', js_content, re.DOTALL)
    if game_match:
        entries = game_match.group(1).split('","')
        print(f"\nTotal companies in game array: {len(entries)}")
        # Show crown entry (id 545)
        for entry in entries:
            if entry.startswith('545|'):
                fields = entry.split('|')
                print(f"\nCrown (545) fields ({len(fields)}):")
                for i, f in enumerate(fields):
                    print(f"  [{i}] {f}")
                break
else:
    print(f"Failed to fetch 1x2d JS: {status}")

print("\n" + "=" * 70)
print("PROBE COMPLETE")
print("=" * 70)
print("\nReview the ✅ entries above for working endpoints.")
print("If no change history endpoints found, we'll build our own timeline.")
