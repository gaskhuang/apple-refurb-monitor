#!/bin/bash
# 安裝成 macOS LaunchAgent（開機自動執行，崩潰自動重啟）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.apple.refurb.monitor"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
PYTHON="$(which python3)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Apple 整修品監控 - 安裝程式"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Python  : $PYTHON"
echo "腳本    : $SCRIPT_DIR/monitor.py"
echo "plist   : $PLIST_PATH"
echo ""

# 確認 python3 存在
if ! command -v python3 &>/dev/null; then
    echo "❌ 找不到 python3，請先安裝："
    echo "   https://www.python.org/downloads/"
    exit 1
fi

# 先測試跑一次確認正常
echo "🔍 先測試查詢一次..."
python3 "$SCRIPT_DIR/monitor.py" --once
echo ""

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${SCRIPT_DIR}/monitor.py</string>
        <string>--interval</string>
        <string>10</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/launchd_error.log</string>
</dict>
</plist>
PLIST

# 卸載舊版（若存在）
launchctl unload "$PLIST_PATH" 2>/dev/null || true

# 安裝並啟動
launchctl load "$PLIST_PATH"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 安裝完成！監控已在背景執行"
echo ""
echo "常用指令："
echo "  即時日誌  : tail -f $SCRIPT_DIR/monitor.log"
echo "  停止      : launchctl unload $PLIST_PATH"
echo "  重啟      : launchctl unload $PLIST_PATH && launchctl load $PLIST_PATH"
echo "  卸載      : bash $SCRIPT_DIR/uninstall.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
