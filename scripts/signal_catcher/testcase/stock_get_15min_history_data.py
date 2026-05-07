# -*- coding: utf-8 -*-
# 获取15分钟k线历史数据并存储到 /data/signal_catcher/<stock code>.csv 文件中

import akshare as ak
import pandas as pd
import json
import os
from datetime import datetime

from scripts.utils import stock_logger


DATA_SUBDIR = "signal_catcher"


def _get_project_root():
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )


def _get_data_dir():
    data_dir = os.path.join(_get_project_root(), "data", DATA_SUBDIR)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _read_info_json(info_file):
    if not os.path.exists(info_file):
        return {}, None, None
    try:
        with open(info_file, "r", encoding="utf-8") as f:
            info = json.load(f)
        return info, info.get("start_time"), info.get("end_time")
    except (json.JSONDecodeError, KeyError) as e:
        stock_logger.error("Failed to read info file %s: %s", info_file, str(e))
        return {}, None, None


def _determine_fetch_range(start_time, end_time, old_start, old_end):
    """
    Determine the date range to fetch and the new overall range.
    Returns (fetch_start, fetch_end, overall_start, overall_end) or None if fully covered.
    """
    if old_start and old_end:
        if start_time >= old_start and end_time <= old_end:
            return None
        if end_time < old_start:
            fetch_start = start_time
            fetch_end = old_start
        elif start_time > old_end:
            fetch_start = old_end
            fetch_end = end_time
        elif start_time < old_start and end_time > old_end:
            fetch_start = start_time
            fetch_end = end_time
        elif start_time < old_start:
            fetch_start = start_time
            fetch_end = old_start
        else:
            fetch_start = old_end
            fetch_end = end_time
        overall_start = min(start_time, old_start)
        overall_end = max(end_time, old_end)
    else:
        fetch_start = start_time
        fetch_end = end_time
        overall_start = start_time
        overall_end = end_time

    return fetch_start, fetch_end, overall_start, overall_end


def _merge_and_save_csv(csv_file, df_new):
    if os.path.exists(csv_file):
        try:
            df_existing = pd.read_csv(csv_file)
            df_merged = pd.concat([df_existing, df_new], ignore_index=True)
            df_merged["datetime"] = pd.to_datetime(df_merged["datetime"])
            df_merged = df_merged.drop_duplicates(subset=["datetime"], keep="last")
            df_merged = df_merged.sort_values("datetime")
            return df_merged
        except Exception as e:
            stock_logger.error("Merge with existing CSV failed: %s", str(e))
    return df_new


def _save_info_json(info_file, stock_code, start_time, end_time):
    info = {
        "stock_code": stock_code,
        "start_time": start_time,
        "end_time": end_time,
    }
    with open(info_file, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)


def request_stock_15min_history(stock_code, start_time, end_time):
    """
    Request 15-minute K-line historical data and store as CSV.

    Args:
        stock_code: stock code, e.g. "600893"
        start_time: start date, format yyyy-mm-dd
        end_time: end date, format yyyy-mm-dd

    Returns:
        csv file path, or None if no new data fetched
    """
    data_dir = _get_data_dir()
    csv_file = os.path.join(data_dir, f"{stock_code}_data.csv")
    info_file = os.path.join(data_dir, f"{stock_code}_info.json")

    _, old_start, old_end = _read_info_json(info_file)

    if old_start and old_end:
        stock_logger.debug(
            "Stock %s: existing range [%s, %s], requested [%s, %s]",
            stock_code, old_start, old_end, start_time, end_time,
        )

    result = _determine_fetch_range(start_time, end_time, old_start, old_end)
    if result is None:
        stock_logger.debug(
            "Stock %s: requested range already covered by [%s, %s]",
            stock_code, old_start, old_end,
        )
        return None

    fetch_start, fetch_end, overall_start, overall_end = result

    stock_logger.debug(
        "Stock %s: fetching range [%s, %s]",
        stock_code, fetch_start, fetch_end,
    )

    try:
        df = ak.stock_zh_a_hist_min_em(
            symbol=stock_code,
            period="15",
            adjust="qfq",
            start_date=fetch_start,
            end_date=fetch_end,
        )
    except Exception as e:
        stock_logger.error("Stock %s: fetch data failed: %s", stock_code, str(e))
        return None

    if df is None or df.empty:
        stock_logger.debug(
            "Stock %s: no data received for [%s, %s]",
            stock_code, fetch_start, fetch_end,
        )
        return None

    stock_logger.debug("Stock %s: fetched %d records", stock_code, len(df))

    df_output = df[["时间", "开盘", "最高", "最低", "收盘", "成交量"]].copy()
    df_output.columns = ["datetime", "open", "high", "low", "close", "volume"]

    df_final = _merge_and_save_csv(csv_file, df_output)
    df_final.to_csv(csv_file, index=False, encoding="utf-8-sig")
    stock_logger.debug(
        "Stock %s: saved %d total records to %s",
        stock_code, len(df_final), csv_file,
    )

    _save_info_json(info_file, stock_code, overall_start, overall_end)
    stock_logger.debug(
        "Stock %s: updated info range to [%s, %s]",
        stock_code, overall_start, overall_end,
    )

    return csv_file


if __name__ == "__main__":
    from scripts.utils import stock_logger_simple as stock_logger

    STOCK_CODE = "600893"
    START_DATE = "2026-01-01"
    END_DATE = datetime.now().strftime("%Y-%m-%d")

    stock_logger.debug("=== Historical Data Fetch Service Started ===")

    csv_file = request_stock_15min_history(STOCK_CODE, START_DATE, END_DATE)

    if csv_file:
        test_data = pd.read_csv(csv_file)
        stock_logger.debug("Data is ready, first 5 records preview:")
        stock_logger.debug(str(test_data.head()))
    else:
        stock_logger.debug("Data preparation failed")

    stock_logger.debug("=== Historical Data Fetch Service Finished ===")
