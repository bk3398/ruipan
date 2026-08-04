#!/usr/bin/env python3
"""
patch_scraper_timeline_v2.py — 修正版：修复缩进问题
"""

import shutil
import os
from datetime import datetime

SCRAPER_PATH = '/opt/ruipan/scraper/scraper.py'
BACKUP_SUFFIX = f'.bak_timeline_{datetime.now().strftime("%Y%m%d_%H%M%S")}'


def patch_scraper():
    if not os.path.exists(SCRAPER_PATH):
        print(f"ERROR: {SCRAPER_PATH} not found")
        return False

    # 如果已patch过（从备份恢复后应该没有），跳过
    with open(SCRAPER_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'TIMELINE_PATCH_V2' in content:
        print("Already patched (TIMELINE_PATCH_V2 marker found)")
        return True

    # 备份
    backup_path = SCRAPER_PATH + BACKUP_SUFFIX
    shutil.copy2(SCRAPER_PATH, backup_path)
    print(f"Backup: {backup_path}")

    original_size = len(content)

    # ── Patch 1: 在 print_stats 前插入timeline方法 ──
    inject_marker = "    def print_stats(self):"

    # 注意：末尾不能有多余空格，否则会把print_stats顶进上一个方法
    timeline_methods = (
        "    # ── TIMELINE_PATCH_V2: Append-only快照写入 ──\n"
        "    async def start_crawl_batch(self):\n"
        "        async with self.pool.acquire() as conn:\n"
        "            row = await conn.fetchrow(\n"
        '                "INSERT INTO crawl_batches (status) VALUES (\'running\') RETURNING id"\n'
        "            )\n"
        "            self._batch_id = row['id']\n"
        "            return self._batch_id\n"
        "\n"
        "    async def end_crawl_batch(self, matches=0, asia=0, euro=0, status='done'):\n"
        "        if not hasattr(self, '_batch_id') or self._batch_id is None:\n"
        "            return\n"
        "        async with self.pool.acquire() as conn:\n"
        "            await conn.execute(\"\"\"\n"
        "                UPDATE crawl_batches\n"
        "                SET finished_at=NOW(), matches_processed=$2,\n"
        "                    asia_snapshots=$3, euro_snapshots=$4, status=$5\n"
        "                WHERE id=$1\n"
        "            \"\"\", self._batch_id, matches, asia, euro, status)\n"
        "        self._batch_id = None\n"
        "\n"
        "    async def write_timeline_snapshot(self, match_id, bookmaker, market_type,\n"
        "                                       odds_type, **kwargs):\n"
        "        if not hasattr(self, '_batch_id'):\n"
        "            self._batch_id = None\n"
        "        try:\n"
        "            async with self.pool.acquire() as conn:\n"
        "                await conn.execute(\"\"\"\n"
        "                    INSERT INTO odds_timeline\n"
        "                        (match_id, bookmaker, market_type, odds_type,\n"
        "                         handicap, home_odds, away_odds,\n"
        "                         home_win, draw, away_win,\n"
        "                         snapshot_time, recorded_at, crawl_batch)\n"
        "                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW(),NOW(),$11)\n"
        "                    ON CONFLICT (match_id, bookmaker, market_type, odds_type, snapshot_time)\n"
        "                    DO NOTHING\n"
        "                \"\"\", match_id, bookmaker, market_type, odds_type,\n"
        "                    kwargs.get('handicap'), kwargs.get('home_odds'),\n"
        "                    kwargs.get('away_odds'), kwargs.get('home_win'),\n"
        "                    kwargs.get('draw'), kwargs.get('away_win'),\n"
        "                    self._batch_id)\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
    )

    if inject_marker not in content:
        print("ERROR: Cannot find inject point 'def print_stats'")
        return False

    content = content.replace(inject_marker, timeline_methods + inject_marker, 1)
    print("  Injected timeline methods")

    # ── Patch 2: 亚盘快照调用 ──
    # VPS实际代码结构：self._stats['asia_written'] += 1 后面紧接 async def write_euro_odds
    asia_old = "                self._stats['asia_written'] += 1\n\n    async def write_euro_odds"
    asia_new = (
        "                self._stats['asia_written'] += 1\n"
        "\n"
        "            # TIMELINE_PATCH_V2\n"
        "            if odds_type == 'live':\n"
        "                await self.write_timeline_snapshot(\n"
        "                    match_id, bookmaker, 'asia', odds_type,\n"
        "                    handicap=handicap, home_odds=home_odds, away_odds=away_odds\n"
        "                )\n"
        "\n"
        "    async def write_euro_odds"
    )

    if asia_old in content:
        content = content.replace(asia_old, asia_new, 1)
        print("  Injected asia snapshot call")
    else:
        # fallback: 简单匹配
        asia_fallback = "self._stats['asia_written'] += 1"
        if asia_fallback in content:
            content = content.replace(
                asia_fallback,
                asia_fallback +
                "\n\n            # TIMELINE_PATCH_V2\n"
                "            if odds_type == 'live':\n"
                "                await self.write_timeline_snapshot(\n"
                "                    match_id, bookmaker, 'asia', odds_type,\n"
                "                    handicap=handicap, home_odds=home_odds, away_odds=away_odds\n"
                "                )",
                1
            )
            print("  Injected asia snapshot call (fallback)")
        else:
            print("  ERROR: asia injection point not found")
            return False

    # ── Patch 3: 欧盘快照调用 ──
    euro_old = "                self._stats['euro_written'] += 1\n\n    async def clear_odds_for_match"
    euro_new = (
        "                self._stats['euro_written'] += 1\n"
        "\n"
        "            # TIMELINE_PATCH_V2\n"
        "            if odds_type == 'live':\n"
        "                await self.write_timeline_snapshot(\n"
        "                    match_id, bookmaker, 'euro', odds_type,\n"
        "                    home_win=home_win, draw=draw, away_win=away_win\n"
        "                )\n"
        "\n"
        "    async def clear_odds_for_match"
    )

    if euro_old in content:
        content = content.replace(euro_old, euro_new, 1)
        print("  Injected euro snapshot call")
    else:
        euro_fallback = "self._stats['euro_written'] += 1"
        if euro_fallback in content:
            content = content.replace(
                euro_fallback,
                euro_fallback +
                "\n\n            # TIMELINE_PATCH_V2\n"
                "            if odds_type == 'live':\n"
                "                await self.write_timeline_snapshot(\n"
                "                    match_id, bookmaker, 'euro', odds_type,\n"
                "                    home_win=home_win, draw=draw, away_win=away_win\n"
                "                )",
                1
            )
            print("  Injected euro snapshot call (fallback)")
        else:
            print("  ERROR: euro injection point not found")
            return False

    # ── Patch 4: 批次追踪（可选，不影响数据采集）──
    # 在 elapsed = time.time() - start 前插入 end_batch
    if "end_crawl_batch" not in content.split("def print_stats")[0]:
        old_elapsed = "            elapsed = time.time() - start"
        if old_elapsed in content:
            new_elapsed = (
                "            # TIMELINE_PATCH_V2: 结束批次\n"
                "            try:\n"
                "                await self.db.end_crawl_batch(\n"
                "                    matches=self.stats.get('processed', 0),\n"
                "                    asia=self.stats.get('asia_written', 0),\n"
                "                    euro=self.stats.get('euro_written', 0),\n"
                "                )\n"
                "            except Exception:\n"
                "                pass\n"
                "\n"
                "            elapsed = time.time() - start"
            )
            content = content.replace(old_elapsed, new_elapsed, 1)
            print("  Injected end_batch")

    # 写入
    with open(SCRAPER_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    new_size = len(content)
    print(f"\nFile size: {original_size} → {new_size} bytes (diff: {new_size - original_size})")

    # 语法检查
    import ast
    try:
        ast.parse(content)
        print("✅ Syntax check passed")
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
        print("Restoring backup...")
        shutil.copy2(backup_path, SCRAPER_PATH)
        print("Restored from backup")
        return False

    # 验证
    checks = [
        ('TIMELINE_PATCH_V2 marker', 'TIMELINE_PATCH_V2' in content),
        ('write_timeline_snapshot method', 'async def write_timeline_snapshot' in content),
        ('asia call', "bookmaker, 'asia'" in content),
        ('euro call', "bookmaker, 'euro'" in content),
    ]

    all_ok = True
    print("\nVerification:")
    for name, ok in checks:
        status = '✅' if ok else '❌'
        print(f"  {status} {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n✅ Patch v2 applied successfully!")
    else:
        print("\n⚠️ Some checks failed")

    return all_ok


if __name__ == '__main__':
    patch_scraper()
