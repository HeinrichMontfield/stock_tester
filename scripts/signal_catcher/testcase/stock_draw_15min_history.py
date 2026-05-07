# -*- coding: utf-8 -*-
# 使用 plotly 绘制15分钟k线图，保存为 html 文件

import json
import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go

from scripts.utils import stock_logger
from scripts.utils.stock_common_consts import A_STOCK_HOLIDAYS


def _get_project_root():
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )


def draw_stock_15min_history(stock_code, start_time=None, end_time=None):
    """
    Draw 15-minute K-line candlestick chart using plotly and save as HTML.

    Args:
        stock_code: stock code, e.g. "600893"
        start_time: start date, format yyyy-mm-dd (optional, defaults to all data)
        end_time: end date, format yyyy-mm-dd (optional, defaults to all data)

    Returns:
        html file path, or None on failure
    """
    project_root = _get_project_root()
    csv_file = os.path.join(project_root, "data", "signal_catcher", f"{stock_code}_data.csv")
    temp_dir = os.path.join(project_root, "data", "temp")
    os.makedirs(temp_dir, exist_ok=True)

    if not os.path.exists(csv_file):
        stock_logger.error("Stock %s: csv file not found at %s", stock_code, csv_file)
        return None

    # 从 info.json 中获取股票简称
    info_file = os.path.join(project_root, "data", "signal_catcher", f"{stock_code}_info.json")
    stock_name = ""
    if os.path.exists(info_file):
        try:
            with open(info_file, "r", encoding="utf-8") as f:
                info = json.load(f)
            stock_name = info.get("individual_info", {}).get("股票简称", "")
        except (json.JSONDecodeError, KeyError) as e:
            stock_logger.debug("Stock %s: failed to read stock name from info: %s", stock_code, str(e))

    try:
        df = pd.read_csv(csv_file)
        df["datetime"] = pd.to_datetime(df["datetime"])
    except Exception as e:
        stock_logger.error("Stock %s: failed to read csv: %s", stock_code, str(e))
        return None

    if start_time:
        df = df[df["datetime"] >= pd.Timestamp(start_time)]
    if end_time:
        df = df[df["datetime"] <= pd.Timestamp(end_time)]

    if df.empty:
        stock_logger.debug("Stock %s: no data in range [%s, %s]", stock_code, start_time or "all", end_time or "all")
        return None

    stock_logger.debug("Stock %s: drawing chart with %d records", stock_code, len(df))

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df["datetime"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name=stock_code,
            )
        ]
    )

    title_text = f"{stock_code}_{stock_name} 15min K-line" if stock_name else f"{stock_code} 15min K-line"

    # 构建 rangebreaks: 周末 + 非交易时段 + A股节假日
    rangebreaks = [
        dict(bounds=["sat", "mon"]),  # remove weekend gaps
        # 跨午夜的间断拆成两段：当日收盘→24点、0点→次日开市
        dict(bounds=[15, 24], pattern="hour"),  # remove overnight: 15:00 to midnight
        dict(bounds=[0, 9.5], pattern="hour"),  # remove overnight: midnight to 9:30
        dict(bounds=[11.5, 13], pattern="hour"),  # remove lunch break gaps (11:30 to 13:00)
    ]

    # 有问题，会导致 html 空白
    # 节假日：使用 values + dvalue 替代 bounds + pattern=""，
    # 避免 plotly 对日期字符串 pattern 推断失败导致 html 空白。
    # dvalue 单位毫秒，86400000 = 1 天，天数 = (结束-开始).days + 1（含首尾）
    # for holiday_start, holiday_end in A_STOCK_HOLIDAYS:
    #     start_dt = datetime.strptime(holiday_start, "%Y-%m-%d")
    #     end_dt = datetime.strptime(holiday_end, "%Y-%m-%d")
    #     holiday_days = (end_dt - start_dt).days + 1
    #     rangebreaks.append(dict(values=[holiday_start], dvalue=holiday_days * 86400000))

    fig.update_layout(
        title=title_text,
        xaxis_title="Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        xaxis_rangebreaks=rangebreaks,
    )

    range_start = start_time or df["datetime"].iloc[0].strftime("%Y-%m-%d")
    range_end = end_time or df["datetime"].iloc[-1].strftime("%Y-%m-%d")
    html_filename = f"{stock_code}_{range_start}_{range_end}_15min.html"
    html_path = os.path.join(temp_dir, html_filename)

    try:
        fig.write_html(
            html_path,
            include_plotlyjs=True,
            default_height="100vh",
            default_width="100%",
        )
    except Exception as e:
        stock_logger.error("Stock %s: failed to save html: %s", stock_code, str(e))
        return None

    stock_logger.debug("Stock %s: chart saved to %s", stock_code, html_path)
    return html_path


if __name__ == "__main__":
    from scripts.utils import stock_logger_simple as stock_logger

    STOCK_CODE = "600893"
    START_DATE = "2026-01-01"
    END_DATE = "2026-05-07"

    stock_logger.debug("=== 15min K-line Chart Drawing ===")
    result = draw_stock_15min_history(STOCK_CODE, START_DATE, END_DATE)
    if result:
        stock_logger.debug("Chart saved: %s", result)
    else:
        stock_logger.debug("Failed to draw chart")
    stock_logger.debug("=== Chart Drawing Finished ===")
