#!/bin/bash
# PaperMind 每日 digest 自动运行脚本（供 launchd 调用）。
# 手动测试：bash scripts/run_digest.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="/opt/homebrew/Caskroom/miniforge/base/bin/python"
LOG_DIR="$PROJECT_DIR/outputs/logs"
mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR"

# 幂等：当天已生成就跳过。配合 launchd 一天多次触发，
# 早上没网失败也不会留下文件，中午/晚上联网时自动补跑，成功后当天不再重复。
TODAY_FILE="$PROJECT_DIR/outputs/digest/digest_$(date '+%Y-%m-%d').md"
if [ -f "$TODAY_FILE" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') 今日已生成，跳过：$TODAY_FILE" >> "$LOG_DIR/digest.log"
    exit 0
fi

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 启动 digest =====" >> "$LOG_DIR/digest.log"
"$PYTHON" main.py --digest >> "$LOG_DIR/digest.log" 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 结束 =====" >> "$LOG_DIR/digest.log"
