#!/bin/bash
# vps_pipeline.sh — VPS端管道
# 1. 导出timeline数据
# 2. push到GitHub
# 3. pull沙箱计算结果并导入
#
# 前置条件: git已配置credential（运行前先执行一次）
#   git config --global credential.helper store
#   echo "https://bk3398:TOKEN@github.com" > ~/.git-credentials
#
# crontab: */30 * * * * /opt/ruipan/scraper/vps_pipeline.sh >> /opt/ruipan/logs/pipeline.log 2>&1

set -e

REPO_DIR="/opt/ruipan/ruipan_repo"
SCRAPER_DIR="/opt/ruipan/scraper"
LOG_DIR="/opt/ruipan/logs"

mkdir -p "$LOG_DIR"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') VPS Pipeline Start ==="

# 1. 导出timeline数据（最近6小时）
cd "$SCRAPER_DIR"
python3 -u timeline_schema.py --export --hours 6

EXPORT_SRC="/opt/ruipan/data/timeline_export.json"
if [ ! -f "$EXPORT_SRC" ]; then
    echo "WARNING: Export file not found, skipping push"
else
    EXPORT_SIZE=$(stat -c%s "$EXPORT_SRC" 2>/dev/null || stat -f%z "$EXPORT_SRC" 2>/dev/null)
    echo "Export: ${EXPORT_SIZE} bytes"
fi

# 2. Clone或pull仓库
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "Cloning repo..."
    rm -rf "$REPO_DIR"
    git clone "https://github.com/bk3398/ruipan.git" "$REPO_DIR"
    cd "$REPO_DIR"
    git config user.email "vps@ruipan.local"
    git config user.name "VPS Pipeline"
else
    cd "$REPO_DIR"
    git config user.email "vps@ruipan.local"
    git config user.name "VPS Pipeline"
    git pull origin main 2>&1 | tail -3
fi

# 3. 复制导出文件到仓库
mkdir -p gold_vps/data
if [ -f "$EXPORT_SRC" ]; then
    cp "$EXPORT_SRC" gold_vps/data/timeline_export.json
    git add gold_vps/data/timeline_export.json
    git commit -m "vps: timeline export $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || true
    git push origin main 2>&1 | tail -3
    echo "Export pushed"
fi

# 4. Pull最新结果
git pull origin main 2>&1 | tail -3

# 5. 导入K线结果
RESULT_FILE="gold_vps/results/kline_results.json"
if [ -f "$RESULT_FILE" ]; then
    RESULT_MTIME=$(stat -c %Y "$RESULT_FILE" 2>/dev/null || stat -f %m "$RESULT_FILE" 2>/dev/null)
    MARKER_FILE="${SCRAPER_DIR}/.last_result_mtime"
    LAST_MTIME=0
    if [ -f "$MARKER_FILE" ]; then
        LAST_MTIME=$(cat "$MARKER_FILE")
    fi

    if [ "$RESULT_MTIME" != "$LAST_MTIME" ]; then
        echo "Importing new results..."
        cd "$SCRAPER_DIR"
        python3 -u import_kline_results.py "${REPO_DIR}/${RESULT_FILE}" 2>&1
        echo "$RESULT_MTIME" > "$MARKER_FILE"
        echo "Import done"
    else
        echo "Results unchanged, skipping import"
    fi
else
    echo "No result file yet (waiting for sandbox)"
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') VPS Pipeline Done ==="
