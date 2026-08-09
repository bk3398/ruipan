#!/usr/bin/env python3
"""
基本面数据采集器 - 从球探分析页抓取真实近期战绩/H2H/积分榜

数据源: https://zq.titan007.com/analysis/{sid}.htm
解析:
  - h_data / a_data: 主队/客队近期全部比赛
  - h2_data / a2_data: 主队主场/客队客场近期比赛
  - v_data: 两队历史交锋H2H
  - HTML表格: 球队总/主/客/近6统计(排名/积分/胜率)
  - 进球排行: homeScoreStr/guestScoreStr/totalScoreStr

写入: team_fundamentals 表 (JSON存储)
"""

import json
import logging
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_URL = "postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
ANALYSIS_URL = "https://zq.titan007.com/analysis/{sid}.htm"
REFRESH_HOURS = 12          # re-fetch if data older than this
BATCH_LIMIT = 200           # max matches per run
REQUEST_DELAY = 1.5         # seconds between requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fundamental")


# ---------------------------------------------------------------------------
# Traditional Chinese -> Simplified
# ---------------------------------------------------------------------------
try:
    import opencc
    _t2s = opencc.OpenCC('t2s')
    def t2s(text):
        return _t2s.convert(text) if text else text
except ImportError:
    # Fallback: strip HTML tags, keep traditional
    def t2s(text):
        return text


def clean_team_name(raw):
    """Remove HTML tags from team name in data arrays."""
    if not raw:
        return ""
    # Remove span tags
    text = re.sub(r'<[^>]+>', '', raw)
    return t2s(text.strip())


def extract_rank_from_span(raw):
    """Extract rank number from span title like '<span title="Team Name 排名:5">Team</span>'."""
    m = re.search(r'排名[：:]\s*(\d+)', raw)
    if m:
        return int(m.group(1))
    m = re.search(r'排名[：:]\s*([^\s<"]+)', raw)
    if m:
        val = m.group(1)
        try:
            return int(val)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Page fetch & parse
# ---------------------------------------------------------------------------
def fetch_analysis(sid):
    """Fetch and return analysis page HTML."""
    url = ANALYSIS_URL.format(sid=sid)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.titan007.com/",
    })
    resp = urllib.request.urlopen(req, timeout=15)
    return resp.read().decode("utf-8", errors="replace")


def parse_js_array(html, varname):
    """Extract a JS array variable and evaluate it safely."""
    pattern = r'var\s+' + varname + r'\s*=\s*(\[.*?\]);'
    m = re.search(pattern, html, re.DOTALL)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        # JS arrays are mostly JSON-compatible, but may have unquoted keys
        # Use json after cleaning
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try with ast.literal_eval after replacing single quotes
        try:
            import ast
            return ast.literal_eval(raw)
        except Exception:
            log.warning("Failed to parse %s", varname)
            return None


def parse_match_record(rec):
    """
    Parse a match record from h_data/a_data/etc.
    Format:
      [date, league_id, league_name, color, home_id, home_name,
       away_id, away_name, home_score, away_score, half_score,
       handicap, ?, ?, result_flag, match_id, pos1, pos2, league_url, ?, ?, ?]
    """
    if not rec or len(rec) < 16:
        return None
    try:
        date_str = str(rec[0])  # "26-08-02"
        home_score = rec[8] if len(rec) > 8 else None
        away_score = rec[9] if len(rec) > 9 else None
        half_score = rec[10] if len(rec) > 10 else ""
        handicap = rec[11] if len(rec) > 11 else ""
        result_flag = rec[14] if len(rec) > 14 else None
        match_id = rec[15] if len(rec) > 15 else None

        return {
            "date": "20" + date_str if len(date_str) == 8 else date_str,
            "league_id": rec[1],
            "league": t2s(rec[2]) if rec[2] else "",
            "home_id": rec[4],
            "home_team": clean_team_name(str(rec[5])) if rec[5] else "",
            "away_id": rec[6],
            "away_team": clean_team_name(str(rec[7])) if rec[7] else "",
            "home_score": home_score if isinstance(home_score, int) else None,
            "away_score": away_score if isinstance(away_score, int) else None,
            "half_score": str(half_score) if half_score else "",
            "handicap": str(handicap) if handicap else "",
            "result_flag": result_flag,
            "match_id": match_id,
        }
    except (IndexError, TypeError) as e:
        log.debug("parse error: %s in %s", e, rec)
        return None


