#!/bin/bash
# Start news monitoring script.
# Ctrl+C is passed via exec to python, which handles cleanup and exit.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="${VIRTUAL_ENV}/bin/python"

cd "$SCRIPT_DIR"
echo "[start_news_monitor.sh] Starting news_monitor..."
exec nice -n 10 "$VENV_PYTHON" ./news_monitor/news_monitor.py
