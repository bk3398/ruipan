#!/usr/bin/env python3
"""
API层封盘脏数据过滤补丁 v2
过滤范围：
- 亚盘: home_odds/away_odds 必须在 [0.5, 2.0]
- 欧赔: LEAST(home_win, draw, away_win) 最低赔率必须在 [1.0, 3.0]
脏数据（封盘归零/极端值）被SQL层过滤，DISTINCT ON自动回退到initial。
"""
import shutil, datetime, sys

APP = "/opt/ruipan/app.py"

with open(APP, "r") as f:
    code = f.read()

original_size = len(code)
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{APP}.bak_{ts}"
shutil.copy2(APP, bak)
print(f"备份: {bak}")

patches_applied = 0

ASIA_FILTER = "AND home_odds BETWEEN 0.5 AND 2.0 AND away_odds BETWEEN 0.5 AND 2.0"
EURO_FILTER = "AND LEAST(home_win, draw, away_win) BETWEEN 1.0 AND 3.0"

# ============================================================
# 1. odds-timeline euro (L132-135)
# ============================================================
old1 = """        SELECT bookmaker, odds_type, home_win, draw, away_win, recorded_at
        FROM odds_euro WHERE match_id = $1 ORDER BY recorded_at ASC"""
new1 = f"""        SELECT bookmaker, odds_type, home_win, draw, away_win, recorded_at
        FROM odds_euro WHERE match_id = $1
        {EURO_FILTER}
        ORDER BY recorded_at ASC"""
if old1 in code:
    code = code.replace(old1, new1, 1)
    patches_applied += 1
    print("✅ odds-timeline euro: 添加脏数据过滤")
else:
    print("⚠️ odds-timeline euro: 未找到匹配，可能已打过补丁")

# ============================================================
# 2. odds-timeline asia (L136-139)
# ============================================================
old2 = """        SELECT bookmaker, odds_type, handicap, home_odds, away_odds, recorded_at
        FROM odds_asia WHERE match_id = $1 ORDER BY recorded_at ASC"""
new2 = f"""        SELECT bookmaker, odds_type, handicap, home_odds, away_odds, recorded_at
        FROM odds_asia WHERE match_id = $1
        {ASIA_FILTER}
        ORDER BY recorded_at ASC"""
if old2 in code:
    code = code.replace(old2, new2, 1)
    patches_applied += 1
    print("✅ odds-timeline asia: 添加脏数据过滤")
else:
    print("⚠️ odds-timeline asia: 未找到匹配")

# ============================================================
# 3. analysis euro (L183-187)
# ============================================================
old3 = """        SELECT bookmaker, odds_type, home_win, draw, away_win, recorded_at
        FROM odds_euro WHERE match_id = $1
        ORDER BY bookmaker, recorded_at DESC"""
new3 = f"""        SELECT bookmaker, odds_type, home_win, draw, away_win, recorded_at
        FROM odds_euro WHERE match_id = $1
        {EURO_FILTER}
        ORDER BY bookmaker, recorded_at DESC"""
if old3 in code:
    code = code.replace(old3, new3, 1)
    patches_applied += 1
    print("✅ analysis euro: 添加脏数据过滤")
else:
    print("⚠️ analysis euro: 未找到匹配")

# ============================================================
# 4. analysis asia (L189-193)
# ============================================================
old4 = """        SELECT bookmaker, odds_type, handicap, home_odds, away_odds, recorded_at
        FROM odds_asia WHERE match_id = $1
        ORDER BY bookmaker, recorded_at DESC"""
new4 = f"""        SELECT bookmaker, odds_type, handicap, home_odds, away_odds, recorded_at
        FROM odds_asia WHERE match_id = $1
        {ASIA_FILTER}
        ORDER BY bookmaker, recorded_at DESC"""
if old4 in code:
    code = code.replace(old4, new4, 1)
    patches_applied += 1
    print("✅ analysis asia: 添加脏数据过滤")
else:
    print("⚠️ analysis asia: 未找到匹配")

# ============================================================
# 5. odds-quick euro (L727-731) - DISTINCT ON
# ============================================================
old5 = """        SELECT DISTINCT ON (bookmaker) bookmaker, odds_type, home_win, draw, away_win
        FROM odds_euro WHERE match_id = $1
        ORDER BY bookmaker, recorded_at DESC"""
new5 = f"""        SELECT DISTINCT ON (bookmaker) bookmaker, odds_type, home_win, draw, away_win
        FROM odds_euro WHERE match_id = $1
        {EURO_FILTER}
        ORDER BY bookmaker, recorded_at DESC"""
if old5 in code:
    code = code.replace(old5, new5, 1)
    patches_applied += 1
    print("✅ odds-quick euro: 添加脏数据过滤")
else:
    print("⚠️ odds-quick euro: 未找到匹配")

# ============================================================
# 6. odds-quick asia (L733-737) - DISTINCT ON
# ============================================================
old6 = """        SELECT DISTINCT ON (bookmaker) bookmaker, odds_type, handicap, home_odds, away_odds
        FROM odds_asia WHERE match_id = $1
        ORDER BY bookmaker, recorded_at DESC"""
new6 = f"""        SELECT DISTINCT ON (bookmaker) bookmaker, odds_type, handicap, home_odds, away_odds
        FROM odds_asia WHERE match_id = $1
        {ASIA_FILTER}
        ORDER BY bookmaker, recorded_at DESC"""
if old6 in code:
    code = code.replace(old6, new6, 1)
    patches_applied += 1
    print("✅ odds-quick asia: 添加脏数据过滤")
else:
    print("⚠️ odds-quick asia: 未找到匹配")

# ============================================================
# 写入文件
# ============================================================
if patches_applied > 0:
    with open(APP, "w") as f:
        f.write(code)
    new_size = len(code)
    print(f"\n文件大小: {original_size} → {new_size} bytes (diff: {new_size - original_size})")
    print(f"应用补丁数: {patches_applied}")
    print("\n✅ 补丁完成！重启API服务：")
    print("   systemctl restart ruipan-api")
    print("   sleep 2 && systemctl status ruipan-api | head -5")
else:
    print("\n⚠️ 未应用任何补丁，文件未修改")
    sys.exit(1)