def parse_h2h_record(rec):
    """Parse H2H record from v_data (fewer trailing fields)."""
    if not rec or len(rec) < 16:
        return None
    try:
        date_str = str(rec[0])
        return {
            "date": "20" + date_str if len(date_str) == 8 else date_str,
            "league": t2s(rec[2]) if rec[2] else "",
            "home_team": clean_team_name(str(rec[5])) if rec[5] else "",
            "away_team": clean_team_name(str(rec[7])) if rec[7] else "",
            "home_score": rec[8] if isinstance(rec[8], int) else None,
            "away_score": rec[9] if isinstance(rec[9], int) else None,
            "half_score": str(rec[10]) if rec[10] else "",
            "match_id": rec[15] if len(rec) > 15 else None,
        }
    except (IndexError, TypeError):
        return None


def parse_team_stats_tables(html, home_team, away_team):
    """
    Parse the team statistics tables from HTML.
    Each team has 4 rows: 總(all), 主(home), 客(away), 近6(recent6)
    Columns: 賽 勝 平 負 得 失 凈 積分 排名 勝率
    """
    stats = {}

    # Find all tables in the page
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    for table_html in tables:
        text = re.sub(r'<[^>]+>', '|', table_html)
        text = re.sub(r'\|+', '|', text)
        cells = [c.strip() for c in text.split('|') if c.strip()]

        # Look for pattern: [league-pos]TeamName then stat rows
        # Find team name and following numbers
        for team_label in [home_team, away_team]:
            # Try simplified and traditional variants
            for name_variant in set([team_label, t2s(team_label)]):
                if not name_variant or len(name_variant) < 2:
                    continue
                for i, cell in enumerate(cells):
                    if name_variant in cell:
                        # Next cells should have 賽 勝 平 負 得 失 凈 積分 排名 勝率 labels
                        # followed by values in groups
                        vals = []
                        j = i + 1
                        while j < len(cells) and len(vals) < 50:
                            c = cells[j]
                            # Skip header labels
                            if c in ('總', '主', '客', '近6', '全場', '賽', '勝', '平', '負',
                                     '得', '失', '凈', '積分', '排名', '勝率', ''):
                                j += 1
                                continue
                            vals.append(c)
                            j += 1

                        # Parse numeric values into structured rows
                        if len(vals) >= 10:
                            team_stats = parse_stat_values(vals)
                            if team_stats:
                                stats[team_label] = team_stats
                        break
    return stats


def parse_stat_values(vals):
    """Parse flat stat values into structured dict."""
    result = {}
    labels = ['played', 'won', 'drawn', 'lost', 'gf', 'ga', 'gd', 'points', 'rank']
    sections = {'overall': None, 'home': None, 'away': None, 'recent6': None}

    # Values come in groups after section labels (總/主/客/近6)
    # Try to extract numeric groups
    numeric_vals = []
    for v in vals:
        v = v.replace('%', '').replace(',', '').strip()
        try:
            numeric_vals.append(float(v) if '.' in v else int(v))
        except ValueError:
            continue

    # Expect 4 sections x (9 stats + winrate) = ~40 values
    if len(numeric_vals) >= 36:
        idx = 0
        for section in ['overall', 'home', 'away', 'recent6']:
            if idx + 9 <= len(numeric_vals):
                row = {}
                for k, label in enumerate(labels):
                    row[label] = numeric_vals[idx + k]
                # Win rate (percentage)
                if idx + 9 < len(numeric_vals):
                    row['win_rate'] = numeric_vals[idx + 9] / 100.0 if numeric_vals[idx + 9] > 1 else numeric_vals[idx + 9]
                sections[section] = row
                idx += 10  # 9 stats + winrate
            else:
                break
        return sections
    return None


