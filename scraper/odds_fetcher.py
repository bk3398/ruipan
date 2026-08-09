#!/usr/bin/env python3
"""
赔率抓取爬虫 — 并发版
━━━━━━━━━━━━━━━━━━━━
只负责赔率抓取，不做赛事同步。
- aiohttp并发抓取（默认8并发）
- 优先级：走地中 > 赛前3小时内 > 其他
- 每场只抓亚盘+欧赔2个请求
- 跳过已完赛超过2小时的比赛（赔率已锁定）
建议cron: */10 * * * *
"""
import asyncio
import aiohttp
import asyncpg
import re
import sys
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import (
    should_include_match, STATUS_MAP,
    COMPANY_MAP, EURO_COMPANY_MAP,
    safe_float,
)

DSN = 'postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("odds_fetcher")

CONCURRENCY = 4
REQUEST_TIMEOUT = 15
PRE_MATCH_WINDOW_HOURS = 6  # 赛前6小时内开始抓赔率
FINISHED_GRACE_HOURS = 2    # 完赛后2小时内仍抓（终盘修正）

# ── 亚盘解析 ──────────────────────────────────────────────────────

def _build_asian_entry(company_id: str, init_data: dict, live_data: dict) -> Optional[dict]:
    try:
        init_hcp = float(init_data['handicap'])
        init_upper = float(init_data['upper'])
        init_lower = float(init_data['lower'])
        live_hcp = float(live_data.get('handicap', init_hcp))
        live_upper = float(live_data.get('upper', init_upper))
        live_lower = float(live_data.get('lower', init_lower))
    except (KeyError, ValueError, TypeError):
        return None

    if init_hcp < 0:
        init_upper, init_lower = init_lower, init_upper
        live_upper, live_lower = live_lower, live_upper

    return {
        'company_id': company_id,
        'init_upper': init_upper, 'init_handicap': init_hcp, 'init_lower': init_lower,
        'live_upper': live_upper, 'live_handicap': live_hcp, 'live_lower': live_lower,
    }


