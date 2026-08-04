#!/usr/bin/env python3
"""
Backtest Rebuild & Continuous Learning System
================================================
Full rebuild:  python3 rebuild_backtest.py
Incremental:   python3 rebuild_backtest.py --update

1. Extracts COEFF_TABLE and HDP_NAMES from live HTML (ensures consistency)
2. Creates backtest_samples table in PostgreSQL
3. Processes finished matches with valid paired asia+euro odds per bookmaker
4. Settles Asian handicap results (incl. quarter-ball half-win/half-lose)
5. Stores individual samples for traceability and incremental updates
6. Aggregates into lookup JSON matching existing format
7. Updates both JSON file and inline HTML BACKTEST_WINRATE_LOOKUP
8. Reports coverage statistics

Cron for continuous learning (run after scraper cycles):
  0 */2 * * * /usr/bin/python3 /opt/ruipan/backtest/rebuild_backtest.py --update >> /var/log/backtest_update.log 2>&1
"""

import subprocess
import json
import re
import sys
import os
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
HTML_PATH = '/opt/ruipan/static/live-scores-preview-v6.html'
JSON_PATH = '/opt/ruipan/static/backtest_winrate_lookup.json'
BACKTEST_DIR = '/opt/ruipan/backtest'
DB_NAME = 'ruipan'

# ─── PG helpers ───────────────────────────────────────────────────────────────
def psql(query, fetch=True):
    """Execute SQL via psql, return list of row-tuples."""
    cmd = ['sudo', '-u', 'postgres', 'psql', '-d', DB_NAME, '-t', '-A', '-F', '\x1f', '-c', query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"[PSQL ERROR] {r.stderr.strip()}", file=sys.stderr)
        return []
    if not fetch:
        return []
    rows = []
    for line in r.stdout.strip().split('\n'):
        if line:
            rows.append(tuple(line.split('\x1f')))
    return rows

def psql_exec(query):
    """Execute SQL without returning results (DDL/DML)."""
    cmd = ['sudo', '-u', 'postgres', 'psql', '-d', DB_NAME, '-q', '-c', query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"[PSQL EXEC ERROR] {r.stderr.strip()}", file=sys.stderr)
        return False
    return True

# ─── Extract constants from HTML ──────────────────────────────────────────────
def extract_js_constants():
    """Parse COEFF_TABLE and HDP_NAMES from the live HTML file."""
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    # Extract COEFF_TABLE
    coeff_match = re.search(r'COEFF_TABLE\s*=\s*\{([^}]+)\}', html)
    if not coeff_match:
        raise RuntimeError("Cannot find COEFF_TABLE in HTML")
    coeff_str = '{' + coeff_match.group(1) + '}'
    # Convert JS object to Python dict: keys might be 0, 0.25, etc or quoted
    coeff_str = re.sub(r'(\d+\.?\d*)\s*:', r'"\1":', coeff_str)
    COEFF_TABLE = json.loads(coeff_str)
    # Convert string keys to float
    COEFF_TABLE = {float(k): v for k, v in COEFF_TABLE.items()}

    # Extract HDP_NAMES
    hdp_match = re.search(r'HDP_NAMES\s*=\s*\{([^}]+)\}', html)
    if not hdp_match:
        raise RuntimeError("Cannot find HDP_NAMES in HTML")
    hdp_str = '{' + hdp_match.group(1) + '}'
    hdp_str = re.sub(r'(\d+\.?\d*)\s*:', r'"\1":', hdp_str)
    hdp_str = hdp_str.replace("'", '"')
    HDP_NAMES = json.loads(hdp_str)
    HDP_NAMES = {float(k): v for k, v in HDP_NAMES.items()}

    return COEFF_TABLE, HDP_NAMES


# ─── Binning functions (mirror JS) ────────────────────────────────────────────
def get_coeff(hdp, coeff_table):
    a = abs(hdp)
    if a in coeff_table:
        return coeff_table[a]
    if a > 4:
        return 8
    keys = sorted(coeff_table.keys())
    for i in range(len(keys) - 1):
        if keys[i] <= a < keys[i+1]:
            lo = coeff_table[keys[i]]
            hi = coeff_table[keys[i+1]]
            return lo + (hi - lo) * (a - keys[i]) / (keys[i+1] - keys[i])
    return 8


def hdp_name(hdp, hdp_names):
    a = abs(round(hdp * 100) / 100)
    sign = '主让' if hdp >= 0 else '客让'
    name = hdp_names.get(a, f'{a:.2f}')
    return f'{name}({sign})'


