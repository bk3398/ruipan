#!/bin/bash
# vps_pipeline.sh — VPS端管道
# 1. 导出timeline数据
# 2. push到GitHub
# 3. pull沙箱计算结果并导入
#
# crontab: */30 * * * * /opt/ruipan/scraper/vps_pipeline.sh >> /opt/ruipan/logs/pipeline.log 2>&1

REPO_DIR="/opt/ruipan/ruipan_repo"
SCRAPER_DIR="/opt/ruipan/scraper"
LOG_DIR="/opt/ruipan/logs"

mkdir -p "$LOG_DIR"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') VPS Pipeline Start ==="

# ── Git helper: 带重试的pull --rebase ──
git_pull_rebase() {
    local attempt=1
    while [ $attempt -le 3 ]; do
        if git pull --rebase origin main 2>&1; then
            return 0
        fi
        echo "git pull attempt $attempt failed, retrying in 10s..."
        sleep 10
        attempt=$((attempt + 1))
    done
    echo "ERROR: git pull failed after 3 attempts"
    git rebase --abort 2>/dev/null
    return 1
}

# ── Git helper: 带重试的push ──
git_push() {
    local attempt=1
    while [ $attempt -le 3 ]; do
        # push前先rebase拉取远端最新，避免divergent branches
        git fetch origin main 2>/dev/null
        if ! git diff --quiet HEAD origin/main 2>/dev/null; then
            echo "Remote has new commits, rebasing..."
            git pull --rebase origin main 2>&1 || { git rebase --abort 2>/dev/null; return 1; }
        fi
        if git push origin main 2>&1; then
            return 0
        fi
        echo "git push attempt $attempt failed, retrying in 10s..."
        sleep 10
        attempt=$((attempt + 1))
    done
    echo "ERROR: git push failed after 3 attempts"
    return 1
}

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
    git_pull_rebase || echo "WARNING: initial pull failed, continuing"
fi

# 3. 复制导出文件到仓库并push
mkdir -p gold_vps/data
if [ -f "$EXPORT_SRC" ]; then
    cp "$EXPORT_SRC" gold_vps/data/timeline_export.json
    git add gold_vps/data/timeline_export.json
    if git diff --cached --quiet; then
        echo "No changes to export"
    else
        git commit -m "vps: timeline export $(date '+%Y-%m-%d %H:%M')"
        if git_push; then
            echo "Export pushed"
        else
            echo "ERROR: Failed to push export"
        fi
    fi
fi

# 4. Pull最新结果（沙箱可能已push计算结果）
git_pull_rebase || echo "WARNING: pull for results failed"

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
