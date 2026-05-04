# -*- coding: utf-8 -*-

import os
import sys

import baostock as bs
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv

from scripts.database_ops.db_requestdata import get_stock_basic, get_stock_kline


def get_stock_data(code, lookback_months=6):
    """Fetch stock data via the cached MongoDB layer.

    Returns (DataFrame, stock_name).
    """
    lg = bs.login()
    print("Login response:", lg.error_msg)

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=lookback_months * 30)).strftime(
        "%Y-%m-%d"
    )

    # Stock name from cached basic info
    basic_info = get_stock_basic(code)
    stock_name = basic_info.get("code_name", code)
    print(f"Stock name: {stock_name}")

    # K-line data from cached layer
    df = get_stock_kline(code, start_date=start_date, end_date=end_date)

    if df.empty:
        print(f"No data obtained for {code}")
        bs.logout()
        return None, None

    # Type conversion
    df["date"] = pd.to_datetime(df["date"])
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)

    df = df.sort_values("date").reset_index(drop=True)

    bs.logout()
    return df, stock_name


def calculate_kdj(df, n=9, m1=3, m2=3):
    """Calculate KDJ indicator."""
    df = df.copy()

    low_list = df["low"].rolling(window=n, min_periods=1).min()
    high_list = df["high"].rolling(window=n, min_periods=1).max()

    rsv = (df["close"] - low_list) / (high_list - low_list) * 100
    rsv = rsv.fillna(50)

    df["K"] = 0.0
    df["D"] = 0.0

    df.loc[0, "K"] = 50
    df.loc[0, "D"] = 50

    for i in range(1, len(df)):
        df.loc[i, "K"] = (2 / 3) * df.loc[i - 1, "K"] + (1 / 3) * rsv.loc[i]
        df.loc[i, "D"] = (2 / 3) * df.loc[i - 1, "D"] + (1 / 3) * df.loc[i, "K"]

    df["J"] = 3 * df["K"] - 2 * df["D"]
    df.loc[: n - 2, ["K", "D", "J"]] = np.nan

    return df


def plot_stock_with_kdj(df, stock_name="sz.002050"):
    """Plot candlestick, volume and KDJ chart."""
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.5, 0.25, 0.25],
        subplot_titles=(f"{stock_name} - Candlestick Chart", "Volume", "KDJ Indicator"),
    )

    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Candlestick",
            increasing_line_color="red",
            decreasing_line_color="green",
        ),
        row=1,
        col=1,
    )

    colors = [
        "red" if close >= open else "green"
        for close, open in zip(df["close"], df["open"])
    ]

    fig.add_trace(
        go.Bar(
            x=df["date"],
            y=df["volume"],
            name="Volume",
            marker_color=colors,
            showlegend=True,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["K"],
            name="K Line",
            line=dict(color="blue", width=1.5),
            mode="lines",
            connectgaps=False,
        ),
        row=3,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["D"],
            name="D Line",
            line=dict(color="orange", width=1.5),
            mode="lines",
            connectgaps=False,
        ),
        row=3,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["J"],
            name="J Line",
            line=dict(color="purple", width=1.5),
            mode="lines",
            connectgaps=False,
        ),
        row=3,
        col=1,
    )

    fig.add_hline(y=20, line_dash="dash", line_color="gray", opacity=0.5, row=3, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="gray", opacity=0.5, row=3, col=1)
    fig.add_hrect(
        y0=0, y1=20, line_width=0, fillcolor="green", opacity=0.1, row=3, col=1
    )
    fig.add_hrect(
        y0=80, y1=100, line_width=0, fillcolor="red", opacity=0.1, row=3, col=1
    )

    fig.update_layout(
        title=f"{stock_name} Stock Analysis Chart (with KDJ Indicator)",
        xaxis_title="Date",
        yaxis_title="Price",
        template="plotly_white",
        height=900,
        showlegend=True,
        hovermode="x unified",
    )

    fig.update_yaxes(title_text="Price (CNY)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="KDJ Value", row=3, col=1, range=[0, 100])

    fig.update_xaxes(title_text="Date", row=3, col=1)

    return fig


def main():
    if len(sys.argv) < 2:
        print("Error: output_folder argument is required", file=sys.stderr)
        sys.exit(1)

    output_folder = sys.argv[1]

    load_dotenv()
    html_output_folder = os.getenv("HTML_OUTPUT_FOLDER")
    if not html_output_folder:
        print("Error: HTML_OUTPUT_FOLDER not set in .env", file=sys.stderr)
        sys.exit(1)

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not os.path.isabs(html_output_folder):
        html_output_folder = os.path.join(project_root, html_output_folder)

    target_dir = os.path.join(html_output_folder, output_folder)

    stock_code = "sz.002050"

    print(f"Fetching data for {stock_code}...")

    df, stock_name = get_stock_data(stock_code, lookback_months=6)

    if df is None or df.empty:
        print("Data fetch failed")
        sys.exit(1)

    print(f"Successfully obtained {len(df)} records")
    print(f"Data date range: {df['date'].min()} to {df['date'].max()}")
    print("\nFirst 5 rows of data:")
    print(df.head())

    print("\nCalculating KDJ indicator...")
    df = calculate_kdj(df, n=9, m1=3, m2=3)

    print("\nKDJ calculation results (last 5 rows):")
    print(df[["date", "close", "K", "D", "J"]].tail())

    print("\nGenerating chart...")
    fig = plot_stock_with_kdj(df, stock_name)

    from scripts.utils.stock_custom_utils import save_fig_to_data_analyzed

    safe_name = stock_name if stock_name else stock_code.replace(".", "_")
    filename = f"{safe_name}_{stock_code.replace('.', '_')}_kdj.html"
    save_fig_to_data_analyzed(fig, filename, output_dir=target_dir)


if __name__ == "__main__":
    main()
