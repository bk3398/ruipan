#!/usr/bin/env python3
"""
kline_aggregator.py — VPS端K线聚合引擎
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
直接从 odds_timeline 读取赔率快照，计算分歧度 → OHLC聚合 →
形态特征提取 → 标签分类 → 写入 kline_cache / pattern_library。

数据流（全部在VPS本地闭环）：
  odds_fetcher → odds_timeline (append-only)
  → 本脚本 (cron */30min)
  → kline_cache + pattern_library
  → kline_api.py → 前端展示

不含预测模型、回测参数、胜率计算。仅做数据聚合与模式标注。

用法:
  python3 kline_aggregator.py              # 增量聚合最近12小时
  python3 kline_aggregator.py --full       # 全量重建
  python3 kline_aggregator.py --hours 24   # 指定时间窗口
"""

import asyncio
import bisect
import math
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import asyncpg

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

DSN = "postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan"

# ── 参数 ──────────────────────────────────────────────────────────────
KLINE_WINDOWS = [30, 60, 120]
PRE_MATCH_FINE_WINDOW = 10
PRE_MATCH_FINE_HOURS = 2
CROSS_ALIGN_MAX_GAP_MIN = 30
MIN_CANDLES_FOR_PATTERN = 3

# 水位有效范围
ASIA_WATER_MIN = 0.5
ASIA_WATER_MAX = 2.0
EURO_MIN_VALID = 1.0
EURO_MAX_VALID = 3.0

# 形态阈值
CONVERGENCE_THRESHOLD = 0.7
DIVERGENCE_THRESHOLD = 1.4
TREND_THRESHOLD = 0.001

# EMA参数（球队状态用，本期暂不计算球队K线）
EMA_SPAN = 5
FORM_WINDOW = 10


# ═══════════════════════════════════════════════════════════════════════
#  分歧度计算
# ═══════════════════════════════════════════════════════════════════════

def water_divergence(home_odds: float, away_odds: float) -> Optional[float]:
    """亚盘水位分歧度 = |上盘水位 - 下盘水位|"""
    if home_odds is None or away_odds is None:
        return None
    if not (ASIA_WATER_MIN <= home_odds <= ASIA_WATER_MAX):
        return None
    if not (ASIA_WATER_MIN <= away_odds <= ASIA_WATER_MAX):
        return None
    return round(abs(home_odds - away_odds), 4)


def euro_dispersion(odds_list: List[Tuple[float, float, float]]) -> float:
    """欧赔离散度 = 多家公司主胜赔率的变异系数(CV)"""
    valid = [o for o in odds_list if o and o[0] and EURO_MIN_VALID <= o[0] <= EURO_MAX_VALID]
    if len(valid) < 2:
        return 0.0
    vals = [o[0] for o in valid]
    mean = sum(vals) / len(vals)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    return round(math.sqrt(variance) / mean, 4)


def cross_bookmaker_divergence(
    bm1: Tuple[float, float, float],
    bm2: Tuple[float, float, float],
) -> Optional[float]:
    """跨机构分歧度（皇冠vs澳门）：水位差 + 盘口差×0.3"""
    if not bm1 or not bm2:
        return None
    h1, ho1, ao1 = bm1
    h2, ho2, ao2 = bm2
    if ho1 is None or ho2 is None:
        return None
    waters = [w for w in [ho1, ao1, ho2, ao2] if w is not None]
    if not all(ASIA_WATER_MIN <= w <= ASIA_WATER_MAX for w in waters):
        return None
    hdp_diff = abs((h1 or 0) - (h2 or 0))
    water_diff = abs(ho1 - ho2)
    return round(water_diff + hdp_diff * 0.3, 4)


# ═══════════════════════════════════════════════════════════════════════
#  OHLC聚合
# ═══════════════════════════════════════════════════════════════════════

def _make_candle(bucket_time: datetime, values: List[float], volume: int) -> Dict:
    return {
        'bucket_time': bucket_time,
        'open': round(values[0], 4),
        'high': round(max(values), 4),
        'low': round(min(values), 4),
        'close': round(values[-1], 4),
        'volume': volume,
    }


