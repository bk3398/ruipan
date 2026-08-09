import urllib.request as urlrequest
import re, sys, json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
sid = sys.argv[1] if len(sys.argv) > 1 else "3021929"
url = "https://zq.titan007.com/analysis/" + sid + ".htm"
req = urlrequest.Request(url, headers={"User-Agent": UA, "Referer": "https://www.titan007.com/"})
resp = urlrequest.urlopen(req, timeout=15)
html = resp.read().decode("utf-8", errors="replace")

print("Status:", resp.status, "Size:", len(html))
print()

# 1. External scripts
scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
print("=== External scripts ===")
for s in scripts:
    print("  " + s)

# 2. Find integral/rank related content
print("\n=== Integral/Rank search ===")
for kw in ["integral", "rank", "stand", "jifen", "paiming", "TeamRank", "LeagueRank", "subleague", "GetData", "tableData"]:
    for m in re.finditer(kw, html, re.IGNORECASE):
        pos = m.start()
        ctx = html[max(0,pos-50):pos+120].replace(chr(10)," ").replace(chr(13),"").replace(chr(9)," ")
        print("  [" + kw + "] @" + str(pos) + ": " + ctx[:150])
        break

# 3. Parse h_data first record fully
m = re.search(r'var\s+h_data\s*=\s*(\[.*?\]);', html, re.DOTALL)
if m:
    print("\n=== h_data raw (first 800 chars) ===")
    print(m.group(1).strip()[:800])

# 4. v_data fully
m = re.search(r'var\s+v_data\s*=\s*(\[.*?\]);', html, re.DOTALL)
if m:
    print("\n=== v_data (H2H) ===")
    print(m.group(1).strip()[:1000])

# 5. Look for any AJAX/fetch URLs
print("\n=== AJAX/fetch URLs ===")
for m in re.finditer(r'(https?://[^\s"\'<>]+(?:rank|integral|jifen|table|standing|subleague)[^\s"\'<>]*)', html, re.IGNORECASE):
    print("  " + m.group(1))

# 6. Look for function calls that load rankings
print("\n=== Function calls with rank/integral ===")
for m in re.finditer(r'(\w+[Rr]ank\w*\([^)]*\)|\w+[Ii]ntegral\w*\([^)]*\)|\w+[Tt]able\w*\([^)]*\))', html):
    print("  " + m.group(0)[:120])