def water_bin(w):
    if w < 0.80: return '超低水'
    if w < 0.95: return '低水'
    if w < 1.05: return '中水'
    return '高水'


def divg_bin(d):
    if d < -0.20: return '负分歧'
    if d < -0.05: return '弱负分歧'
    if d < 0.10: return '中性'
    if d < 0.50: return '弱正分歧'
    if d < 1.50: return '正分歧'
    return '强正分歧'


# ─── Asian handicap settlement ────────────────────────────────────────────────
def settle_handicap(home_score, away_score, handicap):
    """
    Returns (upper_result, upper_water_side, lower_water_side)
    upper_result: 1.0=full win, 0.5=half win, 0.0=push, -0.5=half lose, -1.0=full lose
    """
    h = float(handicap)
    hs, as_ = int(home_score), int(away_score)

    if h >= 0:
        # Upper = home team
        upper_margin = (hs - as_) - h
    else:
        # Upper = away team
        upper_margin = (as_ - hs) - abs(h)

    # upper_margin is at 0.25 increments (integer score diff - 0.25-step line)
    if upper_margin >= 0.5:
        return 1.0
    elif upper_margin == 0.25:
        return 0.5
    elif upper_margin == 0:
        return 0.0
    elif upper_margin == -0.25:
        return -0.5
    else:
        return -1.0


def calc_profit(result, upper_water, lower_water):
    """Returns (upper_profit, lower_profit) for unit stake."""
    if result == 1.0:
        return upper_water, -1.0
    elif result == 0.5:
        return upper_water / 2.0, -0.5
    elif result == 0.0:
        return 0.0, 0.0
    elif result == -0.5:
        return -0.5, lower_water / 2.0
    else:  # -1.0
        return -1.0, lower_water


# ─── Database setup ───────────────────────────────────────────────────────────
def setup_database():
    psql_exec("""
        CREATE TABLE IF NOT EXISTS backtest_samples (
            id SERIAL PRIMARY KEY,
            match_id VARCHAR(50) NOT NULL,
            phase VARCHAR(10) NOT NULL,
            bookmaker VARCHAR(50) NOT NULL,
            handicap NUMERIC(6,2),
            upper_water NUMERIC(6,3),
            lower_water NUMERIC(6,3),
            own_euro NUMERIC(6,3),
            divg NUMERIC(8,4),
            hdp_name VARCHAR(30),
            water_bin VARCHAR(10),
            divg_bin VARCHAR(10),
            upper_result NUMERIC(3,1),
            upper_profit NUMERIC(6,3),
            lower_profit NUMERIC(6,3),
            home_score INT,
            away_score INT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(match_id, phase, bookmaker)
        );
    """)
    psql_exec("CREATE INDEX IF NOT EXISTS idx_bt_phase ON backtest_samples(phase);")
    psql_exec("CREATE INDEX IF NOT EXISTS idx_bt_match ON backtest_samples(match_id);")
    print("[DB] backtest_samples table ready")


# ─── Fetch and process matches ────────────────────────────────────────────────
def fetch_samples(incremental=False):
    """Fetch finished matches with valid paired odds and compute samples."""
    
    if incremental:
        # Only matches not already in backtest_samples
        match_filter = "AND m.match_id NOT IN (SELECT DISTINCT match_id FROM backtest_samples)"
        print("[MODE] Incremental update — only new finished matches")
    else:
        match_filter = ""
        print("[MODE] Full rebuild — processing all finished matches")

    query = f"""
        SELECT 
            m.match_id,
            m.home_score, m.away_score,
            ae.bookmaker,
            ae.handicap,
            ae.home_odds, ae.away_odds,
            ee.home_win, ee.draw, ee.away_win,
            'initial' AS phase
        FROM matches m
        JOIN odds_asia ae ON m.match_id = ae.match_id AND ae.odds_type = 'initial'
        JOIN odds_euro ee ON m.match_id = ee.match_id 
            AND ee.bookmaker = ae.bookmaker AND ee.odds_type = 'initial'
        WHERE m.status = 'finished'
          AND m.home_score IS NOT NULL 
          AND m.away_score IS NOT NULL
          AND ae.home_odds BETWEEN 0.5 AND 2.0 
          AND ae.away_odds BETWEEN 0.5 AND 2.0
          AND LEAST(ee.home_win, ee.draw, ee.away_win) BETWEEN 1.0 AND 3.0
          {match_filter}

        UNION ALL

        SELECT 
            m.match_id,
            m.home_score, m.away_score,
            ae.bookmaker,
            ae.handicap,
            ae.home_odds, ae.away_odds,
            ee.home_win, ee.draw, ee.away_win,
            'live' AS phase
        FROM matches m
        JOIN odds_asia ae ON m.match_id = ae.match_id AND ae.odds_type = 'live'
        JOIN odds_euro ee ON m.match_id = ee.match_id 
            AND ee.bookmaker = ae.bookmaker AND ee.odds_type = 'live'
        WHERE m.status = 'finished'
          AND m.home_score IS NOT NULL 
          AND m.away_score IS NOT NULL
          AND ae.home_odds BETWEEN 0.5 AND 2.0 
          AND ae.away_odds BETWEEN 0.5 AND 2.0
          AND LEAST(ee.home_win, ee.draw, ee.away_win) BETWEEN 1.0 AND 3.0
          {match_filter}
        ORDER BY match_id, phase, bookmaker;
    """
    
    rows = psql(query)
    print(f"[DATA] Fetched {len(rows)} raw (match×bookmaker×phase) samples")
    return rows


