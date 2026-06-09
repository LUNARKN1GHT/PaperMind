#!/bin/bash
# 安装/重装 PaperMind 每日 digest 定时任务（launchd）。
# 用法：bash scripts/install_digest.sh
# 卸载：launchctl unload ~/Library/LaunchAgents/com.papermind.digest.plist
#       rm ~/Library/LaunchAgents/com.papermind.digest.plist
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$SCRIPT_DIR/com.papermind.digest.plist.template"
DEST="$HOME/Library/LaunchAgents/com.papermind.digest.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/outputs/logs"

# 用本机真实路径替换模版占位符，生成到 LaunchAgents（不进 git）
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$TEMPLATE" > "$DEST"

# 先卸载旧的（若存在）再加载，确保改动生效
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "已安装并加载：$DEST"
echo "查看是否注册：launchctl list | grep papermind"
echo "立即跑一次测试：launchctl start com.papermind.digest"
echo "日志：outputs/logs/digest.log"
