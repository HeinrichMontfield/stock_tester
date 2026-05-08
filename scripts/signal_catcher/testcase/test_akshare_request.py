# -*- coding: utf-8 -*-
# 测试 stock_bid_ask_em 获取集合竞价开盘价

import akshare as ak
import pandas as pd
import json
import sys
import os

# 支持传入股票代码作为命令行参数
STOCK_CODE = sys.argv[1] if len(sys.argv) > 1 else "002545"

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.width", 200)

print(f"\n=== 测试 stock_bid_ask_em for {STOCK_CODE} ===\n")

try:
    df = ak.stock_bid_ask_em(symbol=STOCK_CODE)
    print("DataFrame shape:", df.shape)
    print("DataFrame columns:", df.columns.tolist())
    print()

    # 打印全部数据
    print("=== 全部行情数据 ===")
    for _, row in df.iterrows():
        print(f"  {row['item']:8s}  {row['value']}")

    print()

    # 提取今开
    try:
        today_open = float(df[df["item"] == "昨收"]["value"].iloc[0])
        print(f"今开 (today_open) = {today_open}")
    except Exception as e:
        print(f"提取今开失败: {e}")

    print()

    # 常见字段
    for key in ["最新", "今开", "昨收", "最高", "最低", "涨停", "跌停", "换手", "量比"]:
        match = df[df["item"] == key]
        if not match.empty:
            print(f"  {key}: {match['value'].iloc[0]}")

except Exception as e:
    print(f"请求失败: {e}")
    import traceback
    traceback.print_exc()
