#!/usr/bin/env python3
"""
Replace hardcoded jczq-recommend.html GitHub Pages URL in
live-scores-preview-v6.html with same-origin /jczq (nginx rewrite).
Logo stays on GitHub Pages CDN (no local copy on VPS).
"""
import shutil, datetime

SRC = "/opt/ruipan/static/live-scores-preview-v6.html"
BAK = SRC + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

shutil.copy2(SRC, BAK)
with open(SRC, "r", encoding="utf-8") as f:
    html = f.read()

orig_len = len(html)

old = "https://bk3398.github.io/ruipan/jczq-recommend.html"
new = "/jczq"
cnt = html.count(old)
if cnt:
    html = html.replace(old, new)
    print(f"Replaced {cnt}x jczq link -> /jczq")
else:
    print("jczq link not found (already fixed?)")

with open(SRC, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Size: {orig_len} -> {len(html)}")
print("OK - jczq link now same-origin")
