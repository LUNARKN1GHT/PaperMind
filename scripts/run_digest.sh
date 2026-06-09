#!/bin/bash
# PaperMind 每日 digest 自动运行脚本（供 launchd 调用）。
# 手动测试：bash scripts/run_digest.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="/opt/homebrew/Caskroom/miniforge/base/bin/python"
LOG_DIR="$PROJECT_DIR/outputs/logs"
mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 启动 digest =====" >> "$LOG_DIR/digest.log"
"$PYTHON" main.py --digest >> "$LOG_DIR/digest.log" 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 结束 =====" >> "$LOG_DIR/digest.log"
