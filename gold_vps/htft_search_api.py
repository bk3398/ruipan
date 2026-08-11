#!/usr/bin/env python3
"""
半全场进球分级检索 API
━━━━━━━━━━━━━━━━━━━━━━
独立模块，挂载到 /opt/ruipan/app.py。
维度：国家 × 联赛 × 机构 × 盘口 × 上半场比分 × 完场比分
数据源：matches（含 home_ht_score/away_ht_score）+ odds_asia（初盘盘口）
纯客观历史检索，不做预测/推荐。

端点：
  GET /api/htft/options          返回各筛选项的可选值（级联用）
  GET /api/htft/search           按条件检索历史比赛
"""
from fastapi import APIRouter, Query
from typing import Optional

# 模块级连接池，由 app.py 在 lifespan 中注入（与 kline_api 同模式）
_db_pool = None

router = APIRouter(prefix="/api/htft", tags=["htft"])

# 联赛→国家映射（与回测 V4 保持同源；新联赛归入"其他"）
LEAGUE_COUNTRY = {
    "英超": "英格兰", "英冠": "英格兰", "英甲": "英格兰", "英乙": "英格兰",
    "苏超": "苏格兰", "苏冠": "苏格兰",
    "西甲": "西班牙", "西乙": "西班牙", "国王杯": "西班牙",
    "意甲": "意大利", "意乙": "意大利", "德国杯": "德国",
    "德甲": "德国", "德乙": "德国",
    "法甲": "法国", "法乙": "法国",
    "葡超": "葡萄牙", "葡甲": "葡萄牙",
    "荷甲": "荷兰", "荷乙": "荷兰",
    "比甲": "比利时", "比乙": "比利时",
    "土超": "土耳其", "土甲": "土耳其",
    "希超": "希腊", "瑞士超": "瑞士", "奥甲": "奥地利",
    "俄超": "俄罗斯", "俄甲": "俄罗斯",
    "乌超": "乌克兰", "波兰超": "波兰", "捷克甲": "捷克",
    "丹超": "丹麦", "丹甲": "丹麦", "瑞典超": "瑞典", "瑞典甲": "瑞典",
    "挪超": "挪威", "挪甲": "挪威", "芬超": "芬兰", "芬甲": "芬兰",
    "冰岛超": "冰岛", "爱尔兰超": "爱尔兰", "北爱超": "北爱尔兰",
    "威尔士超": "威尔士",
    "中超": "中国", "中甲": "中国", "中乙": "中国", "足协杯": "中国",
    "日职": "日本", "日职乙": "日本", "天皇杯": "日本", "日联杯": "日本",
    "韩K联": "韩国", "韩K2联": "韩国", "韩足总杯": "韩国",
    "澳超": "澳大利亚", "澳昆超": "澳大利亚", "澳维超": "澳大利亚",
    "澳首超": "澳大利亚", "澳威超": "澳大利亚",
    "沙特联": "沙特", "阿联酋超": "阿联酋", "卡塔尔联": "卡塔尔",
    "伊朗超": "伊朗", "乌兹超": "乌兹别克",
    "泰超": "泰国", "越南联": "越南", "新加坡联": "新加坡", "印尼超": "印尼",
    "印度超": "印度", "港超": "中国香港", "台企甲": "中国台湾",
    "美职业": "美国", "美职联": "美国", "美乙": "美国", "美公开杯": "美国",
    "加拿超": "加拿大",
    "墨超": "墨西哥", "墨西甲": "墨西哥",
    "巴西甲": "巴西", "巴西乙": "巴西", "巴塞阿甲": "巴西", "巴戈甲": "巴西",
    "巴米内罗": "巴西", "巴伯南": "巴西", "巴卡德": "巴西", "巴高甲": "巴西",
    "巴圣甲": "巴西", "巴地区": "巴西", "巴西杯": "巴西",
    "阿根廷甲": "阿根廷", "阿乙": "阿根廷", "阿杯": "阿根廷",
    "智利甲": "智利", "哥伦甲": "哥伦比亚", "秘鲁甲": "秘鲁",
    "厄瓜多尔甲": "厄瓜多尔", "乌拉圭甲": "乌拉圭", "巴拉圭甲": "巴拉圭",
    "玻利维亚甲": "玻利维亚", "委超": "委内瑞拉",
    "世界杯": "国际赛", "友谊赛": "国际赛", "欧洲杯": "国际赛",
    "欧国联": "国际赛", "美洲杯": "国际赛", "非洲杯": "国际赛",
    "亚洲杯": "国际赛", "世预赛": "国际赛", "亚冠": "国际赛",
    "欧冠杯": "欧洲", "欧联杯": "欧洲", "欧协联": "欧洲",
    "欧罗巴": "欧洲", "欧冠": "欧洲",
    "解放者杯": "南美", "南球杯": "南美",
    "英非联": "英格兰", "英议南": "英格兰", "英议北": "英格兰",
    "苏挑杯": "苏格兰", "苏联杯": "苏格兰",
    "法联杯": "法国", "法杯": "法国", "意杯": "意大利",
    "西超杯": "西班牙", "英联杯": "英格兰", "社区盾杯": "英格兰",
    "德地区": "德国", "西青U19": "西班牙", "非青U17": "国际赛",
}

