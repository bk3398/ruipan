#!/usr/bin/env python3
"""
锐盘VPS数据层 — 时间线Schema & Append-Only写入器
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本文件部署在VPS，仅包含：
  1. 数据库表结构创建
  2. append-only快照写入
  3. 原始数据导出（供沙箱拉取）

不含任何算法、计算逻辑、模型参数。
算法全部在Coze沙箱执行，结果以JSON推送到VPS。

用法:
  python3 timeline_schema.py --migrate     # 建表
  python3 timeline_schema.py --export      # 导出新timeline数据为JSON
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import asyncpg

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

DSN = "postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan"
EXPORT_PATH = "/opt/ruipan/data/timeline_export.json"

# ═══════════════════════════════════════════════════════════════════════
#  Schema — VPS只建表，不建函数/触发器/计算逻辑
# ═══════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
-- 赔率时间线（append-only，永不覆盖）
CREATE TABLE IF NOT EXISTS odds_timeline (
    id BIGSERIAL PRIMARY KEY,
    match_id VARCHAR(50) NOT NULL,
    bookmaker VARCHAR(50) NOT NULL,
    market_type VARCHAR(10) NOT NULL,
    odds_type VARCHAR(10) NOT NULL,
    handicap NUMERIC(5,2),
    home_odds NUMERIC(6,3),
    away_odds NUMERIC(6,3),
    home_win NUMERIC(6,3),
    draw NUMERIC(6,3),
    away_win NUMERIC(6,3),
    snapshot_time TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    crawl_batch BIGINT,
    source VARCHAR(20) DEFAULT 'titan007',
    CONSTRAINT uq_timeline UNIQUE (match_id, bookmaker, market_type, odds_type, snapshot_time)
);
CREATE INDEX IF NOT EXISTS idx_ot_match ON odds_timeline(match_id);
CREATE INDEX IF NOT EXISTS idx_ot_time ON odds_timeline(snapshot_time);
CREATE INDEX IF NOT EXISTS idx_ot_bm ON odds_timeline(bookmaker);
CREATE INDEX IF NOT EXISTS idx_ot_match_bm ON odds_timeline(match_id, bookmaker, market_type);
CREATE INDEX IF NOT EXISTS idx_ot_recorded ON odds_timeline(recorded_at);

-- 球队状态时间线（沙箱算好后批量写入）
CREATE TABLE IF NOT EXISTS team_form_timeline (
    id BIGSERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    league VARCHAR(100),
    season VARCHAR(20),
    match_id VARCHAR(50) NOT NULL,
    match_date DATE NOT NULL,
    is_home BOOLEAN NOT NULL,
    opponent VARCHAR(100),
    goals_for INTEGER,
    goals_against INTEGER,
    result VARCHAR(5),
    cumulative_points INTEGER,
    points_per_game NUMERIC(5,3),
    form_ema NUMERIC(6,3),
    rolling_gf NUMERIC(5,2),
    rolling_ga NUMERIC(5,2),
    rolling_gd NUMERIC(5,2),
    rolling_win_rate NUMERIC(5,3),
    attack_strength NUMERIC(6,3),
    defense_strength NUMERIC(6,3),
    home_away_form VARCHAR(10),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_team_form UNIQUE (team_name, match_id, home_away_form)
);
CREATE INDEX IF NOT EXISTS idx_tf_team ON team_form_timeline(team_name);
CREATE INDEX IF NOT EXISTS idx_tf_league ON team_form_timeline(league, season);
CREATE INDEX IF NOT EXISTS idx_tf_date ON team_form_timeline(match_date);

-- K线缓存（沙箱聚合后写入，VPS只读）
CREATE TABLE IF NOT EXISTS kline_cache (
    id BIGSERIAL PRIMARY KEY,
    match_id VARCHAR(50) NOT NULL,
    kline_type VARCHAR(30) NOT NULL,
    window_minutes INTEGER NOT NULL,
    bucket_time TIMESTAMPTZ NOT NULL,
    open NUMERIC(10,4),
    high NUMERIC(10,4),
    low NUMERIC(10,4),
    close NUMERIC(10,4),
    volume INTEGER DEFAULT 0,
    extra JSONB,
    aggregated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_kline UNIQUE (match_id, kline_type, window_minutes, bucket_time)
);
CREATE INDEX IF NOT EXISTS idx_kc_match ON kline_cache(match_id, kline_type);
CREATE INDEX IF NOT EXISTS idx_kc_time ON kline_cache(bucket_time);

-- 爬虫批次追踪
CREATE TABLE IF NOT EXISTS crawl_batches (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    matches_processed INTEGER DEFAULT 0,
    asia_snapshots INTEGER DEFAULT 0,
    euro_snapshots INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'running',
    notes TEXT
);

-- 形态特征库（沙箱提取标注后写入）
CREATE TABLE IF NOT EXISTS pattern_library (
    id BIGSERIAL PRIMARY KEY,
    pattern_type VARCHAR(50) NOT NULL,
    match_id VARCHAR(50) NOT NULL,
    bookmaker VARCHAR(50),
    features JSONB NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    handicap_result VARCHAR(10),
    total_goals INTEGER,
    confidence NUMERIC(5,3),
    sample_count INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    labeled_at TIMESTAMPTZ,
    CONSTRAINT uq_pattern UNIQUE (pattern_type, match_id, bookmaker)
);
CREATE INDEX IF NOT EXISTS idx_pl_type ON pattern_library(pattern_type);
CREATE INDEX IF NOT EXISTS idx_pl_labeled ON pattern_library(labeled_at) WHERE labeled_at IS NOT NULL;

-- 迁移日志
CREATE TABLE IF NOT EXISTS migration_log (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(100) UNIQUE NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO migration_log (migration_name) VALUES ('timeline_v1')
ON CONFLICT (migration_name) DO NOTHING;
"""


