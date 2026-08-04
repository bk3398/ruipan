#!/usr/bin/env python3
"""
修复亚盘handicap=0被误判为None的bug
根因: Python中 if 0 为False，导致平手盘(handicap=0)被当成空值
odds-timeline L158: if r['handicap'] else None → if r['handicap'] is not None else None
analysis L226: if r['handicap'] else 0 → if r['handicap'] is not None else 0
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

# 1. odds-timeline asia: handicap=0被误判为None
old1 = "_hcp = float(r['handicap']) if r['handicap'] else None"
new1 = "_hcp = float(r['handicap']) if r['handicap'] is not None else None"
if old1 in code:
    code = code.replace(old1, new1, 1)
    patches_applied += 1
    print("✅ odds-timeline: handicap=0 不再被误判为None")
else:
    print("⚠️ odds-timeline: 未找到匹配")

# 2. analysis asia: 同样的falsy问题（虽然默认值0碰巧正确，但改为is not None更严谨）
old2 = "hcp = float(r['handicap']) if r['handicap'] else 0"
new2 = "hcp = float(r['handicap']) if r['handicap'] is not None else 0"
if old2 in code:
    code = code.replace(old2, new2, 1)
    patches_applied += 1
    print("✅ analysis: handicap判断改为is not None")
else:
    print("⚠️ analysis: 未找到匹配")

# 3. 同样修复 odds-timeline 中的 home_odds/away_odds（0也是falsy但正常水位不会是0，保险起见也改）
old3a = "_ho = float(r['home_odds']) if r['home_odds'] else None"
new3a = "_ho = float(r['home_odds']) if r['home_odds'] is not None else None"
old3b = "_ao = float(r['away_odds']) if r['away_odds'] else None"
new3b = "_ao = float(r['away_odds']) if r['away_odds'] is not None else None"
if old3a in code:
    code = code.replace(old3a, new3a, 1)
    patches_applied += 1
    print("✅ odds-timeline: home_odds判断改为is not None")
if old3b in code:
    code = code.replace(old3b, new3b, 1)
    patches_applied += 1
    print("✅ odds-timeline: away_odds判断改为is not None")

# 4. 同样修复欧赔字段（赔率不会是0，但保持一致性）
for field in ['home_win', 'draw', 'away_win']:
    old = f"_{field[0]}w = float(r['{field}']) if r['{field}'] else None"
    # 实际变量名不同，单独处理
# 直接用更通用的替换
old_euro_hw = "_hw = float(r['home_win']) if r['home_win'] else None"
new_euro_hw = "_hw = float(r['home_win']) if r['home_win'] is not None else None"
old_euro_dr = "_dr = float(r['draw']) if r['draw'] else None"
new_euro_dr = "_dr = float(r['draw']) if r['draw'] is not None else None"
old_euro_aw = "_aw = float(r['away_win']) if r['away_win'] else None"
new_euro_aw = "_aw = float(r['away_win']) if r['away_win'] is not None else None"

for old, new, label in [
    (old_euro_hw, new_euro_hw, "home_win"),
    (old_euro_dr, new_euro_dr, "draw"),
    (old_euro_aw, new_euro_aw, "away_win"),
]:
    if old in code:
        code = code.replace(old, new, 1)
        patches_applied += 1
        print(f"✅ odds-timeline: {label}判断改为is not None")

# 5. analysis端点中的home_odds/away_odds也有同样问题
old_ana_ho = "ho = float(r['home_odds']) if r['home_odds'] else None"
new_ana_ho = "ho = float(r['home_odds']) if r['home_odds'] is not None else None"
old_ana_ao = "ao = float(r['away_odds']) if r['away_odds'] else None"
new_ana_ao = "ao = float(r['away_odds']) if r['away_odds'] is not None else None"

for old, new, label in [
    (old_ana_ho, new_ana_ho, "home_odds"),
    (old_ana_ao, new_ana_ao, "away_odds"),
]:
    if old in code:
        code = code.replace(old, new, 1)
        patches_applied += 1
        print(f"✅ analysis: {label}判断改为is not None")

# 6. analysis端点欧赔字段
for field in ['home_win', 'draw', 'away_win']:
    old = f"'{field}': float(r['{field}']) if r['{field}'] else None,"
    new = f"'{field}': float(r['{field}']) if r['{field}'] is not None else None,"
    if old in code:
        code = code.replace(old, new, 1)
        patches_applied += 1
        print(f"✅ analysis: {field}判断改为is not None")

if patches_applied > 0:
    with open(APP, "w") as f:
        f.write(code)
    new_size = len(code)
    print(f"\n文件大小: {original_size} → {new_size} bytes (diff: {new_size - original_size})")
    print(f"应用补丁数: {patches_applied}")
    print("\n✅ 补丁完成！重启API：")
    print("   systemctl restart ruipan-api")
else:
    print("\n⚠️ 未应用任何补丁")
    sys.exit(1)
