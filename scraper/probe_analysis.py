import urllib.request as urlrequest
import re, sys

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
sid = sys.argv[1] if len(sys.argv) > 1 else "3021929"
url = "https://zq.titan007.com/analysis/" + sid + ".htm"
req = urlrequest.Request(url, headers={"User-Agent": UA, "Referer": "https://www.titan007.com/"})
resp = urlrequest.urlopen(req, timeout=15)
html = resp.read().decode("utf-8", errors="replace")

# 1. Find content around isShowIntegral (standings data is right before it)
idx = html.find("isShowIntegral")
if idx > 0:
    print("=== 600 chars before isShowIntegral ===")
    print(html[max(0,idx-600):idx+50])
    print()

# 2. Find ShowIntegral function call and nearby code
for m in re.finditer(r'ShowIntegral', html):
    pos = m.start()
    print("=== ShowIntegral at", pos, "===")
    print(html[max(0,pos-200):pos+300])
    print()

# 3. Find all var declarations that contain arrays with numeric+team pattern
# Standings look like [position, team_id, 'name', value]
for m in re.finditer(r'var\s+(\w+)\s*=\s*(\[\[)', html):
    varname = m.group(1)
    start = m.start(2)
    # Get a sample
    sample = html[start:start+200]
    if re.search(r"\d+,\d+,'", sample):
        print("=== Array var:", varname, "at", m.start(), "===")
        print(sample[:200])
        print()

# 4. Look for integral/table/stand HTML div IDs
for div_id in re.findall(r'id=["\']([^"\']*(?:integral|rank|stand|jifen|table|league)[^"\']*)["\']', html, re.IGNORECASE):
    print("DIV id:", div_id)
