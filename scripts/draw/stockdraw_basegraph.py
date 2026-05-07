# -*- coding: utf-8 -*-

import baostock as bs
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas_ta_classic as pta
from datetime import datetime
from dateutil.relativedelta import relativedelta

from scripts.database_ops.db_requestdata import get_stock_basic, get_stock_kline
from scripts.utils import stock_logger


def main():

    # ===================== 1. 登录 =====================
    loginStatus = bs.login()
    if loginStatus.error_code != "0":
        stock_logger.error("Login failed: %s", loginStatus.error_msg)

    stock_logger.debug("login success!")

    code = "sz.002050"
    # code = "sz.159272"
    current_date = datetime.now()
    six_months_ago = current_date - relativedelta(months=6)

    startDate = six_months_ago.strftime("%Y-%m-%d")
    endDate = current_date.strftime("%Y-%m-%d")

    stock_logger.debug("Start date: %s", startDate)
    stock_logger.debug("End date: %s", endDate)

    # 获取股票中文名称（走缓存）
    basic_info = get_stock_basic(code)
    stock_name = basic_info.get("code_name", code)
    stock_logger.debug("Name corresponding to code %s: %s", code, stock_name)

    # 获取K线数据（走缓存）
    df = get_stock_kline(code, start_date=startDate, end_date=endDate)
    stock_logger.debug("df.shape: %s, df.head: %s", df.shape, df.head())
    if df.shape[0] == 0:
        stock_logger.error("[error] no data get for %s !!!", code)
        return

    bs.logout()
    stock_logger.debug("logout success!")

    # 数据类型转换
    df[["open", "high", "low", "close", "volume"]] = df[
        ["open", "high", "low", "close", "volume"]
    ].astype(float)
    df["date"] = pd.to_datetime(df["date"])

    # ===================== 2. 正确计算 MACD（pandas-ta-classic 专用） =====================
    macd = pta.macd(df["close"], fast=12, slow=26, signal=9, talib=False)
    df["MACD"] = macd["MACD_12_26_9"]
    df["Signal"] = macd["MACDs_12_26_9"]
    df["Histogram"] = macd["MACDh_12_26_9"]

    # ===================== 3. 绘图 =====================
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.5, 0.25, 0.25],
        vertical_spacing=0.03
    )

    # K线
    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="K-line",
            increasing_line_color="red",
            decreasing_line_color="green"
        ), row=1, col=1
    )

    # 成交量
    colors = ['red' if close >= open else 'green'
              for close, open in zip(df['close'], df['open'])]

    fig.add_trace(
        go.Bar(
            x=df['date'],
            y=df['volume'],
            name='Volume',
            marker_color=colors,
            showlegend=True
        ),
        row=2, col=1
    )

    # MACD
    fig.add_trace(
        go.Line(x=df["date"], y=df["MACD"], name="MACD", line=dict(color="blue")),
        row=3, col=1,
    )
    fig.add_trace(
        go.Line(x=df["date"], y=df["Signal"], name="Signal", line=dict(color="red")),
        row=3, col=1,
    )
    fig.add_trace(
        go.Bar(x=df["date"], y=df["Histogram"], name="Histogram"),
        row=3, col=1,
    )

    fig.update_layout(
        title=stock_name + " Daily K-line Chart",
        xaxis_rangeslider_visible=False,
        height=800,
    )

    from utils.stock_custom_utils import save_fig_to_data_analyzed

    chartName = stock_name + code + startDate + "_" + endDate + ".html"
    save_fig_to_data_analyzed(fig, chartName)


if __name__ == "__main__":
    main()
