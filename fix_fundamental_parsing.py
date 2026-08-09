#!/usr/bin/env python3
"""Fix fundamental_fetcher.py: inline standings + team stats parsing."""
import re

FILE = "scraper/fundamental_fetcher.py"

with open(FILE, "r", encoding="utf-8") as f:
    code = f.read()

# ── Fix 1: Rewrite extract_inline_standings ──
# Handle single quotes via ast.literal_eval, 5-element totalScoreStr rows
old_extract = '''def extract_inline_standings(html):
    """
    Extract league standings from inline JS array embedded in analysis page.
    The array appears immediately before 'var guestScoreStr' or 'var isShowIntegral',
    format: [[rank, team_id, 'trad_team_name', points], ...]

    There may be two similar arrays (overall and away/home). We pick the one
    containing the most teams (typically 18 for a full league).
    """
    # Find all [[...]] arrays in the page that match standings pattern
    # Standings rows always start with [number, number, 'name', number]
    candidates = []
    for m in re.finditer(r'\\[\\[(\\d+),\\d+,', html):
        start = m.start()
        # Find matching closing ]]
        depth = 0
        end = start
        for i in range(start, min(start + 20000, len(html))):
            ch = html[i]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        arr_text = html[start:end]
        # Quick check: must contain quotes (team names) and be in the score/standings region
        if "'" not in arr_text and '"' not in arr_text:
            continue
        try:
            data = json.loads(arr_text)
            if isinstance(data, list) and len(data) >= 4:
                # Validate: each row should be [int, int, str, int/float]
                valid = 0
                for row in data:
                    if (isinstance(row, list) and len(row) >= 4
                        and isinstance(row[0], (int, float))
                        and isinstance(row[1], (int, float))
                        and isinstance(row[2], str)
                        and isinstance(row[3], (int, float))):
                        valid += 1
                if valid >= len(data) * 0.7:
                    candidates.append((len(data), data))
        except (json.JSONDecodeError, IndexError):
            continue

    if not candidates:
        return None

    # Pick the array with most teams (full league table, not split home/away)
    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0][1]

    standings = []
    for row in best:
        if isinstance(row, list) and len(row) >= 4:
            standings.append({
                "position": int(row[0]),
                "team_id": int(row[1]),
                "team": clean_team_name(str(row[2])),
                "points": row[3],
            })
    return standings if standings else None'''

new_extract = '''def extract_inline_standings(html):
    """
    Extract league standings from inline JS arrays in analysis page.

    Three arrays exist:
      totalScoreStr = [[status, rank, team_id, 'trad_name', points], ...]  (5 cols, full table)
      homeScoreStr  = [[rank, team_id, 'trad_name', points], ...]           (4 cols, home only)
      guestScoreStr = [[rank, team_id, 'trad_name', points], ...]           (4 cols, away only)

    We prefer totalScoreStr (complete league). JS uses single quotes, so
    ast.literal_eval handles it natively (json.loads only accepts double quotes).
    """
    import ast

    # First try totalScoreStr (most complete: 5 columns with status flag)
    m = re.search(r'var\\s+totalScoreStr\\s*=\\s*(\\[\\[.*?\\]\\])\\s*;', html, re.DOTALL)
    if m:
        try:
            data = ast.literal_eval(m.group(1))
            if isinstance(data, list) and len(data) >= 4:
                standings = []
                for row in data:
                    if isinstance(row, list) and len(row) >= 5:
                        # [status, rank, team_id, name, points]
                        standings.append({
                            "position": int(row[1]),
                            "team_id": int(row[2]),
                            "team": clean_team_name(str(row[3])),
                            "points_titan007": int(row[4]),
                            "status_flag": int(row[0]),
                        })
                if standings:
                    return standings
        except Exception:
            pass

    # Fallback: look for any [[N,N,'...',N pattern arrays
    candidates = []
    for m in re.finditer(r'\\[\\[(\\d+),\\d+,', html):
        start = m.start()
        depth = 0
        end = start
        for i in range(start, min(start + 20000, len(html))):
            ch = html[i]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        arr_text = html[start:end]
        if "'" not in arr_text and '"' not in arr_text:
            continue
        try:
            data = ast.literal_eval(arr_text)
            if isinstance(data, list) and len(data) >= 4:
                valid = 0
                for row in data:
                    if isinstance(row, list) and len(row) >= 4:
                        if (isinstance(row[0], (int, float))
                            and isinstance(row[1], (int, float))
                            and isinstance(row[2], str)
                            and isinstance(row[3], (int, float))):
                            valid += 1
                if valid >= len(data) * 0.7:
                    candidates.append((len(data), data))
        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0][1]

    standings = []
    for row in best:
        if isinstance(row, list) and len(row) >= 4:
            standings.append({
                "position": int(row[0]),
                "team_id": int(row[1]),
                "team": clean_team_name(str(row[2])),
                "points_titan007": int(row[3]) if isinstance(row[3], (int, float)) else row[3],
            })
    return standings if standings else None'''

