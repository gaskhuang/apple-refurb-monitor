#!/bin/bash
# Apple 台灣整修品 Mac 每小時即時監控
# 偵測變動才寄信，腳本內已包含 email 發送邏輯

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$HOME/logs/apple_refurb.log"

mkdir -p "$HOME/logs" "$HOME/data" "$HOME/reports"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Apple 整修品監控 ===" >> "$LOG_FILE"
python3 "$SCRIPT_DIR/apple_refurb_monitor.py" >> "$LOG_FILE" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 完成 ===" >> "$LOG_FILE"