def process_samples(raw_rows, coeff_table, hdp_names):
    """Process raw DB rows into computed sample dicts."""
    samples = []
    skipped = 0
    
    for row in raw_rows:
        try:
            match_id = row[0]
            home_score = int(row[1])
            away_score = int(row[2])
            bookmaker = row[3]
            handicap = float(row[4])
            home_odds = float(row[5])
            away_odds = float(row[6])
            home_win = float(row[7])
            draw = float(row[8])
            away_win = float(row[9])
            phase = row[10]

            # Determine upper/lower water
            if handicap >= 0:
                upper_water = home_odds
                lower_water = away_odds
                own_euro = home_win
            else:
                upper_water = away_odds
                lower_water = home_odds
                own_euro = away_win

            # Compute divergence
            coeff = get_coeff(handicap, coeff_table)
            divg = (own_euro - 1.0) * coeff - upper_water

            # Settle result
            result = settle_handicap(home_score, away_score, handicap)
            upper_profit, lower_profit = calc_profit(result, upper_water, lower_water)

            # Bin features
            hn = hdp_name(handicap, hdp_names)
            wb = water_bin(upper_water)
            db = divg_bin(divg)

            samples.append({
                'match_id': match_id,
                'phase': phase,
                'bookmaker': bookmaker,
                'handicap': round(handicap, 2),
                'upper_water': round(upper_water, 3),
                'lower_water': round(lower_water, 3),
                'own_euro': round(own_euro, 3),
                'divg': round(divg, 4),
                'hdp_name': hn,
                'water_bin': wb,
                'divg_bin': db,
                'upper_result': result,
                'upper_profit': round(upper_profit, 3),
                'lower_profit': round(lower_profit, 3),
                'home_score': home_score,
                'away_score': away_score,
            })
        except (ValueError, TypeError, IndexError) as e:
            skipped += 1
            continue

    if skipped:
        print(f"[WARN] Skipped {skipped} rows due to parse errors")
    return samples


def insert_samples(samples):
    """Insert samples into backtest_samples table."""
    if not samples:
        print("[DB] No samples to insert")
        return 0

    inserted = 0
    # Batch in groups of 100
    batch_size = 100
    for i in range(0, len(samples), batch_size):
        batch = samples[i:i+batch_size]
        values = []
        for s in batch:
            values.append(
                f"('{s['match_id']}','{s['phase']}','{s['bookmaker']}',"
                f"{s['handicap']},{s['upper_water']},{s['lower_water']},"
                f"{s['own_euro']},{s['divg']},'{s['hdp_name']}','{s['water_bin']}','{s['divg_bin']}',"
                f"{s['upper_result']},{s['upper_profit']},{s['lower_profit']},"
                f"{s['home_score']},{s['away_score']})"
            )
        sql = f"""
            INSERT INTO backtest_samples 
            (match_id, phase, bookmaker, handicap, upper_water, lower_water,
             own_euro, divg, hdp_name, water_bin, divg_bin,
             upper_result, upper_profit, lower_profit, home_score, away_score)
            VALUES {','.join(values)}
            ON CONFLICT (match_id, phase, bookmaker) DO NOTHING;
        """
        if psql_exec(sql):
            inserted += len(batch)

    print(f"[DB] Inserted {inserted} samples (with conflict skip)")
    return inserted


