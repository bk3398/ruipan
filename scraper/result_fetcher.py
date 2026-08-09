#!/usr/bin/env python3
"""
完场赛果修正器 — result_fetcher.py

问题：bfdata_ut.js 即时接口不返回已完场多时的比赛，导致这些比赛：
  1. status 可能停留在 live/scheduled（stale收尾会改成finished但比分冻结）
  2. 比分停留在某个中间值（如2-0而实际2-2）

方案：调用 ChangeDate.ashx 获取指定日期的全量比赛（含真实完场比分），
     将 matches 表中状态不对或比分不对的记录修正为 finished + 正确比分。

数据源: POST https://m.titan007.com/ChangeDate.ashx
        data: {date: YYYY-MM-DD, kind:0, type:0}
        返回: match_data$$$$league_data
        match_data 按 ! 分隔每场，^ 分隔字段
        字段: [0]=sid [1]=league_id [2]=status [3]=datetime(YYYYMMDDHHmmss)
              [5]=home [6]=away [7]=home_score [8]=away_score

运行频率：每30分钟（cron），检查今天和昨天
"""

import asyncio
import asyncpg
import logging
import sys
import os
from datetime import datetime, timedelta
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("result_fetcher")

DB_URL = "postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan"
CHANGE_DATE_URL = "https://m.titan007.com/ChangeDate.ashx"
UA = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"

# ChangeDate status_code: -1=完场, -10/-11/-14=取消/延期
FINISHED_CODES = {-1}
CANCELLED_CODES = {-10, -11, -14}


def http_post(url: str, data: str, timeout: int = 15) -> str:
    req = urlrequest.Request(
        url,
        data=data.encode("utf-8"),
        headers={
            "User-Agent": UA,
            "Referer": "https://m.titan007.com/",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_results(date_str: str) -> dict:
    """获取指定日期的完场比分，返回 {sid: (status, home_score, away_score)}"""
    try:
        raw = http_post(CHANGE_DATE_URL, f"date={date_str}&kind=0&type=0")
    except (URLError, HTTPError, OSError) as e:
        logger.error("ChangeDate fetch failed for %s: %s", date_str, e)
        return {}

    parts = raw.split("$$$$")
    if not parts or not parts[0] or len(parts[0]) < 10:
        return {}

    results = {}
    for line in parts[0].split("!"):
        f = line.split("^")
        if len(f) < 9:
            continue
        sid = f[0]
        status_code = int(f[2]) if f[2].lstrip("-").isdigit() else 0
        try:
            hs = int(f[7]) if f[7] else 0
            aws = int(f[8]) if f[8] else 0
        except (ValueError, IndexError):
            hs, aws = 0, 0

        if status_code in FINISHED_CODES:
            results[sid] = ("finished", hs, aws)
        elif status_code in CANCELLED_CODES:
            results[sid] = ("cancelled", hs, aws)

    return results


async def sync_results(pool, date_str: str) -> dict:
    """用ChangeDate数据修正DB中的比赛状态和比分"""
    results = fetch_results(date_str)
    if not results:
        return {"checked": 0, "updated": 0, "cancelled": 0}

    updated = 0
    cancelled = 0
    checked = 0

    # 只修正白名单内的比赛（通过match_id匹配）
    sids = list(results.keys())
    # 分批查询，避免IN列表过长
    batch_size = 200
    for i in range(0, len(sids), batch_size):
        batch = sids[i : i + batch_size]
        rows = await pool.fetch(
            "SELECT match_id, status, home_score, away_score FROM matches WHERE match_id = ANY($1)",
            batch,
        )
        row_map = {str(r["match_id"]): r for r in rows}

        for sid in batch:
            if sid not in row_map:
                continue
            checked += 1
            row = row_map[sid]
            new_status, new_hs, new_as = results[sid]

            # 只在状态或比分确实不同时更新
            if (
                row["status"] != new_status
                or row["home_score"] != new_hs
                or row["away_score"] != new_as
            ):
                await pool.execute(
                    """UPDATE matches
                       SET status=$2, home_score=$3, away_score=$4
                       WHERE match_id=$1""",
                    sid,
                    new_status,
                    new_hs,
                    new_as,
                )
                if new_status == "cancelled":
                    cancelled += 1
                else:
                    updated += 1

    return {"checked": checked, "updated": updated, "cancelled": cancelled, "total": len(results)}


async def main():
    now = datetime.now()
    # 检查昨天和今天
    dates = [
        (now - timedelta(days=1)).strftime("%Y-%m-%d"),
        now.strftime("%Y-%m-%d"),
    ]

    logger.info("=" * 60)
    logger.info("完场赛果修正 — %s", now.strftime("%H:%M:%S"))

    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
    try:
        total_updated = 0
        total_cancelled = 0
        for ds in dates:
            r = await sync_results(pool, ds)
            logger.info(
                "  %s: ChangeDate=%d场, 白名单命中=%d, 修正比分/状态=%d, 取消=%d",
                ds,
                r.get("total", 0),
                r["checked"],
                r["updated"],
                r["cancelled"],
            )
            total_updated += r["updated"]
            total_cancelled += r["cancelled"]
        logger.info("  合计修正: %d场, 取消: %d场", total_updated, total_cancelled)
    finally:
        await pool.close()

    logger.info("Done")


if __name__ == "__main__":
    asyncio.run(main())
