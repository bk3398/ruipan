#!/usr/bin/env python3
"""
import_kline_results.py — VPS端只读导入器
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
将沙箱算好的K线/形态/球队状态JSON写入VPS缓存表。
本文件不含任何算法，只做数据写入。

用法:
  python3 import_kline_results.py kline_results.json
  python3 import_kline_results.py team_form.json
  python3 import_kline_results.py --all /opt/ruipan/data/
"""

import asyncio
import json
import sys
import os
import logging

import asyncpg

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

DSN = "postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan"


async def import_klines(conn, data):
    """导入K线缓存"""
    rows = data.get('kline_cache', [])
    count = 0
    for r in rows:
        try:
            await conn.execute("""
                INSERT INTO kline_cache
                    (match_id, kline_type, window_minutes, bucket_time,
                     open, high, low, close, volume)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (match_id, kline_type, window_minutes, bucket_time)
                DO UPDATE SET open=$5, high=$6, low=$7, close=$8, volume=$9,
                              aggregated_at=NOW()
            """, r['match_id'], r['kline_type'], r['window_minutes'],
                r['bucket_time'], r['open'], r['high'], r['low'],
                r['close'], r.get('volume', 0))
            count += 1
        except Exception as e:
            logger.warning(f"kline row error: {e}")
    logger.info(f"  kline_cache: {count} rows")
    return count


async def import_patterns(conn, data):
    """导入形态特征"""
    rows = data.get('patterns', [])
    count = 0
    for r in rows:
        try:
            labeled = r.get('labeled', False)
            await conn.execute("""
                INSERT INTO pattern_library
                    (pattern_type, match_id, bookmaker, features,
                     home_score, away_score, handicap_result, total_goals,
                     confidence, labeled_at)
                VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,$8,$9,
                        CASE WHEN $10 THEN NOW() ELSE NULL END)
                ON CONFLICT (pattern_type, match_id, bookmaker)
                DO UPDATE SET features=$4::jsonb, home_score=$5, away_score=$6,
                              handicap_result=$7, total_goals=$8,
                              labeled_at=CASE WHEN $10 THEN NOW() ELSE NULL END
            """, r['pattern_type'], r['match_id'], r.get('bookmaker', 'market'),
                json.dumps(r['features']),
                r.get('home_score'), r.get('away_score'),
                r.get('handicap_result'), r.get('total_goals'),
                0.5, labeled)
            count += 1
        except Exception as e:
            logger.warning(f"pattern row error: {e}")
    logger.info(f"  pattern_library: {count} rows")
    return count


async def import_team_form(conn, data):
    """导入球队状态"""
    rows = data.get('team_form', data if isinstance(data, list) else [])
    count = 0
    for r in rows:
        try:
            await conn.execute("""
                INSERT INTO team_form_timeline
                    (team_name, league, season, match_id, match_date,
                     is_home, opponent, goals_for, goals_against, result,
                     cumulative_points, points_per_game, form_ema,
                     rolling_gf, rolling_ga, rolling_gd, rolling_win_rate,
                     attack_strength, defense_strength, home_away_form)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
                ON CONFLICT (team_name, match_id, home_away_form)
                DO UPDATE SET cumulative_points=$11, points_per_game=$12,
                    form_ema=$13, rolling_gf=$14, rolling_ga=$15,
                    rolling_gd=$16, rolling_win_rate=$17,
                    attack_strength=$18, defense_strength=$19
            """, r['team_name'], r.get('league'), r.get('season'),
                r['match_id'], r['match_date'], r['is_home'],
                r.get('opponent'), r['gf'], r['ga'], r['result'],
                r['cumulative_points'], r['points_per_game'], r['form_ema'],
                r['rolling_gf'], r['rolling_ga'], r['rolling_gd'],
                r['rolling_win_rate'], r['attack_strength'],
                r['defense_strength'], r['home_away_form'])
            count += 1
        except Exception as e:
            logger.warning(f"team_form row error: {e}")
    logger.info(f"  team_form_timeline: {count} rows")
    return count


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    conn = await asyncpg.connect(DSN)
    try:
        args = sys.argv[1:]

        if args[0] == '--all':
            data_dir = args[1] if len(args) > 1 else '/opt/ruipan/data'
            for fname in os.listdir(data_dir):
                fpath = os.path.join(data_dir, fname)
                if fname.endswith('.json'):
                    logger.info(f"Importing {fname}...")
                    with open(fpath, 'r') as f:
                        data = json.load(f)
                    if 'kline_cache' in data:
                        await import_klines(conn, data)
                        await import_patterns(conn, data)
                    elif 'team_form' in data or isinstance(data, list):
                        await import_team_form(conn, data)
        else:
            fpath = args[0]
            with open(fpath, 'r') as f:
                data = json.load(f)

            if 'kline_cache' in data:
                await import_klines(conn, data)
                await import_patterns(conn, data)
                if 'stats' in data:
                    logger.info(f"Stats: {json.dumps(data['stats'], indent=2)}")
            elif 'team_form' in data or isinstance(data, list):
                await import_team_form(conn, data)
            else:
                logger.warning("Unknown data format")
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
