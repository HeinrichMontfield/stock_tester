#!/bin/bash
# 启动股票价格涨跌幅监控脚本
# Ctrl+C 会通过 exec 直接传递给 python，python 内部处理清理后退出

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="${VIRTUAL_ENV}/bin/python"

cd "$SCRIPT_DIR"
echo "[run_monitor] Starting stock_monitor_price_variant..."
exec "$VENV_PYTHON" ./signal_catcher/stock_monitor_price_variant.py