def aggregate_ohlc(snapshots: List[Dict], window_minutes: int,
                   value_key: str = 'value') -> List[Dict]:
    """时间序列 → OHLC蜡烛"""
    if not snapshots:
        return []

    candles = []
    wd = timedelta(minutes=window_minutes)

    first = snapshots[0]['time']
    if isinstance(first, str):
        first = datetime.fromisoformat(first.replace('Z', '+00:00'))
    bucket = first.replace(second=0, microsecond=0)
    bucket = bucket.replace(minute=(bucket.minute // window_minutes) * window_minutes)
    if bucket.tzinfo is not None:
        bucket = bucket.replace(tzinfo=None)

    vals = []
    vol = 0
    cur = bucket

    for snap in snapshots:
        t = snap['time']
        if isinstance(t, str):
            t = datetime.fromisoformat(t.replace('Z', '+00:00'))
        if hasattr(t, 'tzinfo') and t.tzinfo is not None:
            t = t.replace(tzinfo=None)

        while t >= cur + wd:
            if vals:
                candles.append(_make_candle(cur, vals, vol))
            vals = []
            vol = 0
            cur += wd

        v = snap.get(value_key)
        if v is not None:
            vals.append(v)
        vol += 1

    if vals:
        candles.append(_make_candle(cur, vals, vol))

    return candles


# ═══════════════════════════════════════════════════════════════════════
#  形态特征提取 & 分类
# ═══════════════════════════════════════════════════════════════════════

def extract_pattern_features(candles: List[Dict],
                              hdp_changes: int = 0) -> Optional[Dict]:
    """从K线序列提取形态特征向量"""
    if len(candles) < MIN_CANDLES_FOR_PATTERN:
        return None

    closes = [c['close'] for c in candles]
    n = len(closes)
    mean_close = sum(closes) / n

    # 线性回归斜率
    xm = (n - 1) / 2.0
    ym = mean_close
    num = sum((i - xm) * (c - ym) for i, c in enumerate(closes))
    den = sum((i - xm) ** 2 for i in range(n))
    slope = num / den if den > 0 else 0

    # 振幅
    hi = max(c['high'] for c in candles)
    lo = min(c['low'] for c in candles)
    amp = (hi - lo) / ym if ym > 0 else 0

    # 收敛/发散
    mid = n // 2
    first_half = closes[:mid]
    second_half = closes[mid:]

    def _sv(vals):
        if len(vals) < 2:
            return 0
        m = sum(vals) / len(vals)
        return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))

    sf, ss = _sv(first_half), _sv(second_half)
    conv_ratio = ss / sf if sf > 0 else 1.0

    if conv_ratio < CONVERGENCE_THRESHOLD:
        pattern = 'convergence'
    elif conv_ratio > DIVERGENCE_THRESHOLD:
        pattern = 'divergence'
    else:
        pattern = 'stable'

    # 尾部方向
    tail = candles[-3:]
    tail_dir = sum(1 for c in tail if c['close'] > c['open']) - \
               sum(1 for c in tail if c['close'] < c['open'])

    # 量能趋势
    vf = sum(c.get('volume', 0) for c in candles[:mid]) / max(mid, 1)
    vs = sum(c.get('volume', 0) for c in candles[mid:]) / max(n - mid, 1)
    vol_trend = vs / vf if vf > 0 else 1.0

    # 上影线
    shadows = []
    for c in candles:
        body = abs(c['close'] - c['open'])
        tr = c['high'] - c['low']
        if tr > 0:
            us = c['high'] - max(c['open'], c['close'])
            shadows.append(us / tr)
    avg_shadow = sum(shadows) / len(shadows) if shadows else 0

    if slope > TREND_THRESHOLD:
        trend = 'up'
    elif slope < -TREND_THRESHOLD:
        trend = 'down'
    else:
        trend = 'flat'

    return {
        'trend_slope': round(slope, 6),
        'trend': trend,
        'amplitude': round(amp, 4),
        'convergence_ratio': round(conv_ratio, 3),
        'pattern': pattern,
        'tail_direction': tail_dir,
        'volume_trend': round(vol_trend, 3),
        'avg_upper_shadow': round(avg_shadow, 3),
        'handicap_changes': hdp_changes,
        'candle_count': n,
        'start_value': closes[0],
        'end_value': closes[-1],
        'net_change': round(closes[-1] - closes[0], 4),
    }


