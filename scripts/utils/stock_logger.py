# -*- coding: utf-8 -*-

import logging
import logging.handlers
import os
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

if not _logger.handlers:
    _handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(LOG_FOLDER, _log_filename),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
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
