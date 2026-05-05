#!/bin/bash
# 启动邮件监控脚本
# Ctrl+C 会通过 exec 直接传递给 python，python 内部处理清理后退出

SCRIPT_DIR="/Users/mac/virtualenvs/venv_baostock/scripts"
VENV_PYTHON="/Users/mac/virtualenvs/venv_baostock/bin/python"

cd "$SCRIPT_DIR"
echo "[start_monitor.sh] Starting stockmail_central..."
exec "$VENV_PYTHON" ./mail/stockmail_central.py
