#!/usr/bin/env python3
"""提取VPS HTML中所有render函数的完整代码，检查JS语法错误"""
import re

HTML_PATH = "/opt/ruipan/static/live-scores-preview-v6.html"

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

# Find all script blocks
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
print(f"Found {len(scripts)} script blocks")
# Find the main app script (largest one)
main_script = max(scripts, key=len)
print(f"Main script: {len(main_script)} chars\n")

# Extract specific functions by name
func_names = [
    'loadOddsData',
    'renderAsianTable', 
    'renderEuroTable',
    'renderAnalysisTab',
    'renderFundamentalTab',
    'renderOddsQuickTab',
    'calcUpperDivg',
    'lookupWR',
    'fmtWinRate',
    'fmtHandicap',
]

def extract_function(script, func_name):
    """Extract a complete function by tracking braces"""
    # Match function name = function( or function name( or async function name(
    patterns = [
        f'async function {func_name}(',
        f'function {func_name}(',
        f'{func_name} = function(',
        f'{func_name} = async function(',
        f'const {func_name} = (',
        f'const {func_name} = function(',
        f'const {func_name} = async function(',
        f'let {func_name} = (',
        f'var {func_name} = function(',
    ]
    
    start = -1
    matched_pattern = None
    for p in patterns:
        idx = script.find(p)
        if idx != -1:
            start = idx
            matched_pattern = p
            break
    
    if start == -1:
        return None, f"NOT FOUND"
    
    # Find the opening brace
    brace_start = script.find('{', start)
    if brace_start == -1:
        return None, "NO OPENING BRACE"
    
    # Track braces to find matching close
    depth = 0
    i = brace_start
    in_string = None
    in_template = False
    escape_next = False
    
    while i < len(script):
        c = script[i]
        
        if escape_next:
            escape_next = False
            i += 1
            continue
        
        if c == '\\':
            escape_next = True
            i += 1
            continue
        
        # Handle strings
        if in_string:
            if c == in_string:
                in_string = None
            i += 1
            continue
        
        if c in ('"', "'", '`'):
            in_string = c
            i += 1
            continue
        
        # Handle template literals (backtick handled above as in_string)
        
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return script[start:i+1], f"OK (pattern: {matched_pattern})"
        
        i += 1
    
    return script[start:], "UNCLOSED BRACE!"

for name in func_names:
    code, status = extract_function(main_script, name)
    lines_count = len(code.split('\n')) if code else 0
    print(f"{'='*60}")
    print(f"FUNCTION: {name}  [{status}]  {lines_count} lines, {len(code) if code else 0} chars")
    print(f"{'='*60}")
    if code:
        # Print first 5 and last 10 lines to spot issues without too much output
        lines = code.split('\n')
        if len(lines) <= 20:
            print(code)
        else:
            print('\n'.join(lines[:5]))
            print(f"    ... ({len(lines)-15} lines omitted) ...")
            print('\n'.join(lines[-10:]))
    print()

# Check DOM element template
print(f"{'='*60}")
print("DOM ELEMENT CHECK")
print(f"{'='*60}")
for pat in ['tab-analysis-', 'tab-asian-', 'tab-euro-', 'tab-fund-', 'tab-quick-', 'tab-poisson-']:
    idx = html.find(pat)
    if idx != -1:
        context = html[max(0,idx-30):idx+80].replace('\n',' ')
        print(f"  FOUND '{pat}' at char {idx}: ...{context}...")
    else:
        print(f"  MISSING '{pat}'")

# Check renderMatches for how tabs are created
rm_code, rm_status = extract_function(main_script, 'renderMatches')
if rm_code:
    print(f"\nrenderMatches length: {len(rm_code)} chars")
    # Look for tab-analysis in renderMatches
    if 'tab-analysis' in rm_code:
        idx = rm_code.find('tab-analysis')
        print(f"  'tab-analysis' found in renderMatches at offset {idx}")
        print(f"  context: {rm_code[max(0,idx-80):idx+120]}")
    else:
        print(f"  WARNING: 'tab-analysis' NOT found in renderMatches!")
    # Look for how expand works
    if 'loadOddsData' in rm_code:
        idx = rm_code.find('loadOddsData')
        print(f"\n  'loadOddsData' call context:")
        print(f"  {rm_code[max(0,idx-100):idx+100]}")

# Also search for common error patterns
print(f"\n{'='*60}")
print("POTENTIAL ISSUES SEARCH")
print(f"{'='*60}")

# Check for template literal issues in renderAnalysisTab
an_code, _ = extract_function(main_script, 'renderAnalysisTab')
if an_code:
    # Look for unmatched template expressions
    dollar_braces = an_code.count('${')
    # Check for null/undefined access patterns
    lines = an_code.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Look for property access without optional chaining that could fail
        if '.toFixed(' in stripped and '?' not in stripped.split('.toFixed')[0][-10:]:
            print(f"  renderAnalysisTab line {i}: potential null .toFixed(): {stripped[:100]}")
        if '.length' in stripped and '?' not in stripped:
            pass  # common, skip