# ─── Aggregate into lookup ────────────────────────────────────────────────────
def aggregate_lookup():
    """Aggregate backtest_samples into the lookup format."""
    lookup = {}
    
    for phase in ['initial', 'live']:
        # Count total and unique matches
        rows = psql(f"SELECT COUNT(*), COUNT(DISTINCT match_id) FROM backtest_samples WHERE phase='{phase}';")
        total_samples = int(rows[0][0]) if rows else 0
        unique_matches = int(rows[0][1]) if rows else 0
        print(f"[AGG] {phase}: {total_samples} samples from {unique_matches} matches")

        # Aggregate by hdp_name × water_bin × divg_bin
        rows = psql(f"""
            SELECT 
                hdp_name, water_bin, divg_bin,
                COUNT(*) as sample,
                -- win_rate_upper: weighted (half=0.5), pushes count as non-win
                ROUND(
                    SUM(CASE WHEN upper_result = 1.0 THEN 1.0
                             WHEN upper_result = 0.5 THEN 0.5
                             ELSE 0.0 END)::numeric / COUNT(*), 3
                ) as win_rate_upper,
                -- win_rate_lower: opposite
                ROUND(
                    SUM(CASE WHEN upper_result = -1.0 THEN 1.0
                             WHEN upper_result = -0.5 THEN 0.5
                             ELSE 0.0 END)::numeric / COUNT(*), 3
                ) as win_rate_lower,
                ROUND(AVG(upper_profit)::numeric, 4) as avg_profit,
                ROUND(AVG(lower_profit)::numeric, 4) as avg_profit_lower,
                SUM(CASE WHEN upper_result = 1.0 THEN 1 ELSE 0 END) as upper_win,
                SUM(CASE WHEN upper_result = 0.0 THEN 1 ELSE 0 END) as upper_push,
                SUM(CASE WHEN upper_result = -1.0 THEN 1 ELSE 0 END) as upper_lose,
                ROUND(AVG(handicap)::numeric, 2) as avg_handicap,
                ROUND(AVG(upper_water)::numeric, 3) as avg_water,
                ROUND(AVG(divg)::numeric, 4) as avg_divg
            FROM backtest_samples
            WHERE phase = '{phase}'
            GROUP BY hdp_name, water_bin, divg_bin
            ORDER BY hdp_name, water_bin, divg_bin;
        """)

        phase_lookup = {}
        for row in rows:
            key = f"{row[0]}×{row[1]}×{row[2]}"
            phase_lookup[key] = {
                "win_rate_upper": float(row[4]),
                "win_rate_lower": float(row[5]),
                "sample": int(row[3]),
                "avg_profit": float(row[6]),
                "avg_profit_lower": float(row[7]),
                "upper_win": int(row[8]),
                "upper_push": int(row[9]),
                "upper_lose": int(row[10]),
                "handicap": row[0],
                "water_level": row[1],
                "divg_level": row[2],
                "avg_handicap": float(row[11]),
                "avg_water": float(row[12]),
                "avg_divg": float(row[13]),
            }
        lookup[phase] = phase_lookup

    # Preserve linkage data from existing JSON (used by other analysis)
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            old = json.load(f)
        for key in ['linkage_unchanged', 'linkage_changed']:
            if key in old:
                lookup[key] = old[key]
                print(f"[PRESERVE] Kept {key}: {len(old[key])} entries")
    except Exception as e:
        print(f"[WARN] Could not read old linkage data: {e}")
        lookup['linkage_unchanged'] = {}
        lookup['linkage_changed'] = {}

    # Also keep 'closing' as alias for 'live' (backward compat)
    lookup['closing'] = lookup['live']

    return lookup


def write_json(lookup):
    """Write lookup to JSON file."""
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(lookup, f, ensure_ascii=False, separators=(',', ':'))
    size = os.path.getsize(JSON_PATH)
    print(f"[OUTPUT] JSON written: {JSON_PATH} ({size} bytes)")


