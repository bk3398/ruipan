#!/usr/bin/env python3
"""
Diagnose win rate lookup failures:
1. Extract hdpNameV3, waterBinV3, getCoeff functions
2. Analyze lookup table coverage (sample >= 5)
3. Simulate lookup with real API data patterns
"""
import json, re

html_path = "/opt/ruipan/static/live-scores-preview-v6.html"
lookup_path = "/opt/ruipan/static/backtest_winrate_lookup.json"

with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
    lines = content.split('\n')

# 1. Extract hdpNameV3, waterBinV3, getCoeff
print("=" * 70)
print("FUNCTION DEFINITIONS:")
print("-" * 70)
func_names = ['hdpNameV3', 'waterBinV3', 'getCoeff', 'divgBinV3']
for fname in func_names:
    for i, line in enumerate(lines):
        if f'function {fname}' in line:
            # Print function until closing brace at same indent
            print(f"\n--- {fname} (L{i+1}) ---")
            indent = len(line) - len(line.lstrip())
            for j in range(i, min(i+30, len(lines))):
                print(f"L{j+1}: {lines[j]}")
                if j > i and lines[j].strip() == '}' and (len(lines[j]) - len(lines[j].lstrip())) == indent:
                    break
            break

# 2. Analyze lookup table coverage
print("\n" + "=" * 70)
print("LOOKUP TABLE COVERAGE:")
print("-" * 70)
with open(lookup_path, 'r') as f:
    lookup = json.load(f)

for phase in ['initial', 'live', 'closing']:
    data = lookup.get(phase, {})
    total = len(data)
    ge5 = sum(1 for v in data.values() if v.get('sample', 0) >= 5)
    ge3 = sum(1 for v in data.values() if v.get('sample', 0) >= 3)
    lt5 = sum(1 for v in data.values() if v.get('sample', 0) < 5)
    samples = [v.get('sample', 0) for v in data.values()]
    print(f"\n{phase}: {total} entries total")
    print(f"  sample>=5: {ge5} ({ge5/total*100:.1f}%)")
    print(f"  sample>=3: {ge3} ({ge3/total*100:.1f}%)")
    print(f"  sample<5:  {lt5} ({lt5/total*100:.1f}%)")
    if samples:
        print(f"  sample range: {min(samples)}-{max(samples)}, avg={sum(samples)/len(samples):.1f}")
    
    # Show all entries with sample >= 5
    if ge5 > 0:
        print(f"  Entries with sample>=5:")
        for k, v in sorted(data.items()):
            if v.get('sample', 0) >= 5:
                print(f"    {k}: wr={v['win_rate_upper']*100:.0f}% n={v['sample']}")

# 3. Analyze what handicap names and water levels exist
print("\n" + "=" * 70)
print("HANDICAP NAMES IN LOOKUP (initial):")
print("-" * 70)
hdp_names = set()
water_levels = set()
divg_levels = set()
for k in lookup.get('initial', {}):
    parts = k.split('×')
    if len(parts) == 3:
        hdp_names.add(parts[0])
        water_levels.add(parts[1])
        divg_levels.add(parts[2])
print(f"Handicap names: {sorted(hdp_names)}")
print(f"Water levels: {sorted(water_levels)}")
print(f"Divg levels: {sorted(divg_levels)}")

# 4. Test with real API data patterns from curl output
# crown initial: hdp=1.75, upper=0.81, divg=0.0776
# crown live: hdp=1.5, upper=0.54, divg=0.4903
# pinnacle initial: hdp=1.5, upper=0.82, divg=0.0625
# pinnacle live: hdp=0.5, upper=0.95, divg=0.7344
print("\n" + "=" * 70)
print("SIMULATING LOOKUP WITH REAL DATA:")
print("-" * 70)

# We need to replicate the JS functions in Python
# First let's see what they look like - we'll print them above
# Then manually simulate

# Common handicap name mapping (will be confirmed from JS)
# For now, let's just check what keys would match
test_cases = [
    ('initial', 1.75, 0.81, 0.0776, 'crown initial'),
    ('initial', 1.5, 0.82, 0.0625, 'pinnacle initial'),
    ('initial', 1.5, 0.85, 0.0195, 'wewbet initial'),
    ('initial', 0.5, 0.98, 0.1624, 'yibosheng initial'),
    ('live', 1.5, 0.54, 0.4903, 'crown live'),
    ('live', 0.5, 0.95, 0.7344, 'pinnacle live'),
    ('live', 0.5, 0.56, 0.4832, 'wewbet live'),
    ('live', 0.25, 0.81, 0.2542, 'yibosheng live'),
]

for phase, hdp, water, divg, label in test_cases:
    data = lookup.get(phase, {})
    # We can't know exact key without seeing hdpNameV3/waterBinV3
    # But let's search for partial matches
    hdp_str = str(hdp)
    matches = []
    for k, v in data.items():
        # Check if handicap part could match
        parts = k.split('×')
        if len(parts) == 3:
            # The handicap name in lookup uses Chinese names
            # We'll check if the water and divg bins match
            pass
    print(f"  {label}: hdp={hdp} water={water} divg={divg:.4f}")
    print(f"    (exact key requires JS binning functions - see output above)")

# 5. Check: does the inline BACKTEST_WINRATE_LOOKUP in HTML differ from the JSON file?
print("\n" + "=" * 70)
print("CHECKING INLINE LOOKUP vs JSON FILE:")
print("-" * 70)
# Extract inline JSON
inline_match = re.search(r'const BACKTEST_WINRATE_LOOKUP = (\{.*?\});', content)
if inline_match:
    try:
        inline = json.loads(inline_match.group(1))
        for phase in ['initial', 'live']:
            inline_count = len(inline.get(phase, {}))
            file_count = len(lookup.get(phase, {}))
            print(f"  {phase}: inline={inline_count} entries, file={file_count} entries")
            if inline_count != file_count:
                print(f"    ⚠️ MISMATCH! HTML may be using stale inline data!")
    except:
        print("  Could not parse inline JSON (may be truncated in line)")
else:
    print("  Could not find inline lookup in HTML")