def classify_pattern(features: Dict) -> List[str]:
    """将特征向量分类为具名形态标签"""
    tags = []
    f = features

    if f['pattern'] == 'convergence' and f['trend'] == 'down':
        tags.append('共识形成')
    elif f['pattern'] == 'divergence' and f['trend'] == 'up':
        tags.append('分歧扩大')

    if f['volume_trend'] > 1.3 and f['pattern'] == 'divergence':
        tags.append('放量分歧')
    elif f['volume_trend'] < 0.7 and f['pattern'] == 'stable':
        tags.append('缩量企稳')

    if f['tail_direction'] >= 2 and f['amplitude'] > 0.02:
        tags.append('尾盘拉升')
    elif f['tail_direction'] <= -2 and f['amplitude'] > 0.02:
        tags.append('尾盘回落')

    if f['avg_upper_shadow'] > 0.4:
        tags.append('上影试探')

    if f['handicap_changes'] >= 3:
        tags.append('频繁变盘')
    elif f['handicap_changes'] == 0 and f['pattern'] == 'stable':
        tags.append('盘口坚定')

    if f['convergence_ratio'] < 0.5 and f['amplitude'] > 0.03:
        tags.append('V型收敛')

    if not tags:
        tags.append('常态波动')

    return tags


# ═══════════════════════════════════════════════════════════════════════
#  盘口结算
# ═══════════════════════════════════════════════════════════════════════

def settle_handicap(home_score: int, away_score: int, handicap: float) -> str:
    """亚盘结算（含半球/四分之一球半赢半输）"""
    diff = home_score - away_score + handicap
    if diff > 0.25:
        return 'upper_win'
    elif diff < -0.25:
        return 'lower_win'
    elif abs(diff) < 0.01:
        return 'push'
    elif diff > 0:
        return 'half_win'
    else:
        return 'half_lose'


# ═══════════════════════════════════════════════════════════════════════
#  跨机构快照对齐
# ═══════════════════════════════════════════════════════════════════════

def _align_and_calc_cross(snaps1: List[Dict], snaps2: List[Dict]) -> List[Dict]:
    """对齐两个机构快照并计算跨机构分歧度（bisect二分查找）"""
    result = []
    max_gap = CROSS_ALIGN_MAX_GAP_MIN * 60

    # 预建snaps2的时间索引
    times2 = [s['time'] for s in snaps2]

    for s1 in snaps1:
        if s1['home_odds'] is None:
            continue

        idx = bisect.bisect_left(times2, s1['time'])
        candidates = []
        if idx < len(snaps2):
            candidates.append(snaps2[idx])
        if idx > 0:
            candidates.append(snaps2[idx - 1])

        best = None
        best_gap = float('inf')
        for s2 in candidates:
            if s2['home_odds'] is None:
                continue
            gap = abs((s1['time'] - s2['time']).total_seconds())
            if gap < best_gap:
                best_gap = gap
                best = s2

        if best and best_gap <= max_gap:
            d = cross_bookmaker_divergence(
                (s1['handicap'], s1['home_odds'], s1['away_odds']),
                (best['handicap'], best['home_odds'], best['away_odds']),
            )
            if d is not None:
                result.append({'time': s1['time'], 'value': d})
    return result


# ═══════════════════════════════════════════════════════════════════════
#  单场比赛处理
# ═══════════════════════════════════════════════════════════════════════

