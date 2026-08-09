#!/usr/bin/env python3
"""Probe encoding using the same UA as fundamental_fetcher."""
import urllib.request, re

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
url = "https://zq.titan007.com/analysis/3021929.htm"
req = urllib.request.Request(url, headers={
    "User-Agent": UA,
    "Referer": "https://www.titan007.com/",
})
resp = urllib.request.urlopen(req, timeout=15)

print("Content-Encoding:", resp.headers.get("Content-Encoding"))
print("Content-Type:", resp.headers.get("Content-Type"))

raw = resp.read()
print("Gzip magic:", raw[:2] == b'\x1f\x8b')
print("Raw len:", len(raw))

# Find charset in meta
meta = re.findall(rb'charset\s*=\s*["\']?([\w-]+)', raw[:3000], re.IGNORECASE)
print("Meta charset:", meta)

# Show bytes around first Chinese-looking area
# Find SKA
idx = raw.find(b'SKA')
if idx >= 0:
    print(f"\nBytes around SKA (offset {idx}):")
    print(repr(raw[idx:idx+80]))

# Try each encoding
for enc in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'big5']:
    try:
        text = raw.decode(enc)
        i = text.find('SKA')
        if i >= 0:
            print(f"\n{enc}: ...{text[i:i+50]}...")
        else:
            print(f"\n{enc}: (SKA not found, first 200): {text[:200]}")
    except Exception as e:
        print(f"\n{enc}: FAILED {e}")