if old_extract in code:
    code = code.replace(old_extract, new_extract)
    print("[OK] extract_inline_standings replaced")
else:
    print("[WARN] extract_inline_standings pattern not found exactly, trying regex...")
    # Try a looser replacement
    pattern = r'def extract_inline_standings\(html\):.*?(?=\ndef parse_standings_js)'
    if re.search(pattern, code, re.DOTALL):
        code = re.sub(pattern, new_extract + '\n\n\n', code, flags=re.DOTALL)
        print("[OK] extract_inline_standings replaced via regex")
    else:
        print("[ERROR] Could not find extract_inline_standings!")

# ── Fix 2: Rewrite parse_team_stats_tables ──
old_stats = '''def parse_team_stats_tables(html, home_team, away_team):
    """
    Parse the team statistics tables from HTML.
    Each team has 4 rows: 總(all), 主(home), 客(away), 近6(recent6)
    Columns: 賽 勝 平 負 得 失 凈 積分 排名 勝率

    Team names in HTML are traditional Chinese. We match both trad and simp.
    """
    stats = {}
    # Build name variants for matching: try original (trad from page), simplified, stripped
    def name_variants(name):
        if not name:
            return set()
        variants = {name, t2s(name), s2t(name)}
        # Also strip common suffixes/prefixes and whitespace
        return {v.strip() for v in variants if v and len(v.strip()) >= 2}

    home_variants = name_variants(home_team)
    away_variants = name_variants(away_team)

    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    for table_html in tables:
        # Extract rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        for row_html in rows:
            # Extract cells from row
            cells_raw = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL)
            cells = []
            for c in cells_raw:
                # Strip HTML tags but keep text
                txt = re.sub(r'<[^>]+>', '', c)
                txt = txt.replace('&nbsp;', ' ').strip()
                cells.append(txt)

            if not cells:
                continue

            cell_text = ' '.join(cells)
            matched_team = None
            for label, variants in [(home_team, home_variants), (away_team, away_variants)]:
                for v in variants:
                    if v in cell_text:
                        matched_team = label
                        break
                if matched_team:
                    break

            if not matched_team:
                continue

            # Extract all numeric values from the row (賽 勝 平 負 得 失 凈 積分 排名 勝率%)
            # Format observed: row label (總/主/客/近6) followed by 10 values
            vals = []
            section_label = None
            for c in cells:
                if c in ('總', '主', '客', '近6', '全場'):
                    section_label = c
                    continue
                # Check if it's a number or percentage
                c_clean = c.replace('%', '').replace(',', '').strip()
                try:
                    if '.' in c_clean:
                        vals.append(float(c_clean))
                    elif c_clean.lstrip('-').isdigit():
                        vals.append(int(c_clean))
                except ValueError:
                    pass

            if len(vals) >= 9:
                if matched_team not in stats:
                    stats[matched_team] = {}
                section_map = {'總': 'overall', '主': 'home', '客': 'away', '近6': 'recent6', '全場': 'overall'}
                sec_key = section_map.get(section_label, 'overall')
                row = {
                    'played': vals[0],
                    'won': vals[1] if len(vals) > 1 else 0,
                    'drawn': vals[2] if len(vals) > 2 else 0,
                    'lost': vals[3] if len(vals) > 3 else 0,
                    'gf': vals[4] if len(vals) > 4 else 0,
                    'ga': vals[5] if len(vals) > 5 else 0,
                    'gd': vals[6] if len(vals) > 6 else 0,
                    'points': vals[7] if len(vals) > 7 else 0,
                    'rank': vals[8] if len(vals) > 8 else None,
                }
                if len(vals) > 9:
                    wr = vals[9]
                    row['win_rate'] = wr / 100.0 if wr > 1 else wr
                stats[matched_team][sec_key] = row

    return stats'''

