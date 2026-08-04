#!/usr/bin/env python3
"""
patch_scraper_timeline.py — 给VPS爬虫注入append-only时间线快照
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
在不改变原有upsert逻辑的前提下，让爬虫每次运行时：
1. 创建crawl_batches记录
2. 在write_asian_odds/write_euro_odds后追加INSERT到odds_timeline
3. 只对live类型做快照（initial基本不变，不需要重复记录）

部署：在VPS执行
  wget --no-check-certificate "https://raw.githubusercontent.com/bk3398/ruipan/main/gold_vps/patch_scraper_timeline.py?nc=1" -O /tmp/patch_st.py
  python3 -u /tmp/patch_st.py
"""

import shutil
import re
import os
from datetime import datetime

SCRAPER_PATH = '/opt/ruipan/scraper/scraper.py'
BACKUP_SUFFIX = f'.bak_timeline_{datetime.now().strftime("%Y%m%d_%H%M%S")}'


def patch_scraper():
    if not os.path.exists(SCRAPER_PATH):
        print(f"ERROR: {SCRAPER_PATH} not found")
        return False

    # 备份
    backup_path = SCRAPER_PATH + BACKUP_SUFFIX
    shutil.copy2(SCRAPER_PATH, backup_path)
    print(f"Backup: {backup_path}")

    with open(SCRAPER_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否已patch
    if 'TIMELINE_PATCH_V1' in content:
        print("Already patched (TIMELINE_PATCH_V1 marker found)")
        return True

    original_size = len(content)

    # ── Patch 1: 在DatabaseWriter类中添加timeline写入方法 ──
    # 找一个好的注入点：在 print_stats 方法后插入
    inject_marker = "    def print_stats(self):"
    timeline_methods = '''    # ── TIMELINE_PATCH_V1: Append-only快照写入 ──
    async def start_crawl_batch(self):
        """开始爬虫批次"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO crawl_batches (status) VALUES ('running') RETURNING id"
            )
            self._batch_id = row['id']
            return self._batch_id

    async def end_crawl_batch(self, matches=0, asia=0, euro=0, status='done'):
        """结束爬虫批次"""
        if not hasattr(self, '_batch_id') or self._batch_id is None:
            return
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE crawl_batches
                SET finished_at=NOW(), matches_processed=$2,
                    asia_snapshots=$3, euro_snapshots=$4, status=$5
                WHERE id=$1
            """, self._batch_id, matches, asia, euro, status)
        self._batch_id = None

    async def write_timeline_snapshot(self, match_id, bookmaker, market_type,
                                       odds_type, **kwargs):
        """写入append-only赔率快照（不覆盖）"""
        if not hasattr(self, '_batch_id'):
            self._batch_id = None
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO odds_timeline
                        (match_id, bookmaker, market_type, odds_type,
                         handicap, home_odds, away_odds,
                         home_win, draw, away_win,
                         snapshot_time, recorded_at, crawl_batch)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW(),NOW(),$11)
                    ON CONFLICT (match_id, bookmaker, market_type, odds_type, snapshot_time)
                    DO NOTHING
                """, match_id, bookmaker, market_type, odds_type,
                    kwargs.get('handicap'), kwargs.get('home_odds'),
                    kwargs.get('away_odds'), kwargs.get('home_win'),
                    kwargs.get('draw'), kwargs.get('away_win'),
                    self._batch_id)
        except Exception as e:
            # 快照写入失败不影响主流程
            pass

    '''

    if inject_marker not in content:
        print("ERROR: Cannot find inject point 'print_stats'")
        return False

    content = content.replace(inject_marker, timeline_methods + inject_marker, 1)

    # ── Patch 2: 在write_asian_odds后追加timeline快照 ──
    # 找到 "self._stats['asia_written'] += 1" 后面插入
    old_asia = """                self._stats['asia_written'] += 1

    async def write_euro_odds"""

    new_asia = """                self._stats['asia_written'] += 1

            # TIMELINE_PATCH_V1: append-only快照（仅live类型）
            if odds_type == 'live':
                await self.write_timeline_snapshot(
                    match_id, bookmaker, 'asia', odds_type,
                    handicap=handicap, home_odds=home_odds, away_odds=away_odds
                )

    async def write_euro_odds"""

    if old_asia not in content:
        print("WARNING: Asia injection point not found, trying alternative...")
        # 尝试用更宽松的匹配
        old_asia_alt = "self._stats['asia_written'] += 1"
        if old_asia_alt in content:
            content = content.replace(
                old_asia_alt,
                old_asia_alt + "\n\n            # TIMELINE_PATCH_V1\n            if odds_type == 'live':\n                await self.write_timeline_snapshot(match_id, bookmaker, 'asia', odds_type, handicap=handicap, home_odds=home_odds, away_odds=away_odds)",
                1
            )
            print("  Injected asia snapshot (alternative mode)")
    else:
        content = content.replace(old_asia, new_asia, 1)
        print("  Injected asia snapshot")

    # ── Patch 3: 在write_euro_odds后追加timeline快照 ──
    old_euro = """                self._stats['euro_written'] += 1

    async def clear_odds_for_match"""

    new_euro = """                self._stats['euro_written'] += 1

            # TIMELINE_PATCH_V1: append-only快照（仅live类型）
            if odds_type == 'live':
                await self.write_timeline_snapshot(
                    match_id, bookmaker, 'euro', odds_type,
                    home_win=home_win, draw=draw, away_win=away_win
                )

    async def clear_odds_for_match"""

    if old_euro not in content:
        print("WARNING: Euro injection point not found, trying alternative...")
        old_euro_alt = "self._stats['euro_written'] += 1"
        if old_euro_alt in content:
            content = content.replace(
                old_euro_alt,
                old_euro_alt + "\n\n            # TIMELINE_PATCH_V1\n            if odds_type == 'live':\n                await self.write_timeline_snapshot(match_id, bookmaker, 'euro', odds_type, home_win=home_win, draw=draw, away_win=away_win)",
                1
            )
            print("  Injected euro snapshot (alternative mode)")
    else:
        content = content.replace(old_euro, new_euro, 1)
        print("  Injected euro snapshot")

    # ── Patch 4: 在run方法中注入batch ──
    # 找到数据库连接后，开始处理前
    old_run = "self.stats['processed'] += 1"
    new_run = """self.stats['processed'] += 1

            # TIMELINE_PATCH_V1: 批次统计（在循环外初始化）"""

    # 更安全的方式：在 "async with self.db.pool.acquire" 之前/之后注入start_batch
    # 找到run方法中数据库初始化的位置
    if "self.db.start_crawl_batch" not in content:
        # 找 "elapsed = time.time() - start" 前注入end_batch
        old_elapsed = "            elapsed = time.time() - start"
        new_elapsed = """            # TIMELINE_PATCH_V1: 结束爬虫批次
            try:
                await self.db.end_crawl_batch(
                    matches=self.stats.get('processed', 0),
                    asia=self.stats.get('asian_ok', 0),
                    euro=self.stats.get('euro_ok', 0),
                )
            except Exception:
                pass

            elapsed = time.time() - start"""

        if old_elapsed in content:
            content = content.replace(old_elapsed, new_elapsed, 1)
            print("  Injected end_batch")

        # 在数据库初始化后注入start_batch
        # 找self.db = 或 pool初始化的位置
        old_db_init = "self.db = db"
        if old_db_init in content:
            content = content.replace(
                old_db_init,
                old_db_init + "\n            # TIMELINE_PATCH_V1: 开始爬虫批次\n            try:\n                await db.start_crawl_batch()\n            except Exception:\n                pass",
                1
            )
            print("  Injected start_batch")

    # 写入
    with open(SCRAPER_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    new_size = len(content)
    print(f"\nFile size: {original_size} → {new_size} bytes (diff: {new_size - original_size})")

    # 验证
    with open(SCRAPER_PATH, 'r', encoding='utf-8') as f:
        verify = f.read()

    checks = [
        ('TIMELINE_PATCH_V1 marker', 'TIMELINE_PATCH_V1' in verify),
        ('write_timeline_snapshot method', 'async def write_timeline_snapshot' in verify),
        ('start_crawl_batch', 'async def start_crawl_batch' in verify),
        ('end_crawl_batch', 'async def end_crawl_batch' in verify),
        ('asia timeline call', "market_type, 'asia'" in verify),
        ('euro timeline call', "market_type, 'euro'" in verify),
    ]

    all_ok = True
    print("\nVerification:")
    for name, ok in checks:
        status = '✅' if ok else '❌'
        print(f"  {status} {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n✅ Patch applied successfully!")
        print("Next steps:")
        print("  1. python3 timeline_schema.py --migrate  (建表)")
        print("  2. systemctl restart ruipan-scraper     (重启爬虫)")
        print("  3. Wait 15min, check: sudo -u postgres psql -d ruipan -c 'SELECT COUNT(*) FROM odds_timeline;'")
    else:
        print("\n⚠️ Some checks failed, review the patched file")

    return all_ok


if __name__ == '__main__':
    patch_scraper()
