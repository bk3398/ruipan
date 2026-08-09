#!/usr/bin/env python3
"""
赛事同步爬虫 — 轻量级
━━━━━━━━━━━━━━━━━━━━
只抓 bfdata_ut.js，更新赛程/比分/状态，不碰赔率。
1个HTTP请求，2秒内完成。
建议cron: */2 * * * *
"""
import asyncio
import asyncpg
import re
import sys
import os
import logging
from datetime import datetime
from typing import Dict, Optional, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 复用 scraper.py 的解析函数和白名单
from scraper import (
    fetch_all_matches, should_include_match,
    STATUS_MAP, LEAGUE_TIER, EXCLUDE_KEYWORDS,
    convert_to_simplified, safe_int,
)

DSN = 'postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("match_sync")


async def sync_matches(dsn: str, dry_run: bool = False):
    start = datetime.now()
    print(f"\n{'━'*50}")
    print(f"  赛事同步 — {start.strftime('%H:%M:%S')}")
    print(f"{'━'*50}")

    # 1. 抓取bfdata
    from scraper import HttpClient
    http = HttpClient()
    all_matches = fetch_all_matches(http)
    print(f"  bfdata: {len(all_matches)} 场")

    if not all_matches:
        print("  ✗ 获取失败，终止")
        return

    # 2. 过滤
    target = {sid: m for sid, m in all_matches.items()
              if m['status_code'] >= -1 and m['status_code'] < 60}

    filtered = {}
    tier_counts = {1: 0, 2: 0}
    for sid, m in target.items():
        include, tier = should_include_match(m.get('league_name', ''))
        if include:
            filtered[sid] = m
            if tier in tier_counts:
                tier_counts[tier] += 1

    print(f"  白名单内: {len(filtered)} 场 (T1:{tier_counts[1]} T2:{tier_counts[2]})")

    if dry_run:
        # 统计状态分布
        status_dist = {}
        for m in filtered.values():
            st = STATUS_MAP.get(m['status_code'], f"code_{m['status_code']}")
            status_dist[st] = status_dist.get(st, 0) + 1
        for st, cnt in sorted(status_dist.items()):
            print(f"    {st}: {cnt}")
        print(f"\n  [DRY-RUN] 不写DB，耗时{(datetime.now()-start).total_seconds():.1f}s")
        return

    # 3. 写入PostgreSQL
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=5)
    new_count = 0
    update_count = 0
    current_sids = [int(s) for s in filtered.keys()]

    try:
        async with pool.acquire() as conn:
            for sid, m in filtered.items():
                league = m['league_name']
                home = m['home_team']
                away = m['away_team']
                status = STATUS_MAP.get(m['status_code'], 'unknown')
                match_time_str = m.get('match_time', '')

                if not match_time_str:
                    continue

                try:
                    match_time = datetime.strptime(match_time_str[:16], '%Y-%m-%d %H:%M')
                except ValueError:
                    match_time = datetime.now()

                # season
                if match_time.month >= 8:
                    season = f"{match_time.year}-{match_time.year+1}"
                else:
                    season = f"{match_time.year-1}-{match_time.year}"

                existing = await conn.fetchrow(
                    "SELECT status, home_score, away_score FROM matches WHERE match_id=$1",
                    sid
                )

                if existing:
                    if (existing['status'] != status or
                        existing['home_score'] != m['home_score'] or
                        existing['away_score'] != m['away_score']):
                        await conn.execute(
                            """UPDATE matches SET league=$2, home_team=$3, away_team=$4,
                               match_time=$5, status=$6, home_score=$7, away_score=$8,
                               home_ht_score=$9, away_ht_score=$10,
                               season=COALESCE($11, season)
                               WHERE match_id=$1""",
                            sid, league, home, away, match_time, status,
                            m['home_score'], m['away_score'],
                            m.get('home_ht_score'), m.get('away_ht_score'),
                            season
                        )
                        update_count += 1
                    else:
                        # 名字可能变了
                        await conn.execute(
                            """UPDATE matches SET league=$2, home_team=$3, away_team=$4,
                               match_time=$5, season=COALESCE($6, season)
                               WHERE match_id=$1 AND (league != $2 OR home_team != $3 OR away_team != $4)""",
                            sid, league, home, away, match_time, season
                        )
                else:
                    await conn.execute(
                        """INSERT INTO matches (match_id, league, home_team, away_team,
                           match_time, status, home_score, away_score,
                           home_ht_score, away_ht_score, season)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
                        sid, league, home, away, match_time, status,
                        m['home_score'], m['away_score'],
                        m.get('home_ht_score'), m.get('away_ht_score'), season
                    )
                    new_count += 1

        # 4. 收尾：bfdata 即时接口完场后不再返回比赛。
        #    (a) 之前是 live 但已不在 bfdata 返回中 -> 立即标记 finished（不等时间阈值）
        #    (b) 有比分但停留在 scheduled/not_started 超过 2h15min（含补时）-> finished
        stale_finished = 0
        try:
            async with pool.acquire() as conn:
                # (a) 之前 live 但本轮 bfdata 未返回（完场即消失）
                if current_sids:
                    result = await conn.execute(
                        """UPDATE matches
                           SET status = 'finished'
                           WHERE status = 'live'
                             AND match_id != ALL($1::bigint[])""",
                        current_sids
                    )
                    parts = result.split()
                    if len(parts) >= 2 and parts[-1].isdigit():
                        stale_finished += int(parts[-1])

                # (b) 有比分但状态停留在 scheduled/not_started 超过 2h15min
                result = await conn.execute(
                    """UPDATE matches
                       SET status = 'finished'
                       WHERE status IN ('scheduled', 'not_started')
                         AND match_time < NOW() - INTERVAL '2 hours 15 minutes'
                         AND (home_score IS NOT NULL OR away_score IS NOT NULL)"""
                )
                parts = result.split()
                if len(parts) >= 2 and parts[-1].isdigit():
                    stale_finished += int(parts[-1])
        except Exception as e:
            print(f"  ⚠️ stale收尾失败: {e}")
    finally:
        await pool.close()

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n  ✅ 完成 — {elapsed:.1f}s")
    print(f"  新增: {new_count} | 更新: {update_count} | stale收尾: {stale_finished}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    asyncio.run(sync_matches(DSN, dry_run=args.dry_run))