new_stats = '''def parse_team_stats_tables(html, home_team, away_team):
    """
    Parse team statistics tables from HTML.

    Table structure (6 rows):
      Row 0: header — contains team name + '全場 賽 勝 平 負 得 失 凈 積分 排名 勝率'
      Row 1: 總    — overall stats (10 numeric values)
      Row 2: 主    — home stats (10 values)
      Row 3: 客    — away stats (10 values)
      Row 4: 近6   — recent 6 matches (9 values, no rank)
      Row 5: (empty or extra)

    Team name is ONLY in the header row. We first identify which table
    belongs to which team, then parse all data rows in that table.

    Scoring: our rule is win=2, draw=1, loss=0 (2-point system).
    titan007 displays 3-point system. We recalculate points from W/D/L.
    """
    stats = {}

    def name_variants(name):
        if not name:
            return set()
        variants = {name, t2s(name), s2t(name)}
        return {v.strip() for v in variants if v and len(v.strip()) >= 2}

    home_variants = name_variants(home_team)
    away_variants = name_variants(away_team)

    def extract_cells(row_html):
        cells_raw = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL)
        cells = []
        for c in cells_raw:
            txt = re.sub(r'<[^>]+>', '', c)
            txt = txt.replace('&nbsp;', ' ').strip()
            cells.append(txt)
        return cells

    def parse_numeric_row(cells):
        """Parse a data row: first non-numeric cell is section label, rest are numbers."""
        vals = []
        section_label = None
        for c in cells:
            if c in ('總', '主', '客', '近6', '全場'):
                section_label = c
                continue
            c_clean = c.replace('%', '').replace(',', '').strip()
            if not c_clean:
                continue
            try:
                if '.' in c_clean:
                    vals.append(float(c_clean))
                elif c_clean.lstrip('-').isdigit():
                    vals.append(int(c_clean))
            except ValueError:
                pass
        return section_label, vals

    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)

    for table_html in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        if len(rows) < 4:
            continue

        # Check first row for team name
        header_cells = extract_cells(rows[0])
        header_text = ' '.join(header_cells)

        matched_team = None
        if any(v in header_text for v in home_variants):
            matched_team = home_team
        elif any(v in header_text for v in away_variants):
            matched_team = away_team

        if not matched_team:
            continue

        # Check this is a stats table (should contain these keywords)
        if not any(kw in header_text for kw in ('賽', '勝', '積分', '全場')):
            continue

        if matched_team not in stats:
            stats[matched_team] = {}

        # Parse data rows (rows after header)
        section_map = {'總': 'overall', '主': 'home', '客': 'away', '近6': 'recent6', '全場': 'overall'}
        for row_html in rows[1:]:
            cells = extract_cells(row_html)
            if not cells:
                continue
            section_label, vals = parse_numeric_row(cells)
            if not section_label or len(vals) < 7:
                continue

            sec_key = section_map.get(section_label, 'overall')
            played = vals[0]
            won = vals[1] if len(vals) > 1 else 0
            drawn = vals[2] if len(vals) > 2 else 0
            lost = vals[3] if len(vals) > 3 else 0
            gf = vals[4] if len(vals) > 4 else 0
            ga = vals[5] if len(vals) > 5 else 0
            gd = vals[6] if len(vals) > 6 else 0

            # titan007 points (3-point system) at index 7
            titan_points = vals[7] if len(vals) > 7 else 0
            # Our points (2-point system: win=2, draw=1, loss=0)
            our_points = won * 2 + drawn

            # Rank at index 8 (not present in 近6 row)
            rank = vals[8] if len(vals) > 8 else None
            # Win rate at index 9
            win_rate = None
            if len(vals) > 9:
                wr = vals[9]
                win_rate = wr / 100.0 if wr > 1 else wr

            stats[matched_team][sec_key] = {
                'played': played,
                'won': won,
                'drawn': drawn,
                'lost': lost,
                'gf': gf,
                'ga': ga,
                'gd': gd,
                'points': our_points,           # our 2-point system
                'points_3pt': titan_points,     # titan007 3-point system
                'rank': rank,
                'win_rate': win_rate,
            }

    return stats'''

