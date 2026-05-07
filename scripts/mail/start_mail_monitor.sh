#!/bin/bash
# 启动邮件监控脚本
# Ctrl+C 会通过 exec 直接传递给 python，python 内部处理清理后退出

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="${VIRTUAL_ENV}/bin/python"

cd "$SCRIPT_DIR"
echo "[start_monitor.sh] Starting stockmail_central..."
exec "$VENV_PYTHON" ./mail/stockmail_central.py
