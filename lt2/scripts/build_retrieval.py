#!/usr/bin/env python3
"""
build_retrieval.py — LT2 检索引擎固化数据（纯 SQLite，不依赖 PG）
=====================================================================
产出: /opt/ruipan/l3_project/lt2/data/retrieval.json
日志: stdout + /opt/ruipan/l3_project/lt2/logs/

用法:
  python3 build_retrieval.py                # 正常构建
  python3 build_retrieval.py --diag         # 诊断模式
  python3 build_retrieval.py --region am    # 仅构建 AM

数据源（只读）：
  SQLite  lottery_raw/lottery_{am,om,hk}.db  — 开奖事实 (draws)
  SQLite  lottery_raw/solid_ema.db           — HIT/OMIT EMA (hit_segments, omit_segments)

口径：
  - 生肖轴 ZXO=[马,蛇,龙,兔,虎,牛,鼠,猪,狗,鸡,猴,羊], (num-1)%12
  - 波色6段=[红单,红双,蓝单,蓝双,绿单,绿双]
  - 五行5段=[金,木,水,火,土] (2026马年固定映射,与生产链一致)
  - 头数5段: num//10 → [0,1,2,3,4]
  - 尾数10段: num%10 → [0..9]
  - 平特(pt)=号位1-7(7票), 平码(pm)=号位1-6(6票)
  - 命中侧: 每号位投 EMA 最高段; 遗漏侧: 每号位投 EMA 最低段
  - 全部严格 T-1 (用 solid_ema.db, source_id 索引)
"""

import json, os, sys, sqlite3, time, traceback
import logging
from datetime import datetime
from collections import Counter, defaultdict
from pathlib import Path

# ═══════════════════════════════════════════════════════════
# 路径
# ═══════════════════════════════════════════════════════════
RAW_DIR   = Path("/opt/ruipan/lottery_project/lottery_raw")
LT2_DIR   = Path("/opt/ruipan/l3_project/lt2")
DATA_DIR  = LT2_DIR / "data"
LOG_DIR   = LT2_DIR / "logs"
SOLID_DB  = RAW_DIR / "solid_ema.db"

REGIONS  = ["am", "om", "hk"]
WINDOW   = 50       # detail 覆盖期数
EXTRA    = 10       # 额外多取（下期验证用）
FETCH_N  = WINDOW + EXTRA

# ═══════════════════════════════════════════════════════════
# 维度定义
# ═══════════════════════════════════════════════════════════
ZXO    = ["马","蛇","龙","兔","虎","牛","鼠","猪","狗","鸡","猴","羊"]
BOSE6  = ["红单","红双","蓝单","蓝双","绿单","绿双"]
WX5    = ["金","木","水","火","土"]
HEAD5  = ["0","1","2","3","4"]
TAIL10 = [str(i) for i in range(10)]

DIM_CFG = {
    "zodiac": {"names": ZXO,    "top": 4, "n_seg": 12},
    "bose":   {"names": BOSE6,  "top": 4, "n_seg": 6},
    "wuxing": {"names": WX5,    "top": 3, "n_seg": 5},
    "head":   {"names": HEAD5,  "top": 3, "n_seg": 5},
    "tail":   {"names": TAIL10, "top": 1, "n_seg": 10},
}

# ── 号码属性函数（固定轴，与生产链一致）──
_RED  = frozenset([1,2,7,8,12,13,18,19,23,24,29,30,34,35,40,45,46])
_BLUE = frozenset([3,4,9,10,14,15,20,25,26,31,36,37,41,42,47,48])

def bose_idx(n):
    if n in _RED:  return 0 if n % 2 == 1 else 1
    if n in _BLUE: return 2 if n % 2 == 1 else 3
    return 4 if n % 2 == 1 else 5

