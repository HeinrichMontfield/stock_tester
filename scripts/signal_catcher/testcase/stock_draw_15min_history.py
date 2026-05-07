# -*- coding: utf-8 -*-
# 使用 plotly 绘制15分钟k线图，保存为 html 文件

import json
import os

import pandas as pd
import plotly.graph_objects as go

from scripts.utils import stock_logger


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

    # 按时间排序，用连续整数索引作为 x 轴，避免 plotly datetime 轴 + rangebreaks 的空白 bug
    df = df.sort_values("datetime").reset_index(drop=True)
    x_indices = list(range(len(df)))

    stock_logger.debug("Stock %s: drawing chart with %d records", stock_code, len(df))

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=x_indices,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name=stock_code,
                text=df["datetime"].dt.strftime("%Y-%m-%d %H:%M"),
                hoverinfo="text",
            )
        ]
    )

    # 每月 1/10/20/30 日在 x 轴做标记（取当日第一条数据的位置）
    tick_indices = []
    tick_texts = []
    target_days = {1, 10, 20, 30}
    for idx, row in df.iterrows():
        if row["datetime"].day in target_days:
            tick_date = row["datetime"].strftime("%m-%d")
            # 每个日期只取第一个位置
            if not tick_texts or tick_texts[-1] != tick_date:
                tick_indices.append(idx)
                tick_texts.append(tick_date)

    title_text = f"{stock_code}_{stock_name} 15min K-line" if stock_name else f"{stock_code} 15min K-line"

    fig.update_layout(
        title=title_text,
        xaxis=dict(
            title="Time",
            tickmode="array",
            tickvals=tick_indices,
            ticktext=tick_texts,
            tickangle=45,
        ),
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
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