if old_stats in code:
    code = code.replace(old_stats, new_stats)
    print("[OK] parse_team_stats_tables replaced")
else:
    print("[WARN] parse_team_stats_tables pattern not found exactly, trying regex...")
    pattern = r'def parse_team_stats_tables\(html, home_team, away_team\):.*?(?=\ndef parse_stat_values)'
    if re.search(pattern, code, re.DOTALL):
        code = re.sub(pattern, new_stats + '\n\n\n', code, flags=re.DOTALL)
        print("[OK] parse_team_stats_tables replaced via regex")
    else:
        print("[ERROR] Could not find parse_team_stats_tables!")

# Also add a function to recalculate full league table with 2-point system
# and update the main parser to call it
old_league_block = '''    # 6. League standings: prefer inline array (most reliable), fallback to external JS
    standings = extract_inline_standings(html)
    if standings:
        result["league_table"] = standings
        log.info("  league_table (inline): %d teams", len(standings))
    elif league_id:
        standings = try_fetch_standings(league_id)
        if standings:
            result["league_table"] = standings
            log.info("  league_table (external): %d teams", len(standings))'''

new_league_block = '''    # 6. League standings from inline JS array
    standings = extract_inline_standings(html)
    if standings:
        # Recalculate points with our 2-point system (win=2, draw=1, loss=0)
        # for the two teams in this match, using their parsed team_stats W/D/L
        team_stats = result.get("team_stats", {})
        for team_label, stats_key in [(home_team, home_team), (away_team, away_team)]:
            if stats_key in team_stats and "overall" in team_stats[stats_key]:
                s = team_stats[stats_key]["overall"]
                our_pts = s.get("won", 0) * 2 + s.get("drawn", 0)
                for row in standings:
                    # Match by team name (simplified)
                    row_team = t2s(row.get("team", ""))
                    if row_team == t2s(team_label) or t2s(team_label) in row_team or row_team in t2s(team_label):
                        row["points"] = our_pts
                        row["points_recalculated"] = True
                        break
        # For other teams, keep titan007 points (we don't have their W/D/L)
        for row in standings:
            if "points" not in row:
                row["points"] = row.get("points_titan007", 0)
                row["points_recalculated"] = False
        result["league_table"] = standings
        log.info("  league_table (inline): %d teams", len(standings))
    elif league_id:
        standings = try_fetch_standings(league_id)
        if standings:
            result["league_table"] = standings
            log.info("  league_table (external): %d teams", len(standings))'''

if old_league_block in code:
    code = code.replace(old_league_block, new_league_block)
    print("[OK] league standings block replaced")
else:
    print("[WARN] league standings block not found exactly")

with open(FILE, "w", encoding="utf-8") as f:
    f.write(code)

print("\n[Done] File written. Verifying syntax...")
import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("[OK] Syntax valid")
except py_compile.PyCompileError as e:
    print(f"[ERROR] Syntax error: {e}")
