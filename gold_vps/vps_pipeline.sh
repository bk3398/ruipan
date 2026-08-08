#!/bin/bash
# vps_pipeline.sh — VPS端管道（全量本地化，零沙箱依赖）
# 1. 导出timeline数据到GitHub（备份用，可选）
# 2. 本地K线聚合（kline_aggregator.py）
# 3. 推送到GitHub做版本留存
#
# crontab: */30 * * * * /opt/ruipan/scraper/vps_pipeline.sh >> /opt/ruipan/logs/pipeline.log 2>&1

REPO_DIR="/opt/ruipan/ruipan_repo"
SCRAPER_DIR="/opt/ruipan/scraper"
LOG_DIR="/opt/ruipan/logs"
DATA_DIR="/opt/ruipan/data"

mkdir -p "$LOG_DIR" "$DATA_DIR"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') VPS Pipeline Start ==="

# ── Git helper ──
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

git_push() {
    local attempt=1
    while [ $attempt -le 3 ]; do
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

# 1. 本地K线聚合（核心：不再依赖沙箱）
echo "--- K线聚合 ---"
cd "$SCRAPER_DIR"
python3 -u kline_aggregator.py --hours 12 2>&1
echo "K线聚合完成"

# 2. 导出timeline到GitHub做备份
echo "--- Timeline导出备份 ---"
python3 -u timeline_schema.py --export --hours 12 2>&1

EXPORT_SRC="${DATA_DIR}/timeline_export.json"
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "Cloning repo for backup..."
    rm -rf "$REPO_DIR"
    git clone "https://github.com/bk3398/ruipan.git" "$REPO_DIR"
    cd "$REPO_DIR"
    git config user.email "vps@ruipan.local"
    git config user.name "VPS Pipeline"
else
    cd "$REPO_DIR"
    git config user.email "vps@ruipan.local"
    git config user.name "VPS Pipeline"
    git_pull_rebase || echo "WARNING: pull failed, continuing"
fi

mkdir -p gold_vps/data
if [ -f "$EXPORT_SRC" ]; then
    cp "$EXPORT_SRC" gold_vps/data/timeline_export.json
    git add gold_vps/data/timeline_export.json
    if git diff --cached --quiet; then
        echo "No export changes"
    else
        git commit -m "vps: timeline backup $(date '+%Y-%m-%d %H:%M')"
        git_push && echo "Backup pushed" || echo "WARNING: backup push failed"
    fi
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') VPS Pipeline Done ==="