def parse_vip_asian(html: str) -> List[Dict]:
    if not html or len(html) < 500:
        return []

    odds_start = html.find('id="odds"')
    if odds_start < 0:
        odds_start = html.find("id='odds'")
    if odds_start < 0:
        return []

    table_start = html.rfind('<table', 0, odds_start)
    if table_start < 0:
        return []

    snippet = html[table_start:table_start + 100000]
    results = []
    tr_pattern = re.compile(r'<tr([^>]*)>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    td_pattern = re.compile(r'<td([^>]*)>(.*?)</td>', re.DOTALL | re.IGNORECASE)

    current_company = None
    current_init = None
    current_live = None

    for tr_match in tr_pattern.finditer(snippet):
        tr_attrs = tr_match.group(1)
        tr_content = tr_match.group(2)

        if "display: none" in tr_attrs or "display:none" in tr_attrs:
            continue
        if '<th' in tr_content:
            continue
        if 'goals=' not in tr_content and 'oddstype=' not in tr_content:
            continue

        cid_match = re.search(r'data-id=["\'](\d+)["\']', tr_content)
        if not cid_match:
            cid_match = re.search(r"companyID\s*=\s*['\"]?(\d+)", tr_content)
        if not cid_match:
            cid_match = re.search(r'companyID=(\d+)', tr_content)
        if not cid_match:
            cid_match = re.search(r'companyid=(\d+)', tr_content, re.IGNORECASE)

        if cid_match:
            new_company = cid_match.group(1)
            if current_company and current_company != new_company:
                if current_company in COMPANY_MAP and current_init and current_live:
                    entry = _build_asian_entry(current_company, current_init, current_live)
                    if entry:
                        results.append(entry)
                current_init = None
                current_live = None
            current_company = new_company

        for td_attrs, td_content in td_pattern.findall(tr_content):
            goals_m = re.search(r'goals\s*=\s*["\']?(-?[\d.]+)', td_attrs)
            odds_type_m = re.search(r'oddstype\s*=\s*["\'](\w+)', td_attrs)
            title_m = re.search(r'title\s*=\s*["\']([^"\']+)', td_attrs)
            text = re.sub(r'<[^>]+>', '', td_content).strip()
            number = safe_float(text)

            if title_m and goals_m:
                current_init = current_init or {}
                current_init['handicap'] = float(goals_m.group(1))
            elif title_m and number is not None and 'oddstype' not in td_attrs:
                if current_init is None:
                    current_init = {}
                if 'upper' not in current_init:
                    current_init['upper'] = number
                elif 'lower' not in current_init:
                    current_init['lower'] = number
            elif odds_type_m and odds_type_m.group(1) == 'wholeLastOdds':
                if current_live is None:
                    current_live = {}
                if goals_m:
                    current_live['handicap'] = float(goals_m.group(1))
                elif number is not None:
                    if 'upper' not in current_live:
                        current_live['upper'] = number
                    elif 'lower' not in current_live:
                        current_live['lower'] = number

    if current_company and current_company in COMPANY_MAP and current_init and current_live:
        entry = _build_asian_entry(current_company, current_init, current_live)
        if entry:
            results.append(entry)

    return results


def parse_1x2d_euro(js: str) -> List[Dict]:
    if not js or len(js) < 100:
        return []

    results = []
    game_start = js.find('game=Array')
    if game_start < 0:
        game_start = js.find('var game')
    if game_start < 0:
        return []

    game_section = js[game_start:]
    arr_end = game_section.find(');')
    if arr_end > 0:
        game_section = game_section[:arr_end]

    for item in re.findall(r'"([^"]+)"', game_section):
        fields = item.split('|')
        if len(fields) < 13:
            continue
        company_id = fields[0]
        if company_id not in EURO_COMPANY_MAP:
            continue
        init_h = safe_float(fields[3])
        init_d = safe_float(fields[4])
        init_a = safe_float(fields[5])
        live_h = safe_float(fields[10])
        live_d = safe_float(fields[11])
        live_a = safe_float(fields[12])

        if init_h and init_d and init_a:
            results.append({
                'company_id': company_id,
                'init_h': init_h, 'init_d': init_d, 'init_a': init_a,
                'live_h': live_h or init_h, 'live_d': live_d or init_d, 'live_a': live_a or init_a,
            })

    return results


# ── 异步抓取 ──────────────────────────────────────────────────────

async def fetch_url(session: aiohttp.ClientSession, url: str, referer: str = None) -> Optional[str]:
    if 'vip.titan007.com' in url:
        ref = referer or 'https://vip.titan007.com/'
    elif '1x2d.titan007.com' in url:
        ref = referer or 'https://www.titan007.com/'
    else:
        ref = referer or 'https://www.titan007.com/'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'identity',
        'Referer': ref,
        'Connection': 'keep-alive',
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            if resp.status == 200:
                return await resp.text(encoding='utf-8', errors='replace')
            else:
                logger.debug("fetch %s -> HTTP %s", url[:60], resp.status)
    except Exception as e:
        logger.debug("fetch %s failed: %s", url[:60], e)
    return None


async def fetch_match_odds(session: aiohttp.ClientSession, sid: str) -> Tuple[List[Dict], List[Dict]]:
    """并发抓取同一场比赛的亚盘+欧赔"""
    asian_url = f"https://vip.titan007.com/AsianOdds_n.aspx?id={sid}"
    euro_url = f"https://1x2d.titan007.com/{sid}.js"

    asian_html, euro_js = await asyncio.gather(
        fetch_url(session, asian_url, referer=f"https://vip.titan007.com/AsianOdds_n.aspx?id={sid}"),
        fetch_url(session, euro_url, referer=f"https://1x2d.titan007.com/{sid}.js"),
        return_exceptions=True
    )

    asian_data = parse_vip_asian(asian_html) if isinstance(asian_html, str) else []
    euro_data = parse_1x2d_euro(euro_js) if isinstance(euro_js, str) else []

    return asian_data, euro_data


# ── DB写入 ────────────────────────────────────────────────────────

async def _upsert_asian(conn, sid: str, bk: str, hcp: float, up: float, low: float, phase: str):
    existing = await conn.fetchrow(
        "SELECT id FROM odds_asia WHERE match_id=$1 AND bookmaker=$2 AND odds_type=$3",
        sid, bk, phase
    )
    if existing:
        await conn.execute(
            "UPDATE odds_asia SET handicap=$2, home_odds=$3, away_odds=$4 WHERE id=$1",
            existing['id'], hcp, up, low
        )
    else:
        await conn.execute(
            "INSERT INTO odds_asia (match_id, bookmaker, handicap, home_odds, away_odds, odds_type) VALUES ($1,$2,$3,$4,$5,$6)",
            sid, bk, hcp, up, low, phase
        )


async def _upsert_euro(conn, sid: str, bk: str, h: float, d: float, a: float, phase: str):
    existing = await conn.fetchrow(
        "SELECT id FROM odds_euro WHERE match_id=$1 AND bookmaker=$2 AND odds_type=$3",
        sid, bk, phase
    )
    if existing:
        await conn.execute(
            "UPDATE odds_euro SET home_win=$2, draw=$3, away_win=$4 WHERE id=$1",
            existing['id'], h, d, a
        )
    else:
        await conn.execute(
            "INSERT INTO odds_euro (match_id, bookmaker, home_win, draw, away_win, odds_type) VALUES ($1,$2,$3,$4,$5,$6)",
            sid, bk, h, d, a, phase
        )


async def write_odds_to_db(pool: asyncpg.Pool, sid: str,
                           asian_data: List[Dict], euro_data: List[Dict],
                           write_closing: bool = False,
                           crawl_batch: str = None):
    async with pool.acquire() as conn:
        if asian_data:
            for a in asian_data:
                if a['company_id'] not in COMPANY_MAP:
                    continue
                bk = COMPANY_MAP[a['company_id']]
                await _upsert_asian(conn, sid, bk, a['init_handicap'], a['init_upper'], a['init_lower'], 'initial')
                await _upsert_asian(conn, sid, bk, a['live_handicap'], a['live_upper'], a['live_lower'], 'live')
                if write_closing:
                    await _upsert_asian(conn, sid, bk, a['live_handicap'], a['live_upper'], a['live_lower'], 'closing')

        if euro_data:
            for e in euro_data:
                if e['company_id'] not in EURO_COMPANY_MAP:
                    continue
                bk = EURO_COMPANY_MAP[e['company_id']]
                await _upsert_euro(conn, sid, bk, e['init_h'], e['init_d'], e['init_a'], 'initial')
                await _upsert_euro(conn, sid, bk, e['live_h'], e['live_d'], e['live_a'], 'live')
                if write_closing:
                    await _upsert_euro(conn, sid, bk, e['live_h'], e['live_d'], e['live_a'], 'closing')

        # ── append-only timeline快照（给K线管道用）──
        # 只对live盘写快照；initial基本不变，closing是终盘快照
        try:
            for a in asian_data:
                if a['company_id'] not in COMPANY_MAP:
                    continue
                bk = COMPANY_MAP[a['company_id']]
                await conn.execute("""
                    INSERT INTO odds_timeline
                        (match_id, bookmaker, market_type, odds_type,
                         handicap, home_odds, away_odds,
                         home_win, draw, away_win,
                         snapshot_time, recorded_at, crawl_batch)
                    VALUES ($1,$2,'asia','live',$3,$4,$5,NULL,NULL,NULL,NOW(),NOW(),$6)
                    ON CONFLICT (match_id, bookmaker, market_type, odds_type, snapshot_time)
                    DO NOTHING
                """, sid, bk, a['live_handicap'], a['live_upper'], a['live_lower'], int(crawl_batch))

            for e in euro_data:
                if e['company_id'] not in EURO_COMPANY_MAP:
                    continue
                bk = EURO_COMPANY_MAP[e['company_id']]
                await conn.execute("""
                    INSERT INTO odds_timeline
                        (match_id, bookmaker, market_type, odds_type,
                         handicap, home_odds, away_odds,
                         home_win, draw, away_win,
                         snapshot_time, recorded_at, crawl_batch)
                    VALUES ($1,$2,'euro','live',NULL,NULL,NULL,$3,$4,$5,NOW(),NOW(),$6)
                    ON CONFLICT (match_id, bookmaker, market_type, odds_type, snapshot_time)
                    DO NOTHING
                """, sid, bk, e['live_h'], e['live_d'], e['live_a'], int(crawl_batch))
        except Exception as _te:
            # timeline写入失败不影响赔率主流程
            logger.debug("timeline snapshot failed for %s: %s", sid, _te)


# ── 主流程 ────────────────────────────────────────────────────────

async def get_target_matches(pool: asyncpg.Pool) -> List[Dict]:
    """从DB获取需要抓赔率的比赛：
    1. 走地中(status=live) — 最高优先级
    2. 赛前6小时内(status=not_started)
    3. 完赛2小时内(status=finished) — 终盘修正
    """
    now = datetime.now()
    pre_cutoff = now + timedelta(hours=PRE_MATCH_WINDOW_HOURS)
    finished_cutoff = now - timedelta(hours=FINISHED_GRACE_HOURS)

    rows = await pool.fetch(
        """SELECT match_id, league, home_team, away_team, match_time, status
           FROM matches
           WHERE match_time >= CURRENT_DATE - interval '1 day'
             AND match_time < CURRENT_DATE + interval '1 day'
             AND (
               (status = 'live')
               OR (status = 'not_started' AND match_time <= $1)
               OR (status = 'finished' AND match_time >= $2)
             )
           ORDER BY
             CASE status WHEN 'live' THEN 0 WHEN 'not_started' THEN 1 ELSE 2 END,
             match_time ASC""",
        pre_cutoff, finished_cutoff
    )

    return [dict(r) for r in rows]


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--concurrency', type=int, default=CONCURRENCY)
    args = parser.parse_args()

    start = datetime.now()
    # 本批次ID：同一次运行抓取的所有公司共用，便于后续对齐
    batch_id = start.strftime('%Y%m%d%H%M%S')
    print(f"\n{'━'*50}")
    print(f"  赔率抓取(并发{args.concurrency}) — {start.strftime('%H:%M:%S')} batch={batch_id}")
    print(f"{'━'*50}")

    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=5)

    try:
        # 获取目标比赛
        targets = await get_target_matches(pool)
        if args.limit:
            targets = targets[:args.limit]

        live_count = sum(1 for t in targets if t['status'] == 'live')
        pre_count = sum(1 for t in targets if t['status'] == 'not_started')
        fin_count = sum(1 for t in targets if t['status'] == 'finished')
        print(f"  目标: {len(targets)}场 (走地{live_count} 赛前{pre_count} 完赛修正{fin_count})")

        if not targets:
            print("  无需抓取")
            return

        # 并发抓取
        sem = asyncio.Semaphore(args.concurrency)
        stats = {'asian_ok': 0, 'asian_fail': 0, 'euro_ok': 0, 'euro_fail': 0, 'processed': 0}
        total = len(targets)

        connector = aiohttp.TCPConnector(limit=args.concurrency * 2, ttl_dns_cache=300)
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(connector=connector, cookie_jar=cookie_jar) as session:

            async def process_one(idx: int, match: Dict):
                sid = match['match_id']
                async with sem:
                    # 小随机延迟，避免瞬时并发触发限速
                    await asyncio.sleep(0.1 * (idx % 5))
                    asian_data, euro_data = await fetch_match_odds(session, sid)

                if asian_data:
                    stats['asian_ok'] += 1
                else:
                    stats['asian_fail'] += 1
                if euro_data:
                    stats['euro_ok'] += 1
                else:
                    stats['euro_fail'] += 1

                status_icon = '🔴' if match['status'] == 'live' else (
                    '✅' if match['status'] == 'finished' else '⏰')
                league = (match.get('league') or '')[:8]
                home = (match.get('home_team') or '')[:10]
                away = (match.get('away_team') or '')[:10]

                if idx <= 5 or idx % 20 == 0 or idx == total:
                    print(f"  [{idx:3d}/{total}] {status_icon} {league:8s} | {home:10s} vs {away:10s} | 亚{len(asian_data):2d} 欧{len(euro_data):2d}")

                if not args.dry_run:
                    write_closing = match['status'] in ('not_started', 'finished')
                    await write_odds_to_db(pool, sid, asian_data, euro_data, write_closing, crawl_batch=batch_id)

                stats['processed'] += 1

            tasks = [process_one(i + 1, m) for i, m in enumerate(targets)]
            await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = (datetime.now() - start).total_seconds()
        print(f"\n  ✅ 完成 — {elapsed:.0f}s")
        print(f"  亚盘: 成功{stats['asian_ok']} 失败{stats['asian_fail']}")
        print(f"  欧赔: 成功{stats['euro_ok']} 失败{stats['euro_fail']}")

    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
