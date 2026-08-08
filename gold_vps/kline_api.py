#!/usr/bin/env python3
"""
kline_api.py — K线/形态数据API路由
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
纯数据查询，不含任何算法/计算/模型参数。
从 kline_cache 和 pattern_library 表读取数据返回JSON。

部署：在app.py中:
  from kline_api import register_kline_routes
  register_kline_routes(app, db_pool)
"""

import json
from fastapi import APIRouter
from typing import Optional

router = APIRouter()

# 模块级连接池，由 register_kline_routes 注入
_db_pool = None

# K线类型中文映射
KLINE_TYPE_MAP = {
    "div_asia_crown": "皇冠亚盘分歧",
    "div_asia_macau": "澳彩亚盘分歧",
    "div_cross_crown_macau": "皇冠/澳彩跨庄分歧",
    "euro_dispersion": "欧赔离散度",
}

# 形态标签颜色
TAG_COLORS = {
    "盘口坚定": "#4caf50",
    "V型收敛": "#29b6f6",
    "常态波动": "#78909c",
    "分歧扩大": "#ef5350",
    "放量分歧": "#ff5722",
    "尾盘拉升": "#66bb6a",
    "共识形成": "#26c6da",
    "频繁变盘": "#ffa726",
    "尾盘回落": "#ab47bc",
    "上影试探": "#ff7043",
    "缩量企稳": "#8d6e63",
}


@router.get("/api/v1/matches/{fixture_id}/kline")
async def get_kline(fixture_id: str, kline_type: Optional[str] = None):
    """
    获取比赛的K线蜡烛和形态标签数据。

    Query params:
      kline_type: 可选，指定K线类型。不传则返回全部4种。
    """
    if not _db_pool:
        return {"status": "error", "message": "DB pool not available"}

    async with _db_pool.acquire() as conn:
        # 查K线蜡烛
        if kline_type:
            rows = await conn.fetch(
                """SELECT match_id, kline_type, window_minutes, bucket_time,
                          open, high, low, close, volume, extra
                   FROM kline_cache
                   WHERE match_id = $1 AND kline_type = $2
                   ORDER BY bucket_time ASC""",
                fixture_id, kline_type
            )
        else:
            rows = await conn.fetch(
                """SELECT match_id, kline_type, window_minutes, bucket_time,
                          open, high, low, close, volume, extra
                   FROM kline_cache
                   WHERE match_id = $1
                   ORDER BY kline_type, bucket_time ASC""",
                fixture_id
            )

        candles = []
        for r in rows:
            extra = r["extra"]
            if isinstance(extra, str):
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = {}
            candles.append({
                "kline_type": r["kline_type"],
                "window_minutes": r["window_minutes"],
                "bucket_time": r["bucket_time"].isoformat() if r["bucket_time"] else None,
                "open": float(r["open"]) if r["open"] is not None else 0,
                "high": float(r["high"]) if r["high"] is not None else 0,
                "low": float(r["low"]) if r["low"] is not None else 0,
                "close": float(r["close"]) if r["close"] is not None else 0,
                "volume": r["volume"],
                "extra": extra or {},
            })

        # 查形态标签
        pat_rows = await conn.fetch(
            """SELECT pattern_type, match_id, bookmaker, features,
                      home_score, away_score, handicap_result, total_goals,
                      confidence, labeled_at
               FROM pattern_library
               WHERE match_id = $1
               ORDER BY pattern_type""",
            fixture_id
        )

        patterns = []
        for r in pat_rows:
            features = r["features"]
            if isinstance(features, str):
                try:
                    features = json.loads(features)
                except Exception:
                    features = {}
            patterns.append({
                "pattern_type": r["pattern_type"],
                "bookmaker": r["bookmaker"],
                "tags": features.get("tags", []) if features else [],
                "trend": features.get("trend") if features else None,
                "pattern": features.get("pattern") if features else None,
                "amplitude": features.get("amplitude") if features else None,
                "convergence_ratio": features.get("convergence_ratio") if features else None,
                "net_change": features.get("net_change") if features else None,
                "candle_count": features.get("candle_count") if features else None,
                "handicap_changes": features.get("handicap_changes") if features else None,
                "volume_trend": features.get("volume_trend") if features else None,
                "labeled": r["labeled_at"] is not None,
                "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
                "home_score": r["home_score"],
                "away_score": r["away_score"],
                "handicap_result": r["handicap_result"],
                "total_goals": r["total_goals"],
            })

    # 按类型分组蜡烛
    grouped = {}
    for c in candles:
        kt = c["kline_type"]
        if kt not in grouped:
            grouped[kt] = []
        grouped[kt].append(c)

    # 每种类型的元信息
    kline_meta = {}
    for kt, items in grouped.items():
        kline_meta[kt] = {
            "label": KLINE_TYPE_MAP.get(kt, kt),
            "candle_count": len(items),
            "windows": sorted(set(c["window_minutes"] for c in items)),
            "first_time": items[0]["bucket_time"] if items else None,
            "last_time": items[-1]["bucket_time"] if items else None,
        }

    # 形态标签按类型分组
    pat_by_type = {}
    for p in patterns:
        pt = p["pattern_type"]
        if pt not in pat_by_type:
            pat_by_type[pt] = []
        pat_by_type[pt].append(p)

    return {
        "status": "ok",
        "fixture_id": fixture_id,
        "kline_types": kline_meta,
        "candles": grouped,
        "patterns": pat_by_type,
        "tag_colors": TAG_COLORS,
    }


def register_kline_routes(app, db_pool):
    """在FastAPI app上注册K线路由，注入db_pool"""
    global _db_pool
    _db_pool = db_pool
    app.include_router(router)
