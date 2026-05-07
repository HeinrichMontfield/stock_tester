# -*- coding: utf-8 -*-

# 获取数据库中股票数据的各类接口

import os

import baostock as bs
from dotenv import load_dotenv
import pandas as pd
from pymongo import MongoClient
from datetime import datetime

from scripts.utils import stock_logger

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("STOCK_DB_NAME")]
col_basic = db[os.getenv("STOCK_BASIC_COLLECTION")]
col_kline = db[os.getenv("STOCK_KLINE_COLLECTION")]


def get_stock_basic(code):
    """Get stock basic info with MongoDB cache.

    The caller is responsible for baostock login/logout.

    Returns a dict of stock basic fields (e.g. code, code_name, ...).
    """
    basic = col_basic.find_one({"code": code}, {"_id": 0})
    if basic:
        stock_logger.debug("Read basic info of %s from MongoDB", code)
        return basic

    stock_logger.debug("Fetch basic info of %s from baostock", code)
    rs = bs.query_stock_basic(code=code)
    if rs.error_code != '0':
        raise RuntimeError(
            f"Failed to query stock basic for {code}: {rs.error_msg}"
        )

    data = []
    while rs.next():
        data.append(rs.get_row_data())
    if not data:
        raise ValueError(f"No basic info found for stock {code}")

    df = pd.DataFrame(data, columns=rs.fields)
    doc = df.to_dict("records")[0]
    col_basic.insert_one(doc)
    stock_logger.debug("Cached basic info of %s to MongoDB", code)
    return doc


def get_stock_kline(code, start_date, end_date):
    """Get K-line data with MongoDB cache.

    If the cached date range does not fully cover [start_date, end_date],
    re-fetches from baostock and updates the cache.

    When baostock returns data with a smaller range than requested (e.g. due
    to non-trading days), stores max_verified_date to skip redundant re-fetches
    for future requests up to the same end_date.

    The caller is responsible for baostock login/logout.

    Returns a DataFrame with columns: date, open, high, low, close, volume, amount, turn.
    All columns are string-typed; the caller should convert as needed.
    """
    cached = col_kline.find_one({"code": code})

    if cached and "min_date" in cached:
        effective_min = cached.get("min_verified_date", cached["min_date"])
        effective_max = cached.get("max_verified_date", cached["max_date"])
        if effective_min <= start_date and effective_max >= end_date:
            stock_logger.debug(
                "Read K-line data of %s %s-%s from MongoDB",
                code, start_date, end_date,
            )
            cached_df = pd.DataFrame(cached["data"])
            mask = (
                (cached_df["date"] >= start_date)
                & (cached_df["date"] <= end_date)
            )
            return cached_df[mask].reset_index(drop=True)
        else:
            stock_logger.debug(
                "Cache date range %s~%s insufficient for %s~%s, re-fetching from baostock",
                cached["min_date"], cached["max_date"], start_date, end_date,
            )

    stock_logger.debug(
        "Fetch K-line data of %s %s-%s from baostock",
        code, start_date, end_date,
    )
    rs = bs.query_history_k_data_plus(
        code=code,
        fields="date,open,high,low,close,volume,amount,turn",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="3",
    )
    data = []
    while rs.next():
        data.append(rs.get_row_data())

    df = pd.DataFrame(data, columns=rs.fields)

    if not df.empty:
        min_date = df["date"].min()
        max_date = df["date"].max()
        update = {
            "code": code,
            "min_date": min_date,
            "max_date": max_date,
            "data": df.to_dict("records"),
            "update_time": datetime.now(),
        }
        # Record verified extents so non-trading days don't trigger re-fetches.
        update["min_verified_date"] = start_date if min_date > start_date else min_date
        update["max_verified_date"] = end_date if max_date < end_date else max_date
        col_kline.update_one(
            {"code": code},
            {"$set": update},
            upsert=True,
        )
        stock_logger.debug("Cached K-line data of %s to MongoDB", code)

    return df