def update_html_inline(lookup):
    """Replace inline BACKTEST_WINRATE_LOOKUP in HTML with new data."""
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    # Build the new inline JSON (compact)
    new_json = json.dumps(lookup, ensure_ascii=False, separators=(',', ':'))
    
    # Pattern: const BACKTEST_WINRATE_LOOKUP = {...};
    pattern = r'(const\s+BACKTEST_WINRATE_LOOKUP\s*=\s*)\{.*?\}(\s*;)'
    
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        print("[ERROR] Cannot find inline BACKTEST_WINRATE_LOOKUP in HTML")
        return False

    old_size = len(html)
    new_html = html[:match.start(2)] + new_json + html[match.end(2):]
    # Wait, that's wrong. Let me fix:
    # match.group(1) = "const BACKTEST_WINRATE_LOOKUP = "
    # match.group(2) = ";"
    # We want: group(1) + new_json + group(2)
    new_html = html[:match.start(1)] + match.group(1) + new_json + match.group(2) + html[match.end(2):]
    
    # Backup
    backup_path = HTML_PATH + f'.bak_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[BACKUP] {backup_path}")

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    new_size = len(new_html.encode('utf-8'))
    print(f"[OUTPUT] HTML inline lookup updated: {old_size} → {new_size} bytes")
    return True


# ─── Reporting ────────────────────────────────────────────────────────────────
def report_coverage(lookup):
    """Print coverage statistics."""
    print("\n" + "=" * 70)
    print("COVERAGE REPORT")
    print("=" * 70)
    
    for phase in ['initial', 'live']:
        entries = lookup.get(phase, {})
        total = len(entries)
        if total == 0:
            print(f"\n{phase}: NO ENTRIES")
            continue
        
        sample_counts = [e['sample'] for e in entries.values()]
        ge5 = sum(1 for s in sample_counts if s >= 5)
        ge3 = sum(1 for s in sample_counts if s >= 3)
        ge10 = sum(1 for s in sample_counts if s >= 10)
        total_samples = sum(sample_counts)
        
        print(f"\n{phase.upper()}:")
        print(f"  Total combinations: {total}")
        print(f"  Total samples:      {total_samples}")
        print(f"  sample ≥ 3:         {ge3} ({100*ge3/total:.1f}%)")
        print(f"  sample ≥ 5:         {ge5} ({100*ge5/total:.1f}%)")
        print(f"  sample ≥ 10:        {ge10} ({100*ge10/total:.1f}%)")
        print(f"  Avg sample/combo:   {total_samples/total:.1f}")
        
        # Top 10 by sample
        top = sorted(entries.items(), key=lambda x: -x[1]['sample'])[:10]
        print(f"  Top 10 by sample:")
        for key, e in top:
            wr = e['win_rate_upper'] * 100
            print(f"    {key}: wr={wr:.0f}% n={e['sample']}")

    # Unique handicaps
    for phase in ['initial', 'live']:
        entries = lookup.get(phase, {})
        hdps = set()
        for key in entries:
            parts = key.split('×')
            if parts:
                hdps.add(parts[0])
        print(f"\n{phase} handicaps covered: {len(hdps)}")
        print(f"  {', '.join(sorted(hdps))}")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    incremental = '--update' in sys.argv
    
    print("=" * 70)
    print(f"Backtest {'Incremental Update' if incremental else 'Full Rebuild'}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. Extract constants
    print("\n[1/6] Extracting constants from HTML...")
    coeff_table, hdp_names = extract_js_constants()
    print(f"  COEFF_TABLE: {len(coeff_table)} entries, range {min(coeff_table)}–{max(coeff_table)}")
    print(f"  HDP_NAMES: {len(hdp_names)} entries")

    # 2. Setup DB
    print("\n[2/6] Setting up database...")
    setup_database()

    # 3. For full rebuild, clear existing samples
    if not incremental:
        print("\n[3/6] Clearing existing samples for full rebuild...")
        psql_exec("TRUNCATE backtest_samples RESTART IDENTITY;")
    else:
        print("\n[3/6] Incremental mode — keeping existing samples")

    # 4. Fetch and process
    print("\n[4/6] Fetching match data...")
    raw_rows = fetch_samples(incremental=incremental)
    samples = process_samples(raw_rows, coeff_table, hdp_names)
    print(f"  Processed {len(samples)} valid samples")

    if samples:
        insert_samples(samples)
    elif incremental:
        print("  No new finished matches to process")

    # 5. Aggregate
    print("\n[5/6] Aggregating lookup table...")
    lookup = aggregate_lookup()
    write_json(lookup)
    update_html_inline(lookup)

    # 6. Report
    print("\n[6/6] Coverage report...")
    report_coverage(lookup)

    print("\n" + "=" * 70)
    print("DONE! Hard refresh: Ctrl+Shift+R")
    if not incremental:
        print("\nSet up cron for continuous learning:")
        print("  crontab -e")
        print(f"  0 */2 * * * /usr/bin/python3 {os.path.abspath(__file__)} --update >> /var/log/backtest_update.log 2>&1")
    print("=" * 70)


if __name__ == '__main__':
    main()