# 亚盘 17 档（与回测/前端统一展示文本）
def _handicap_label(h):
    try:
        h = float(h)
    except (TypeError, ValueError):
        return None
    labels = {
        0.0: "平手", 0.25: "平/半", 0.5: "半球", 0.75: "半/一",
        1.0: "一球", 1.25: "一/球半", 1.5: "球半", 1.75: "球半/两",
        2.0: "两球", 2.25: "两/两球半", 2.5: "两球半", 2.75: "两球半/三",
        3.0: "三球", 3.25: "三/三球半", 3.5: "三球半", 3.75: "三球半/四",
        4.0: "四球",
    }
    base = labels.get(abs(h), f"{abs(h)}球")
    return f"客让{base}" if h < 0 else (f"主让{base}" if h > 0 else "平手")


def country_of(league: str) -> str:
    if not league:
        return "其他"
    if league in LEAGUE_COUNTRY:
        return LEAGUE_COUNTRY[league]
    for known, country in LEAGUE_COUNTRY.items():
        if known in league or league in known:
            return country
    return "其他"


def _score_bucket(hs, as_):
    """进球分级：0球/1球/2球/3球/4球/5球/6+球"""
    try:
        total = int(hs) + int(as_)
    except (TypeError, ValueError):
        return None
    if total >= 6:
        return "6+球"