async def migrate(dsn: str = DSN):
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(SCHEMA_SQL)
        logger.info("✅ Schema created")
        for tbl in ['odds_timeline', 'team_form_timeline', 'kline_cache',
                     'crawl_batches', 'pattern_library']:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            logger.info(f"  {tbl}: {count} rows")
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════════════
#  Append-Only 写入器 — 供爬虫调用，只INSERT不UPDATE不DELETE
# ═══════════════════════════════════════════════════════════════════════

async def insert_snapshot(
    conn,
    match_id: str,
    bookmaker: str,
    market_type: str,
    odds_type: str,
    snapshot_time: datetime,
    crawl_batch: int = None,
    handicap: float = None,
    home_odds: float = None,
    away_odds: float = None,
    home_win: float = None,
    draw: float = None,
    away_win: float = None,
):
    """写入一条赔率快照，冲突时跳过（同一时间点同一数据不重复写）"""
    await conn.execute("""
        INSERT INTO odds_timeline
            (match_id, bookmaker, market_type, odds_type,
             handicap, home_odds, away_odds, home_win, draw, away_win,
             snapshot_time, recorded_at, crawl_batch)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW(),$12)
        ON CONFLICT (match_id, bookmaker, market_type, odds_type, snapshot_time)
        DO NOTHING
    """, match_id, bookmaker, market_type, odds_type,
        handicap, home_odds, away_odds, home_win, draw, away_win,
        snapshot_time, crawl_batch)


async def start_batch(conn) -> int:
    """开始一个爬虫批次，返回batch_id"""
    row = await conn.fetchrow(
        "INSERT INTO crawl_batches (status) VALUES ('running') RETURNING id"
    )
    return row['id']


async def end_batch(conn, batch_id: int, matches: int, asia: int, euro: int,
                     status: str = 'done'):
    await conn.execute("""
        UPDATE crawl_batches
        SET finished_at=NOW(), matches_processed=$2,
            asia_snapshots=$3, euro_snapshots=$4, status=$5
        WHERE id=$1
    """, batch_id, matches, asia, euro, status)


# ═══════════════════════════════════════════════════════════════════════
#  数据导出 — 沙箱通过此接口拉取原始数据，算法在沙箱执行
# ═══════════════════════════════════════════════════════════════════════

async def export_timeline(dsn: str = DSN, since_hours: int = 24,
                           output_path: str = EXPORT_PATH):
    """
    导出最近N小时的timeline原始数据为JSON。
    沙箱拉取后在本地执行K线聚合、形态提取等算法，
    结果再推回VPS写入kline_cache/pattern_library。
    """
    conn = await asyncpg.connect(dsn)
    try:
        since = datetime.utcnow() - timedelta(hours=since_hours)

        rows = await conn.fetch("""
            SELECT match_id, bookmaker, market_type, odds_type,
                   handicap, home_odds, away_odds, home_win, draw, away_win,
                   snapshot_time, recorded_at
            FROM odds_timeline
            WHERE recorded_at >= $1
            ORDER BY match_id, recorded_at ASC
        """, since)

        # 同时导出完赛比赛信息（供标注）
        finished = await conn.fetch("""
            SELECT match_id, league, home_team, away_team,
                   home_score, away_score, match_time, status
            FROM matches
            WHERE status = 'finished'
              AND match_time >= $1
            ORDER BY match_time DESC
        """, since - timedelta(hours=since_hours))

        data = {
            'exported_at': datetime.utcnow().isoformat(),
            'since': since.isoformat(),
            'timeline_count': len(rows),
            'finished_count': len(finished),
            'timeline': [
                {
                    'match_id': r['match_id'],
                    'bookmaker': r['bookmaker'],
                    'market_type': r['market_type'],
                    'odds_type': r['odds_type'],
                    'handicap': float(r['handicap']) if r['handicap'] is not None else None,
                    'home_odds': float(r['home_odds']) if r['home_odds'] is not None else None,
                    'away_odds': float(r['away_odds']) if r['away_odds'] is not None else None,
                    'home_win': float(r['home_win']) if r['home_win'] is not None else None,
                    'draw': float(r['draw']) if r['draw'] is not None else None,
                    'away_win': float(r['away_win']) if r['away_win'] is not None else None,
                    'snapshot_time': r['snapshot_time'].isoformat() if r['snapshot_time'] else None,
                    'recorded_at': r['recorded_at'].isoformat(),
                }
                for r in rows
            ],
            'finished_matches': [
                {
                    'match_id': r['match_id'],
                    'league': r['league'],
                    'home_team': r['home_team'],
                    'away_team': r['away_team'],
                    'home_score': r['home_score'],
                    'away_score': r['away_score'],
                    'match_time': r['match_time'].isoformat() if r['match_time'] else None,
                }
                for r in finished
            ],
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

        logger.info(f"✅ Exported {len(rows)} timeline + {len(finished)} matches → {output_path}")
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════════════

async def main():
    import sys
    if '--migrate' in sys.argv:
        await migrate()
    elif '--export' in sys.argv:
        hours = 24
        for i, arg in enumerate(sys.argv):
            if arg == '--hours' and i+1 < len(sys.argv):
                hours = int(sys.argv[i+1])
        await export_timeline(since_hours=hours)
    else:
        print(__doc__)


if __name__ == '__main__':
    asyncio.run(main())