def try_fetch_standings(league_id):
    """Try to fetch full league standings from titan007."""
    urls = [
        f"https://zq.titan007.com/analysis/integral_{league_id}.js",
        f"https://data.titan007.com/js/integral_{league_id}.js",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://zq.titan007.com/",
            })
            resp = urllib.request.urlopen(req, timeout=8)
            content = resp.read().decode("utf-8", errors="replace")
            if content and len(content) > 50:
                log.info("Standings found at %s (%d chars)", url, len(content))
                return parse_standings_js(content)
        except Exception:
            continue
    return None


def parse_standings_js(content):
    """Parse standings JS data into structured list."""
    # Try to find array of arrays
    m = re.search(r'(\[\[.*?\]\])', content, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        standings = []
        for row in data:
            if isinstance(row, list) and len(row) >= 4:
                standings.append({
                    "position": row[0],
                    "team_id": row[1],
                    "team": clean_team_name(str(row[2])),
                    "value": row[3] if len(row) > 3 else None,
                })
        return standings if standings else None
    except Exception:
        return None


def parse_analysis_page(html, sid):
    """Main parser: extract all fundamental data from analysis page."""
    result = {
        "match_id": int(sid),
        "fetched_at": datetime.now().isoformat(),
        "home_recent": [],
        "away_recent": [],
        "home_home_recent": [],
        "away_away_recent": [],
        "h2h": [],
        "team_stats": {},
        "league_table": None,
    }

    # 1. Recent matches
    for varname, key in [
        ("h_data", "home_recent"),
        ("a_data", "away_recent"),
        ("h2_data", "home_home_recent"),
        ("a2_data", "away_away_recent"),
    ]:
        data = parse_js_array(html, varname)
        if data:
            records = []
            for rec in data:
                parsed = parse_match_record(rec)
                if parsed:
                    records.append(parsed)
            result[key] = records[:20]  # cap at 20
            log.info("  %s: %d records", varname, len(records))

    # 2. H2H
    v_data = parse_js_array(html, "v_data")
    if v_data:
        h2h_records = []
        for rec in v_data:
            parsed = parse_h2h_record(rec)
            if parsed:
                h2h_records.append(parsed)
        result["h2h"] = h2h_records[:20]
        log.info("  v_data (H2H): %d records", len(h2h_records))

    # 3. Team names from page
    home_team = ""
    away_team = ""
    ht_m = re.search(r'var\s+hometeam\s*=\s*["\']([^"\']+)["\']', html)
    at_m = re.search(r'var\s+guestteam\s*=\s*["\']([^"\']+)["\']', html)
    if ht_m:
        home_team = t2s(ht_m.group(1))
    if at_m:
        away_team = t2s(at_m.group(1))

    result["home_team"] = home_team
    result["away_team"] = away_team

    # 4. League info
    league_id = None
    lid_m = re.search(r'subleague\.aspx\?sclassid=(\d+)', html)
    if lid_m:
        league_id = int(lid_m.group(1))
    result["league_id"] = league_id

    # 5. Team stats from HTML tables
    if home_team and away_team:
        result["team_stats"] = parse_team_stats_tables(html, home_team, away_team)

    # 6. Try fetching full league standings
    if league_id:
        standings = try_fetch_standings(league_id)
        if standings:
            result["league_table"] = standings
            log.info("  league_table: %d teams", len(standings))

    return result


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_db():
    return psycopg2.connect(DB_URL)


def ensure_table(conn):
    """Create team_fundamentals table if not exists."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS team_fundamentals (
                match_id BIGINT PRIMARY KEY,
                home_team VARCHAR(128),
                away_team VARCHAR(128),
                league_id INTEGER,
                data JSONB NOT NULL,
                fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fundamentals_league
            ON team_fundamentals(league_id);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fundamentals_updated
            ON team_fundamentals(updated_at);
        """)
        conn.commit()