async def _fetch_filters():
    async with _db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT m.league,
                   oa.bookmaker, oa.handicap,
                   m.home_ht_score, m.away_ht_score,
                   m.home_score, m.away_score
            FROM matches m
            LEFT JOIN LATERAL (
                SELECT bookmaker, handicap
                FROM odds_asia
                WHERE match_id = m.match_id AND odds_type = 'initial'
                ORDER BY recorded_at ASC LIMIT 1
            ) oa ON true
            WHERE m.status = 'finished'
              AND m.home_ht_score IS NOT NULL
              AND m.away_ht_score IS NOT NULL
              AND m.home_score IS NOT NULL
              AND m.away_score IS NOT NULL
        """)
    return rows


@router.get("/options")
async def htft_options():
    rows = await _fetch_filters()
    countries, leagues, books, hdps, ht_buckets, ft_buckets = (
        set(), set(), set(), set(), set(), set())
    for r in rows:
        country = country_of(r['league'])
        countries.add(country)
        leagues.add((country, r['league']))
        if r['bookmaker']:
            books.add(r['bookmaker'])
        lab = _handicap_label(r['handicap'])
        if lab:
            hdps.add((float(r['handicap']), lab))
        htb = _score_bucket(r['home_ht_score'], r['away_ht_score'])
        if htb:
            ht_buckets.add(htb)
        ftb = _score_bucket(r['home_score'], r['away_score'])
        if ftb:
            ft_buckets.add(ftb)

    country_map = {}
    for c, lg in leagues:
        country_map.setdefault(c, set()).add(lg)

    return {
        "status": "ok",
        "total": len(rows),
        "countries": sorted(countries),
        "leagues_by_country": {c: sorted(v) for c, v in sorted(country_map.items())},
        "bookmakers": sorted(books),
        "handicaps": [{"value": v, "label": lab} for v, lab in sorted(hdps, key=lambda x: x[0])],
        "ht_buckets": sorted(ht_buckets, key=lambda b: (len(b), b)),
        "ft_buckets": sorted(ft_buckets, key=lambda b: (len(b), b)),
    }


@router.get("/search")
async def htft_search(
    country: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    bookmaker: Optional[str] = Query(None),
    handicap: Optional[float] = Query(None),
    ht_bucket: Optional[str] = Query(None, description="半场总进球分级：0球..6+球"),
    ft_bucket: Optional[str] = Query(None, description="全场总进球分级"),
    ht_score: Optional[str] = Query(None, description="精确半场比分 如 1-0"),
    ft_score: Optional[str] = Query(None, description="精确全场比分 如 2-1"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    sql = """
        SELECT m.match_id, m.league, m.home_team, m.away_team,
               m.home_ht_score, m.away_ht_score,
               m.home_score, m.away_score,
               m.match_time,
               oa.bookmaker, oa.handicap
        FROM matches m
        LEFT JOIN LATERAL (
            SELECT bookmaker, handicap
            FROM odds_asia
            WHERE match_id = m.match_id AND odds_type = 'initial'
            ORDER BY recorded_at ASC LIMIT 1
        ) oa ON true
        WHERE m.status = 'finished'
          AND m.home_ht_score IS NOT NULL AND m.away_ht_score IS NOT NULL
          AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
    """
    args = []
    if league:
        args.append(league); sql += f" AND m.league = ${len(args)}"
    if bookmaker:
        args.append(bookmaker); sql += f" AND oa.bookmaker = ${len(args)}"
    if handicap is not None:
        args.append(handicap); sql += f" AND oa.handicap = ${len(args)}"
    if ht_score and "-" in ht_score:
        h, a = ht_score.split("-", 1)
        args.extend([int(h), int(a)])
        sql += f" AND m.home_ht_score = ${len(args)-1} AND m.away_ht_score = ${len(args)}"
    if ft_score and "-" in ft_score:
        h, a = ft_score.split("-", 1)
        args.extend([int(h), int(a)])
        sql += f" AND m.home_score = ${len(args)-1} AND m.away_score = ${len(args)}"
    if ht_bucket:
        cond = _bucket_sql(ht_bucket, "m.home_ht_score", "m.away_ht_score")
        if cond:
            sql += f" AND {cond}"
    if ft_bucket:
        cond = _bucket_sql(ft_bucket, "m.home_score", "m.away_score")
        if cond:
            sql += f" AND {cond}"

    async with _db_pool.acquire() as conn:
        rows = await conn.fetch(sql + " ORDER BY m.match_time DESC", *args)

    results = []
    for r in rows:
        c = country_of(r['league'])
        if country and c != country:
            continue
        results.append({
            "match_id": r['match_id'],
            "country": c,
            "league": r['league'],
            "home_team": r['home_team'],
            "away_team": r['away_team'],
            "ht_score": f"{r['home_ht_score']}-{r['away_ht_score']}",
            "ft_score": f"{r['home_score']}-{r['away_score']}",
            "ht_total": (r['home_ht_score'] or 0) + (r['away_ht_score'] or 0),
            "ft_total": (r['home_score'] or 0) + (r['away_score'] or 0),
            "match_time": r['match_time'].isoformat() if r['match_time'] else None,
            "bookmaker": r['bookmaker'],
            "handicap": float(r['handicap']) if r['handicap'] is not None else None,
            "handicap_label": _handicap_label(r['handicap']),
        })

    total = len(results)
    results = results[offset:offset + limit]
    return {"status": "ok", "total": total, "count": len(results), "results": results}


def _bucket_sql(bucket: str, hcol: str, acol: str) -> str:
    """把 0球/1球/.../6+球 转成SQL总进球条件。"""
    bucket = bucket.strip()
    if bucket == "6+球":
        return f"(({hcol})::int + ({acol})::int) >= 6"
    if bucket.endswith("球"):
        try:
            n = int(bucket[:-1])
            return f"(({hcol})::int + ({acol})::int) = {n}"
        except ValueError:
            return ""
    return ""
