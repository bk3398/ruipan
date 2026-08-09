#!/usr/bin/env python3
"""Probe the actual encoding of titan007 analysis page."""
import sys
import urllib.request
import gzip
import io

SID = sys.argv[1] if len(sys.argv) > 1 else '3021929'
url = f'https://zq.titan007.com/analysis/{SID}.htm'
req = urllib.request.Request(url, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Referer": "https://www.titan007.com/",
    "Accept-Encoding": "gzip, deflate",
})
resp = urllib.request.urlopen(req, timeout=15)

# Check headers
print("=== Response Headers ===")
for k, v in resp.headers.items():
    print(f"  {k}: {v}")

raw = resp.read()
print(f"\nRaw bytes length: {len(raw)}")

# Check gzip
if raw[:2] == b'\x1f\x8b':
    print("Content is gzipped, decompressing...")
    raw = gzip.decompress(raw)
    print(f"Decompressed length: {len(raw)}")

# Find charset in meta tags
import re
meta_matches = re.findall(rb'charset\s*=\s*["\']?([\w-]+)', raw[:2000], re.IGNORECASE)
print(f"\nCharset declared in HTML: {meta_matches}")

# Show first 500 bytes as repr
print(f"\n=== First 500 bytes (repr) ===")
print(repr(raw[:500]))

# Try each encoding on a section that should have Chinese
# Find h_data or team name area
for enc in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'big5']:
    try:
        text = raw.decode(enc)
        # Find a known section - look for SKA
        idx = text.find('SKA')
        if idx >= 0:
            sample = text[max(0,idx-20):idx+40]
        else:
            sample = text[200:300]
        print(f"\n=== {enc} (first Chinese area) ===")
        print(sample)
    except Exception as e:
        print(f"\n=== {enc} FAILED: {e} ===")