def process_match(snaps: List[Dict], match_info: Dict = None) -> Dict:
    """
    处理一场比赛的全部timeline快照。
    返回 klines 和 patterns。
    """
    match_id = snaps[0]['match_id'] if snaps else None

    asia = defaultdict(list)
    euro = defaultdict(list)

    for s in snaps:
        t = s.get('snapshot_time') or s.get('recorded_at')
        if isinstance(t, str):
            t = datetime.fromisoformat(t.replace('Z', '+00:00'))
        if hasattr(t, 'tzinfo') and t.tzinfo is not None:
            t = t.replace(tzinfo=None)

        if s['market_type'] == 'asia':
            asia[s['bookmaker']].append({
                'time': t,
                'handicap': s.get('handicap'),
                'home_odds': s.get('home_odds'),
                'away_odds': s.get('away_odds'),
            })
        elif s['market_type'] == 'euro':
            euro[s['bookmaker']].append({
                'time': t,
                'home_win': s.get('home_win'),
                'draw': s.get('draw'),
                'away_win': s.get('away_win'),
            })

    all_klines = {}
    all_patterns = {}

    # 开赛时间（用于赛前2小时细粒度窗口）
    kickoff = None
    if match_info and match_info.get('match_time'):
        mt = match_info['match_time']
        if isinstance(mt, str):
            kickoff = datetime.fromisoformat(
                mt.replace('Z', '+00:00').replace('+00:00', ''))
        elif isinstance(mt, datetime):
            kickoff = mt.replace(tzinfo=None) if mt.tzinfo else mt

    # 切出赛前2小时快照子集
    pre_snaps = None
    if kickoff is not None:
        pre_start = kickoff - timedelta(hours=PRE_MATCH_FINE_HOURS)
        pre_map_asia = defaultdict(list)
        pre_map_euro = defaultdict(list)
        for bm, slist in asia.items():
            for s in slist:
                if pre_start <= s['time'] <= kickoff:
                    pre_map_asia[bm].append(s)
        for bm, slist in euro.items():
            for s in slist:
                if pre_start <= s['time'] <= kickoff:
                    pre_map_euro[bm].append(s)
        if any(pre_map_asia.values()) or any(pre_map_euro.values()):
            pre_snaps = (pre_map_asia, pre_map_euro)

    windows = list(KLINE_WINDOWS)
    if pre_snaps is not None:
        windows.append(PRE_MATCH_FINE_WINDOW)

    for window in windows:
        wkey = f'{window}min'
        all_klines[wkey] = {}

        if window == PRE_MATCH_FINE_WINDOW and pre_snaps is not None:
            asia_w, euro_w = pre_snaps
        else:
            asia_w, euro_w = asia, euro

        # 1. 各机构亚盘水位分歧
        for bm in ['crown', 'macau']:
            bm_snaps = asia_w.get(bm, [])
            values = []
            for s in bm_snaps:
                d = water_divergence(s['home_odds'], s['away_odds'])
                if d is not None:
                    values.append({'time': s['time'], 'value': d})

            if values:
                candles = aggregate_ohlc(values, window)
                ktype = f'div_asia_{bm}'
                all_klines[wkey][ktype] = candles

                if window == 60 and len(candles) >= MIN_CANDLES_FOR_PATTERN:
                    hdp_set = set(s.get('handicap') for s in bm_snaps
                                  if s.get('handicap') is not None)
                    feats = extract_pattern_features(candles,
                                                      max(0, len(hdp_set) - 1))
                    if feats:
                        all_patterns[ktype] = {
                            'features': feats,
                            'tags': classify_pattern(feats),
                        }

        # 2. 皇冠vs澳门跨机构分歧
        crown = asia_w.get('crown', [])
        macau = asia_w.get('macau', [])
        if crown and macau:
            cross = _align_and_calc_cross(crown, macau)
            if cross:
                candles = aggregate_ohlc(cross, window)
                ktype = 'div_cross_crown_macau'
                all_klines[wkey][ktype] = candles

                if window == 60 and len(candles) >= MIN_CANDLES_FOR_PATTERN:
                    feats = extract_pattern_features(candles)
                    if feats:
                        all_patterns[ktype] = {
                            'features': feats,
                            'tags': classify_pattern(feats),
                        }

        # 3. 欧赔离散度（bisect二分查找，避免O(n²)）
        if euro_w:
            # 预建每个bookmaker的时间索引
            euro_indexed = {}
            for bm, bm_snaps in euro_w.items():
                times = [s['time'] for s in bm_snaps]
                euro_indexed[bm] = (times, bm_snaps)

            all_times = sorted(set(
                s['time'] for slist in euro_w.values() for s in slist
            ))
            disp_values = []
            for t in all_times:
                odds_at_t = []
                for bm, (times, bm_snaps) in euro_indexed.items():
                    idx = bisect.bisect_left(times, t)
                    # 取最近的（idx或idx-1中gap更小的）
                    candidates = []
                    if idx < len(times):
                        candidates.append(bm_snaps[idx])
                    if idx > 0:
                        candidates.append(bm_snaps[idx - 1])
                    if not candidates:
                        continue
                    closest = min(candidates,
                                  key=lambda s: abs((s['time'] - t).total_seconds()))
                    if all(closest.get(k) for k in ['home_win', 'draw', 'away_win']):
                        odds_at_t.append((closest['home_win'], closest['draw'],
                                          closest['away_win']))
                if len(odds_at_t) >= 2:
                    d = euro_dispersion(odds_at_t)
                    disp_values.append({'time': t, 'value': d})

            if disp_values:
                candles = aggregate_ohlc(disp_values, window)
                ktype = 'euro_dispersion'
                all_klines[wkey][ktype] = candles

                if window == 60 and len(candles) >= MIN_CANDLES_FOR_PATTERN:
                    feats = extract_pattern_features(candles)
                    if feats:
                        all_patterns[ktype] = {
                            'features': feats,
                            'tags': classify_pattern(feats),
                        }

    return {
        'match_id': match_id,
        'klines': all_klines,
        'patterns': all_patterns,
    }