def get_matches_to_fetch(conn, limit=BATCH_LIMIT):
    """Get scheduled/live matches that need fundamental data."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cutoff = datetime.now() - timedelta(hours=REFRESH_HOURS)
        cur.execute("""
            SELECT m.match_id, m.home_team, m.away_team, m.league_id,
                   m.match_time, m.status
            FROM matches m
            LEFT JOIN team_fundamentals tf ON m.match_id = tf.match_id
            WHERE m.status IN ('scheduled', 'live')
              AND m.match_time >= NOW() - INTERVAL '6 hours'
              AND m.match_time <= NOW() + INTERVAL '48 hours'
              AND (tf.match_id IS NULL OR tf.updated_at < %s)
            ORDER BY m.match_time ASC
            LIMIT %s
        """, (cutoff, limit))
        return cur.fetchall()


def save_fundamentals(conn, data):
    """Upsert fundamental data."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO team_fundamentals
                (match_id, home_team, away_team, league_id, data, fetched_at, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, NOW(), NOW())
            ON CONFLICT (match_id) DO UPDATE SET
                home_team = EXCLUDED.home_team,
                away_team = EXCLUDED.away_team,
                league_id = EXCLUDED.league_id,
                data = EXCLUDED.data,
                updated_at = NOW()
        """, (
            data["match_id"],
            data.get("home_team", ""),
            data.get("away_team", ""),
            data.get("league_id"),
            json.dumps(data, ensure_ascii=False),
        ))
        conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="基本面数据采集器")
    parser.add_argument("--sid", type=str, help="Fetch single match by SID")
    parser.add_argument("--limit", type=int, default=BATCH_LIMIT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("基本面数据采集 — %s", datetime.now().strftime("%Y-%m-%d %H:%M"))

    conn = get_db()
    ensure_table(conn)

    if args.sid:
        # Single match mode
        log.info("Fetching single match: %s", args.sid)
        html = fetch_analysis(args.sid)
        data = parse_analysis_page(html, args.sid)
        log.info("Parsed: home_recent=%d, away_recent=%d, h2h=%d, stats_teams=%d",
                 len(data["home_recent"]), len(data["away_recent"]),
                 len(data["h2h"]), len(data["team_stats"]))
        if not args.dry_run:
            save_fundamentals(conn, data)
            log.info("Saved to DB.")
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
        conn.close()
        return

    # Batch mode
    matches = get_matches_to_fetch(conn, args.limit)
    log.info("Need to fetch: %d matches", len(matches))

    ok = 0
    fail = 0
    for i, m in enumerate(matches):
        sid = str(m["match_id"])
        try:
            log.info("[%d/%d] SID=%s %s vs %s",
                     i + 1, len(matches), sid,
                     m.get("home_team", ""), m.get("away_team", ""))
            html = fetch_analysis(sid)
            data = parse_analysis_page(html, sid)

            # Use team names from DB if parser didn't find them
            if not data.get("home_team") and m.get("home_team"):
                data["home_team"] = m["home_team"]
            if not data.get("away_team") and m.get("away_team"):
                data["away_team"] = m["away_team"]
            if not data.get("league_id") and m.get("league_id"):
                data["league_id"] = m["league_id"]

            save_fundamentals(conn, data)
            ok += 1
            log.info("  OK: home=%d away=%d h2h=%d stats=%d table=%s",
                     len(data["home_recent"]), len(data["away_recent"]),
                     len(data["h2h"]), len(data["team_stats"]),
                     "yes" if data.get("league_table") else "no")
        except Exception as e:
            log.error("  FAIL SID=%s: %s", sid, e)
            fail += 1

        time.sleep(REQUEST_DELAY)

    conn.close()
    log.info("Done: %d ok, %d failed", ok, fail)


if __name__ == "__main__":
    main()
