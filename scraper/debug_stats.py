#!/usr/bin/env python3
"""Debug script: fetch analysis page for a match, print raw team stats table parsing."""
import sys
sys.path.insert(0, '/opt/ruipan/ruipan_repo/scraper')

import requests
import fundamental_fetcher as ff

SID = sys.argv[1] if len(sys.argv) > 1 else '3021929'
url = f'https://zq.titan007.com/analysis/{SID}.htm'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}

print(f'Fetching {url}')
resp = requests.get(url, headers=headers, timeout=15)
# titan007 is gb2312/gbk
for enc in ('gb18030', 'gbk', 'utf-8'):
    try:
        resp.encoding = enc
        html = resp.text
        break
    except Exception:
        continue
print(f'HTML length: {len(html)}')

# Show which file is being used
print(f'Module file: {ff.__file__}')

# Check what home/away teams are
result = ff.parse_analysis_page(html, SID)
home = result.get('home_team', '?')
away = result.get('away_team', '?')
print(f'Home: {home}, Away: {away}')

# Parse stats WITHOUT DB
stats = ff.parse_team_stats_tables(html, home, away)
print(f'\nStats teams: {list(stats.keys())}')
for team, sections in stats.items():
    print(f'\n=== {team} ===')
    for sec, vals in sections.items():
        print(f'  {sec}: {vals}')

# Also dump raw leaf tables for inspection
from html.parser import HTMLParser

class DebugParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.completed = []
        self.stack = []
    def _frame(self):
        return self.stack[-1] if self.stack else None
    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == 'table':
            self.stack.append({'rows': [], 'in_row': False, 'row_cells': [], 'in_cell': False, 'cell_buf': []})
        elif t == 'tr':
            f = self._frame()
            if f is not None:
                f['in_row'] = True
                f['row_cells'] = []
        elif t in ('td', 'th'):
            f = self._frame()
            if f is not None and f['in_row']:
                f['in_cell'] = True
                f['cell_buf'] = []
    def handle_endtag(self, tag):
        t = tag.lower()
        f = self._frame()
        if f is None: return
        if t in ('td', 'th') and f['in_cell']:
            txt = ''.join(f['cell_buf']).replace('&nbsp;', ' ').strip()
            f['row_cells'].append(txt)
            f['in_cell'] = False
            f['cell_buf'] = []
        elif t == 'tr' and f['in_row']:
            f['rows'].append(f['row_cells'])
            f['in_row'] = False
            f['row_cells'] = []
        elif t == 'table':
            self.stack.pop()
            if f['rows']:
                self.completed.append(f['rows'])
    def handle_data(self, data):
        f = self._frame()
        if f is not None and f['in_cell']:
            f['cell_buf'].append(data)

dp = DebugParser()
dp.feed(html)
print(f'\n\n=== Leaf tables found: {len(dp.completed)} ===')
for i, rows in enumerate(dp.completed):
    row0 = ' '.join(rows[0]) if rows else ''
    if 'SKA' in row0 or '斯巴达' in row0 or '哈巴' in row0:
        print(f'\n--- Table {i} ({len(rows)} rows) ---')
        for j, row in enumerate(rows):
            print(f'  Row {j} ({len(row)} cells): {row}')