# ═══════════════════════════════════════════════════════════════════════
#  数据库读写
# ═══════════════════════════════════════════════════════════════════════

async def fetch_timeline(conn, since: datetime,
                          match_ids: List[str] = None) -> Dict[str, List[Dict]]:
    """从odds_timeline读取快照，按match_id分组"""
    if match_ids:
        rows = await conn.fetch("""
            SELECT match_id, bookmaker, market_type, odds_type,
                   handicap, home_odds, away_odds, home_win, draw, away_win,
                   snapshot_time, recorded_at
            FROM odds_timeline
            WHERE snapshot_time >= $1::timestamptz
              AND match_id = ANY($2::varchar[])
            ORDER BY match_id, snapshot_time ASC
        """, since, match_ids)
    else:
        rows = await conn.fetch("""
            SELECT match_id, bookmaker, market_type, odds_type,
                   handicap, home_odds, away_odds, home_win, draw, away_win,
                   snapshot_time, recorded_at
            FROM odds_timeline
            WHERE snapshot_time >= $1::timestamptz
            ORDER BY match_id, snapshot_time ASC
        """, since)

    by_match = defaultdict(list)
    for r in rows:
        by_match[r['match_id']].append({
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
            'snapshot_time': r['snapshot_time'],
            'recorded_at': r['recorded_at'],
        })
    return by_match


async def fetch_matches_info(conn, since: datetime) -> Dict[str, Dict]:
    """读取比赛信息（开赛时间、比分、状态）"""
    rows = await conn.fetch("""
        SELECT match_id, league, home_team, away_team,
               home_score, away_score, match_time, status
        FROM matches
        WHERE match_time >= $1::timestamp - interval '6 hours'
          AND match_time < (CURRENT_DATE + interval '2 day')::timestamp
        ORDER BY match_time DESC
    """, since)

    return {
        r['match_id']: {
            'match_id': r['match_id'],
            'league': r['league'],
            'home_team': r['home_team'],
            'away_team': r['away_team'],
            'home_score': r['home_score'],
            'away_score': r['away_score'],
            'match_time': r['match_time'],
            'status': r['status'],
        }
        for r in rows
    }


async def write_klines(conn, kline_rows: List[Dict]):
    """批量upsert K线缓存"""
    count = 0
    for r in kline_rows:
        try:
            await conn.execute("""
                INSERT INTO kline_cache
                    (match_id, kline_type, window_minutes, bucket_time,
                     open, high, low, close, volume)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (match_id, kline_type, window_minutes, bucket_time)
                DO UPDATE SET open=$5, high=$6, low=$7, close=$8,
                              volume=$9, aggregated_at=NOW()
            """, r['match_id'], r['kline_type'], r['window_minutes'],
                r['bucket_time'], r['open'], r['high'], r['low'],
                r['close'], r.get('volume', 0))
            count += 1
        except Exception as e:
            logger.warning(f"kline write error: {e}")
    return count


