# -*- coding: utf-8 -*-

# 获取股票数据并存入数据库的测试用例

import os
import sys

# Add the scripts parent directory to sys.path so imports work regardless
# of whether this is run as a module or directly.
_scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import baostock as bs
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from scripts.database_ops.db_requestdata import get_stock_basic, get_stock_kline
from scripts.utils import stock_logger

# ======================
# 1. 登录 Baostock
# ======================
bs.login()

# ======================
# 2. 测试示例
# ======================
if __name__ == "__main__":
    code = "sz.002050"

    # 1. 获取基本信息
    basic_info = get_stock_basic(code)
    stock_logger.debug("Basic Info:")
    stock_logger.debug("%s", basic_info)

    # 获取当前系统日期
    current_date = datetime.now()
    # 6个月前的日期
    six_months_ago = current_date - relativedelta(months=6)

    # 格式化为字符串：YYYY-MM-DD
    startDate = six_months_ago.strftime("%Y-%m-%d")
    endDate = current_date.strftime("%Y-%m-%d")

    # 2. 获取日期范围K线
    df = get_stock_kline(code, start_date=startDate, end_date=endDate)
    stock_logger.debug("\nK-line Data:")
    stock_logger.debug("%s", df.head())

# 退出baostock
bs.logout()
