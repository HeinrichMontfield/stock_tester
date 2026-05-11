# -*- coding: utf-8 -*-

import logging
import logging.handlers
import os
import re
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

LOG_FOLDER = os.getenv(
    "LOG_FOLDER",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "log",
    ),
)

os.makedirs(LOG_FOLDER, exist_ok=True)

# 启动时间戳，每次进程启动生成新的日志文件
_startup_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
_log_filename = f"stock_{_startup_ts}.log"

_logger = logging.getLogger("stock")
_logger.setLevel(logging.DEBUG)

# 自定义滚动命名：将默认的 stock_xxx.log.2026-05-11 改为 stock_xxx_20260511.log
def _rotating_namer(default_name: str) -> str:
    m = re.match(r"(.+)\.log\.(\d{4}-\d{2}-\d{2})$", default_name)
    if m:
        return f"{m.group(1)}_{m.group(2).replace('-', '')}.log"
    return default_name


if not _logger.handlers:
    _handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(LOG_FOLDER, _log_filename),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    _handler.namer = _rotating_namer
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s][%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    _logger.addHandler(_handler)


def debug(fmt, *args):
    _logger.debug(fmt, *args)


def error(fmt, *args):
    _logger.error(fmt, *args)
