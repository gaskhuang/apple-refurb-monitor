#!/bin/bash
PLIST_PATH="$HOME/Library/LaunchAgents/com.apple.refurb.monitor.plist"
launchctl unload "$PLIST_PATH" 2>/dev/null && echo "✅ 已停止" || echo "（未在執行）"
rm -f "$PLIST_PATH" && echo "✅ plist 已刪除"
echo "監控已卸載。"