# 五行（2026马年值年固定映射，与 build_omission_ema 生产链一致）
_WX = {}
for _nm, _ns in [("金",[1,8,9,22,23,30,31,38,39]),
                  ("木",[2,12,13,20,21,34,35,42,43]),
                  ("水",[3,10,11,18,19,26,27,40,41,48,49]),
                  ("火",[4,6,7,14,15,28,29,36,37,44,45]),
                  ("土",[5,16,17,24,25,32,33,46,47])]:
    for _v in _ns:
        _WX[_v] = WX5.index(_nm)

def zodiac_idx(n): return (n - 1) % 12
def wuxing_idx(n): return _WX.get(n, 0)
def head_idx(n):   return n // 10
def tail_idx(n):   return n % 10

ATTR_FN = {
    "zodiac": zodiac_idx,
    "bose":   bose_idx,
    "wuxing": wuxing_idx,
    "head":   head_idx,
    "tail":   tail_idx,
}

# ═══════════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════════
LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("build_retrieval")
log.setLevel(logging.DEBUG)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_fh = logging.FileHandler(
    LOG_DIR / f"build_retrieval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    encoding="utf-8")
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
log.addHandler(_fh)
log.addHandler(_sh)


# ═══════════════════════════════════════════════════════════
# 数据读取
# ═══════════════════════════════════════════════════════════
def load_draws(region):
    """读取某彩种全量有效开奖，按 source_id 升序。"""
    db = RAW_DIR / f"lottery_{region}.db"
    if not db.exists():
        log.error(f"开奖库不存在: {db}")
        return []
    conn = sqlite3.connect(str(db))
    rows = conn.execute("""
        SELECT source_id, draw_date, period_no, year,
               n1, n2, n3, n4, n5, n6, special
        FROM draws WHERE is_valid = 1
        ORDER BY source_id ASC
    """).fetchall()
    conn.close()
    cols = ["source_id","draw_date","period_no","year",
            "n1","n2","n3","n4","n5","n6","special"]
    return [dict(zip(cols, r)) for r in rows]


def load_ema(side, region, source_ids):
    """
    从 solid_ema.db 加载 hit/omit segments。
    side: 'hit' 或 'omit'
    返回: {(source_id, position, dimension, segment_idx): ema_value}
    只取 position 1-7。
    """
    table = f"{side}_segments"
    conn = sqlite3.connect(str(SOLID_DB))
    ph = ",".join(["?"] * len(source_ids))
    sql = f"""
        SELECT source_id, position, dimension, segment_idx, ema
        FROM {table}
        WHERE region = ? AND source_id IN ({ph})
              AND position BETWEEN 1 AND 7
    """
    params = [region] + list(source_ids)
    data = {}
    for sid, pos, dim, seg, ema in conn.execute(sql, params):
        data[(sid, pos, dim, seg)] = ema
    conn.close()
    return data


def period_label(draw):
    """格式化 YYYY-NNN。"""
    yr = draw["year"]
    pno = str(draw["period_no"])
    yr_s = str(yr)
    if pno.startswith(yr_s) and len(pno) > len(yr_s):
        seq = pno[len(yr_s):]
    else:
        seq = pno
    return f"{yr}-{seq}"


# ═══════════════════════════════════════════════════════════
# 核心计算
# ═══════════════════════════════════════════════════════════
def gather_pos(hit, omit, sid, positions, dim):
    """
    收集某期某维度各号位的 EMA 字典。
    返回 (hit_by_pos, omit_by_pos): 各为 {pos: {seg_idx: ema}}
    """
    n_seg = DIM_CFG[dim]["n_seg"]
    h = defaultdict(dict)
    o = defaultdict(dict)
    for pos in positions:
        for seg in range(n_seg):
            v = hit.get((sid, pos, dim, seg))
            if v is not None:
                h[pos][seg] = v
            v = omit.get((sid, pos, dim, seg))
            if v is not None:
                o[pos][seg] = v
    return h, o


def mean_top(hit_bp, omit_bp, positions, dim):
    """均值 TOP：每段跨号位取均值，降序取 TOP。"""
    cfg = DIM_CFG[dim]
    names, top_n, n_seg = cfg["names"], cfg["top"], cfg["n_seg"]
    np_ = len(positions)

    def _calc(data_bp):
        vals = []
        for seg in range(n_seg):
            s = sum(data_bp[p].get(seg, 0.0) for p in positions)
            vals.append((seg, s / np_ if np_ else 0.0))
        vals.sort(key=lambda x: -x[1])
        return [{"name": names[seg], "ema": round(v, 6), "rank": i+1}
                for i, (seg, v) in enumerate(vals[:top_n])]

    return _calc(hit_bp), _calc(omit_bp)


def vote_top(hit_bp, omit_bp, positions, dim):
    """
    投票 TOP：每号位投 1 票。
    hit → EMA 最高段; omit → EMA 最低段。
    排序：票数降序 → 组内均值降序。
    返回 (vote_hit_top, vote_omit_top): [{name, count, rank, _seg}, ...]
    """
    cfg = DIM_CFG[dim]
    names, top_n = cfg["names"], cfg["top"]

    def _vote(data_bp, mode):
        counter = Counter()
        ema_sum = defaultdict(float)
        ema_cnt = defaultdict(int)
        for pos in positions:
            if not data_bp[pos]:
                continue
            if mode == "hit":
                best = max(data_bp[pos], key=data_bp[pos].get)
            else:
                best = min(data_bp[pos], key=data_bp[pos].get)
            counter[best] += 1
            ema_sum[best] += data_bp[pos][best]
            ema_cnt[best] += 1

        ranked = sorted(
            counter.keys(),
            key=lambda s: (-counter[s],
                           -(ema_sum[s] / ema_cnt[s] if ema_cnt[s] else 0)))
        return [{"name": names[seg], "count": counter[seg], "rank": i+1, "_seg": seg}
                for i, seg in enumerate(ranked[:top_n])]

    return _vote(hit_bp, "hit"), _vote(omit_bp, "omit")


def next_period_stats(next_draw, top_segs, dim, positions):
    """
    计算下期验证统计。
    返回 (hit_count, special_hit_or_none)
    """
    fn = ATTR_FN[dim]
    nums = [next_draw[f"n{i+1}"] for i in range(6)]
    is_pt = (max(positions) == 7)
    if is_pt:
        nums.append(next_draw["special"])
    seg_set = set(top_segs)
    cnt = sum(1 for n in nums if fn(n) in seg_set)
    sp_hit = fn(next_draw["special"]) in seg_set if is_pt else None
    return cnt, sp_hit


def build_fixed(draws, hit, omit, positions):
    """构建 fixed 部分（全期）。"""
    is_pt = (max(positions) == 7)
    sid_to_idx = {d["source_id"]: i for i, d in enumerate(draws)}

    # 有 EMA 数据的 source_ids
    ema_sids = set()
    for k in hit: ema_sids.add(k[0])
    for k in omit: ema_sids.add(k[0])
    valid_sids = sorted(s for s in ema_sids if s in sid_to_idx)

    res = {
        "sixiao_mean_hit": [], "sixiao_mean_omit": [],
        "sixiao_vote_hit": [], "sixiao_vote_omit": [],
        "wx_vote_hit": [], "wx_vote_omit": [],
        "head_vote_hit": [], "head_vote_omit": [],
        "bose_vote_hit": [], "bose_vote_omit": [],
    }

    for sid in valid_sids:
        idx = sid_to_idx[sid]
        d = draws[idx]
        per = period_label(d)
        dt = d["draw_date"]
        nd = draws[idx + 1] if idx + 1 < len(draws) else None

        # ── 生肖 ──
        hbp, obp = gather_pos(hit, omit, sid, positions, "zodiac")
        mh, mo = mean_top(hbp, obp, positions, "zodiac")
        res["sixiao_mean_hit"].append({"period": per, "date": dt, "top4": mh})
        res["sixiao_mean_omit"].append({"period": per, "date": dt, "top4": mo})

        vh, vo = vote_top(hbp, obp, positions, "zodiac")
        for label, vtop in [("hit", vh), ("omit", vo)]:
            entry = {"period": per, "date": dt,
                     "votes": [{k: v for k, v in e.items() if k != "_seg"} for e in vtop]}
            if nd:
                segs = [e["_seg"] for e in vtop]
                cnt, sp = next_period_stats(nd, segs, "zodiac", positions)
                entry["next_hit_count"] = cnt
                if is_pt:
                    entry["next_special_hit"] = sp
            else:
                entry["next_hit_count"] = None
                if is_pt:
                    entry["next_special_hit"] = None
            res[f"sixiao_vote_{label}"].append(entry)

        # ── 五行/头/波 ──
        for dim, key_pfx in [("wuxing", "wx"), ("head", "head"), ("bose", "bose")]:
            hbp, obp = gather_pos(hit, omit, sid, positions, dim)
            vh, vo = vote_top(hbp, obp, positions, dim)
            for label, vtop in [("hit", vh), ("omit", vo)]:
                entry = {"period": per, "date": dt,
                         "votes": [{k: v for k, v in e.items() if k != "_seg"} for e in vtop]}
                if nd:
                    segs = [e["_seg"] for e in vtop]
                    cnt, sp = next_period_stats(nd, segs, dim, positions)
                    entry["next_hit_count"] = cnt
                    if is_pt:
                        entry["next_special_hit"] = sp
                else:
                    entry["next_hit_count"] = None
                    if is_pt:
                        entry["next_special_hit"] = None
                res[f"{key_pfx}_vote_{label}"].append(entry)

    # 反转为最新期在前
    for k in res:
        res[k].reverse()
    return res


def build_detail(draws, hit, omit):
    """构建 detail 部分（近 WINDOW 期，逐号位逐维度）。"""
    recent = draws[-WINDOW:] if len(draws) > WINDOW else draws[:]

    detail = {}
    for dim in DIM_CFG:
        cfg = DIM_CFG[dim]
        n_seg = cfg["n_seg"]
        pos_data = []

        for pos in range(1, 8):
            periods = []
            for d in recent:
                sid = d["source_id"]
                ema_h = []
                ema_o = []
                for seg in range(n_seg):
                    vh = hit.get((sid, pos, dim, seg))
                    vo = omit.get((sid, pos, dim, seg))
                    ema_h.append(round(vh, 6) if vh is not None else None)
                    ema_o.append(round(vo, 6) if vo is not None else None)

                vh_valid = [(i, v) for i, v in enumerate(ema_h) if v is not None]
                vo_valid = [(i, v) for i, v in enumerate(ema_o) if v is not None]
                top_h = max(vh_valid, key=lambda x: x[1])[0] if vh_valid else None
                top_o = min(vo_valid, key=lambda x: x[1])[0] if vo_valid else None

                periods.append({
                    "period": period_label(d),
                    "date": d["draw_date"],
                    "ema_hit": ema_h,
                    "ema_omit": ema_o,
                    "top_hit": top_h,
                    "top_omit": top_o,
                })
            pos_data.append({"pos": pos, "periods": periods})

        detail[dim] = {"positions": pos_data}
    return detail


def build_draws_section(draws):
    """构建 draws 数组（全量升序）。"""
    out = []
    for d in draws:
        sp = d["special"]
        out.append({
            "period":  period_label(d),
            "date":    d["draw_date"],
            "n1": d["n1"], "n2": d["n2"], "n3": d["n3"],
            "n4": d["n4"], "n5": d["n5"], "n6": d["n6"],
            "special": sp,
            "zodiac":  ZXO[zodiac_idx(sp)],
            "bose":    BOSE6[bose_idx(sp)],
            "wuxing":  WX5[wuxing_idx(sp)],
            "head":    str(head_idx(sp)),
            "tail":    str(tail_idx(sp)),
        })
    return out


# ═══════════════════════════════════════════════════════════
# 诊断
# ═══════════════════════════════════════════════════════════
def diagnose():
    print("=" * 60)
    print("DIAGNOSTIC")
    print("=" * 60)

    # solid_ema.db
    print(f"\n── solid_ema.db: {SOLID_DB} ──")
    if not SOLID_DB.exists():
        print("  NOT FOUND!"); return
    conn = sqlite3.connect(str(SOLID_DB))
    for tbl, in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
        print(f"  {tbl}: {cnt} rows, cols={cols}")
        s = conn.execute(f"SELECT * FROM {tbl} LIMIT 1").fetchone()
        if s: print(f"    sample: {s}")
        # dimensions
        for c in cols:
            if c in ("dimension", "dim"):
                vals = [r[0] for r in conn.execute(f"SELECT DISTINCT {c} FROM {tbl}").fetchall()]
                print(f"    {c} values: {vals}")
        # region
        if "region" in cols:
            vals = [r[0] for r in conn.execute(f"SELECT DISTINCT region FROM {tbl}").fetchall()]
            print(f"    region: {vals}")
        # position range
        if "position" in cols:
            r = conn.execute(f"SELECT MIN(position), MAX(position) FROM {tbl}").fetchone()
            print(f"    position: {r[0]}~{r[1]}")
        # source_id range
        if "source_id" in cols:
            r = conn.execute(f"SELECT MIN(source_id), MAX(source_id) FROM {tbl}").fetchone()
            print(f"    source_id: {r[0]}~{r[1]}")
    conn.close()

    # draws
    for rg in REGIONS:
        db = RAW_DIR / f"lottery_{rg}.db"
        print(f"\n── lottery_{rg}.db ──")
        if not db.exists():
            print("  NOT FOUND!"); continue
        conn = sqlite3.connect(str(db))
        cnt = conn.execute("SELECT COUNT(*) FROM draws WHERE is_valid=1").fetchone()[0]
        latest = conn.execute(
            "SELECT source_id, period_no, draw_date FROM draws WHERE is_valid=1 ORDER BY source_id DESC LIMIT 1"
        ).fetchone()
        print(f"  valid: {cnt}, latest: {latest}")
        conn.close()


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════
def main():
    diag = "--diag" in sys.argv
    region_filter = None
    for a in sys.argv[1:]:
        if a.startswith("--region"):
            parts = a.split("=", 1)
            if len(parts) == 2:
                region_filter = parts[1].split(",")
            elif sys.argv.index(a) + 1 < len(sys.argv):
                region_filter = sys.argv[sys.argv.index(a) + 1].split(",")

    if diag:
        diagnose()
        return 0

    t0 = time.time()
    log.info("=" * 60)
    log.info("build_retrieval.py 开始（纯 SQLite）")
    log.info(f"  solid_ema.db: {SOLID_DB}")
    log.info(f"  output: {DATA_DIR / 'retrieval.json'}")

    if not SOLID_DB.exists():
        log.error(f"solid_ema.db 不存在: {SOLID_DB}")
        return 1

    output = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "n": 3,
        "window": WINDOW,
        "regions": {},
    }

    target_regions = region_filter or REGIONS

    for rg in target_regions:
        rg = rg.strip()
        log.info(f"\n{'='*40}")
        log.info(f"Region: {rg.upper()}")
        t1 = time.time()

        # 1. 开奖
        draws = load_draws(rg)
        if not draws:
            log.warning(f"{rg}: 无开奖数据，跳过")
            continue
        log.info(f"  开奖: {len(draws)} 期, 最新 sid={draws[-1]['source_id']}, "
                 f"period={period_label(draws[-1])}")

        # 2. 加载 EMA（最新 FETCH_N 期）
        sids = [d["source_id"] for d in draws[-FETCH_N:]]
        log.info(f"  加载 EMA: {len(sids)} 期 ({sids[0]}..{sids[-1]})")

        hit   = load_ema("hit",   rg, sids)
        omit  = load_ema("omit",  rg, sids)
        log.info(f"  HIT  rows: {len(hit)}")
        log.info(f"  OMIT rows: {len(omit)}")

        # 3. draws 部分
        draws_sec = build_draws_section(draws)

        # 4. fixed（平特 + 平码）
        log.info(f"  计算 fixed ...")
        pt_positions = [1,2,3,4,5,6,7]
        pm_positions = [1,2,3,4,5,6]
        fixed_pt = build_fixed(draws, hit, omit, pt_positions)
        fixed_pm = build_fixed(draws, hit, omit, pm_positions)

        for gn, gd in [("pingte", fixed_pt), ("pingma", fixed_pm)]:
            total = sum(len(v) for v in gd.values())
            log.info(f"    {gn}: {total} entries / {len(gd)} keys")

        # 5. detail
        log.info(f"  计算 detail (近 {WINDOW} 期) ...")
        detail = build_detail(draws, hit, omit)
        for dim in detail:
            n_pos = len(detail[dim]["positions"])
            n_per = len(detail[dim]["positions"][0]["periods"]) if n_pos else 0
            log.info(f"    {dim}: {n_pos} pos × {n_per} periods")

        # 6. 组装
        last = draws[-1]
        output["regions"][rg] = {
            "last": {"year": last["year"], "period": period_label(last)},
            "draws": draws_sec,
            "fixed": {"pingte": fixed_pt, "pingma": fixed_pm},
            "detail": detail,
        }
        log.info(f"  {rg} 完成 ({time.time()-t1:.1f}s)")

    # 7. 写入
    out_path = DATA_DIR / "retrieval.json"
    log.info(f"\n写入 {out_path} ...")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    fsize = out_path.stat().st_size
    log.info(f"  文件大小: {fsize:,} bytes ({fsize/1024/1024:.1f} MB)")

    # 8. 摘要
    for rg in target_regions:
        rg = rg.strip()
        if rg not in output["regions"]:
            continue
        rdata = output["regions"][rg]
        n_dr = len(rdata["draws"])
        log.info(f"\n  {rg.upper()} 摘要:")
        log.info(f"    开奖: {n_dr} 期")
        log.info(f"    最新: {rdata['last']['period']}")
        for gn in ["pingte", "pingma"]:
            gd = rdata["fixed"][gn]
            for k, v in gd.items():
                log.info(f"    {gn}.{k}: {len(v)} 期")
        # 最新投票样例
        log.info(f"\n  最新投票样例 ({rg.upper()} 平特):")
        for key in ["sixiao_vote_hit", "wx_vote_hit", "bose_vote_hit"]:
            entries = rdata["fixed"]["pingte"].get(key, [])
            if entries:
                e = entries[0]
                log.info(f"    {key}: {e['period']} → {e['votes']}")
                log.info(f"      next_hit_count={e.get('next_hit_count')}, "
                         f"next_special_hit={e.get('next_special_hit')}")

    # 9. 设置属主
    try:
        import pwd, grp
        uid = pwd.getpwnam("postgres").pw_uid
        gid = grp.getgrnam("postgres").gr_gid
        os.chown(str(out_path), uid, gid)
        log.info(f"属主已设为 postgres:postgres")
    except (KeyError, PermissionError, OSError) as e:
        log.warning(f"设置属主跳过: {e}")

    log.info(f"\n总耗时: {time.time()-t0:.1f}s ✓")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log.error(f"FATAL: {e}\n{traceback.format_exc()}")
        sys.exit(1)
