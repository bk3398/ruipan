import urllib.request as urlrequest
import re, sys

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
sid = sys.argv[1] if len(sys.argv) > 1 else "3021929"
url = "https://zq.titan007.com/analysis/" + sid + ".htm"
req = urlrequest.Request(url, headers={"User-Agent": UA, "Referer": "https://www.titan007.com/"})
resp = urlrequest.urlopen(req, timeout=15)
html = resp.read().decode("utf-8", errors="replace")

# 1. Extract integralDiv content
m = re.search(r'id=["\']integralDiv["\'][^>]*>(.*?)</div>', html, re.DOTALL)
if m:
    content = m.group(1)
    print("=== integralDiv (first 2000 chars) ===")
    print(content[:2000])
else:
    # Try broader search
    idx = html.find("integralDiv")
    if idx > 0:
        print("=== integralDiv context (3000 chars) ===")
        print(html[idx:idx+3000])
    else:
        print("integralDiv not found")

# 2. Also look for table with standings
print("\n\n=== Looking for <table> with rank/standing ===")
tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
for i, t in enumerate(tables):
    if re.search(r'排名|積分|积分|場次|场次|勝|胜|和|負|负', t):
        print(f"\n--- Table {i} (relevant, first 1500 chars) ---")
        # Strip tags for readability
        text = re.sub(r'<[^>]+>', ' | ', t)
        text = re.sub(r'\s+', ' ', text).strip()
        print(text[:1500])
        break

# 3. Check analyTop.js for ShowIntegral
print("\n\n=== Fetching analyTop.js for ShowIntegral ===")
try:
    js_url = "https://zq.titan007.com/Script/analyTop.js"
    js_req = urlrequest.Request(js_url, headers={"User-Agent": UA})
    js_resp = urlrequest.urlopen(js_req, timeout=10)
    js_content = js_resp.read().decode("utf-8", errors="replace")
    # Find ShowIntegral function
    m2 = re.search(r'function\s+ShowIntegral.*?(?=\nfunction|\Z)', js_content, re.DOTALL)
    if m2:
        print(m2.group(0)[:1500])
    else:
        # Search for integral-related code
        for kw in ["Integral", "integral", "rankData", "standData"]:
            for mm in re.finditer(kw, js_content):
                pos = mm.start()
                print(f"\n[{kw}] @{pos}:")
                print(js_content[max(0,pos-100):pos+300])
                break
except Exception as e:
    print(f"Failed: {e}")