async def write_patterns(conn, pattern_rows: List[Dict]):
    """批量upsert形态特征"""
    import json
    count = 0
    for r in pattern_rows:
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
            """, r['pattern_type'], r['match_id'],
                r.get('bookmaker', 'market'),
                json.dumps(r['features']),
                r.get('home_score'), r.get('away_score'),
                r.get('handicap_result'), r.get('total_goals'),
                0.5, labeled)
            count += 1
        except Exception as e:
            logger.warning(f"pattern write error: {e}")
    return count


async def clear_stale_klines(conn, since: datetime):
    """删除时间窗口内的旧K线（避免全量重跑时重复）"""
    result = await conn.execute("""
        DELETE FROM kline_cache
        WHERE bucket_time >= $1::timestamptz
    """, since)
    logger.info(f"Cleared stale klines: {result}")


# ═══════════════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════════════

async def run(hours: int = 12, full: bool = False):
    conn = await asyncpg.connect(DSN)
    try:
        if full:
            since = datetime(2026, 1, 1)
            logger.info(f"FULL rebuild from {since}")
        else:
            since = datetime.utcnow() - timedelta(hours=hours)
            logger.info(f"Incremental aggregation since {since}")

        # 1. 读取比赛信息
        matches_info = await fetch_matches_info(conn, since)
        logger.info(f"Matches in window: {len(matches_info)}")

        # 2. 读取timeline快照
        by_match = await fetch_timeline(conn, since)
        logger.info(f"Matches with timeline data: {len(by_match)}")
        total_snaps = sum(len(v) for v in by_match.values())
        logger.info(f"Total snapshots: {total_snaps}")

        if not by_match:
            logger.info("No timeline data, exiting")
            return

        # 3. 全量重跑时清除旧K线
        if full:
            await clear_stale_klines(conn, since)

        # 4. 逐场处理
        kline_rows = []
        pattern_rows = []
        matches_processed = 0

        for match_id, snaps in by_match.items():
            minfo = matches_info.get(match_id)
            result = process_match(snaps, match_info=minfo)
            matches_processed += 1

            if matches_processed % 50 == 0:
                logger.info(f"  Processing... {matches_processed}/{len(by_match)} "
                            f"({len(kline_rows)} candles so far)")

            # 收集K线行
            for wkey, ktypes in result['klines'].items():
                window = int(wkey.replace('min', ''))
                for ktype, candles in ktypes.items():
                    for c in candles:
                        kline_rows.append({
                            'match_id': match_id,
                            'kline_type': ktype,
                            'window_minutes': window,
                            'bucket_time': c['bucket_time'],
                            'open': c['open'],
                            'high': c['high'],
                            'low': c['low'],
                            'close': c['close'],
                            'volume': c.get('volume', 0),
                        })

            # 收集形态行（完赛的标注赛果）
            for ktype, pdata in result['patterns'].items():
                feats = pdata['features']
                tags = pdata['tags']

                row = {
                    'pattern_type': ktype,
                    'match_id': match_id,
                    'bookmaker': ('crown' if 'crown' in ktype
                                  else 'macau' if 'macau' in ktype
                                  else 'market'),
                    'features': {**feats, 'tags': tags},
                }

                if minfo and minfo.get('home_score') is not None:
                    hs, as_ = minfo['home_score'], minfo['away_score']
                    row['home_score'] = hs
                    row['away_score'] = as_
                    row['total_goals'] = hs + as_

                    # 终盘盘口结算
                    final_hdp = None
                    for s in snaps:
                        if (s['bookmaker'] == 'crown'
                                and s['market_type'] == 'asia'
                                and s.get('handicap') is not None):
                            final_hdp = s['handicap']
                    if final_hdp is not None:
                        row['handicap_result'] = settle_handicap(
                            hs, as_, final_hdp)

                    row['labeled'] = True
                else:
                    row['labeled'] = False

                pattern_rows.append(row)

        # 5. 写入数据库
        logger.info(f"Writing {len(kline_rows)} klines...")
        kc = await write_klines(conn, kline_rows)
        logger.info(f"  kline_cache: {kc} rows")

        logger.info(f"Writing {len(pattern_rows)} patterns...")
        pc = await write_patterns(conn, pattern_rows)
        logger.info(f"  pattern_library: {pc} rows")

        # 6. 统计
        tag_dist = defaultdict(int)
        for p in pattern_rows:
            for tag in p['features'].get('tags', []):
                tag_dist[tag] += 1

        logger.info("━" * 50)
        logger.info(f"Matches: {matches_processed}")
        logger.info(f"Snapshots: {total_snaps}")
        logger.info(f"Candles: {len(kline_rows)}")
        logger.info(f"Patterns: {len(pattern_rows)}")
        logger.info(f"Labeled: {sum(1 for p in pattern_rows if p.get('labeled'))}")
        logger.info(f"Tags: {dict(tag_dist)}")
        logger.info("━" * 50)

    finally:
        await conn.close()


def main():
    import sys
    hours = 12
    full = False

    if '--full' in sys.argv:
        full = True
    if '--hours' in sys.argv:
        idx = sys.argv.index('--hours')
        if idx + 1 < len(sys.argv):
            hours = int(sys.argv[idx + 1])

    asyncio.run(run(hours=hours, full=full))


if __name__ == '__main__':
    main()
