# -*- coding: utf-8 -*-
# 股票价格涨跌幅监控，支持模拟模式和实时模式。
# 当股价相对当日开盘价涨跌幅超过阈值时，按阶梯档位发送告警邮件。

import os
import signal
from dotenv import load_dotenv

load_dotenv()

# Ctrl+C 优雅退出标志
_shutdown_requested = False

# 修正 LOG_FOLDER 为绝对路径，确保日志写入项目根目录的 log/ 而非 CWD 下的 log/
# 解决从 scripts/ 目录运行时日志路径偏移的问题
_log_folder = os.getenv("LOG_FOLDER", "log")
if not os.path.isabs(_log_folder):
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_this_dir))
    os.environ["LOG_FOLDER"] = os.path.join(_project_root, _log_folder)

import akshare as ak
import pandas as pd
import json
import logging
import time
from datetime import datetime, timedelta
from pymongo import MongoClient

from scripts.utils import stock_logger
from scripts.utils.stock_common_consts import (
    A_STOCK_HOLIDAYS,
    LIMIT_DOWN_PCT,
    LIMIT_UP_PCT,
)

# ---------- 从 .env 读取配置 ----------
MONITOR_STOCK_CODES = [
    s.strip() for s in os.getenv("MONITOR_STOCK_CODES", "").split(",") if s.strip()
]
PRICE_VARIANT_THRESHOLD = float(os.getenv("PRICE_VARIANT_THRESHOLD", "3.0"))
MARKET_HOURS_START = os.getenv("MARKET_HOURS_START", "09:00")
MARKET_HOURS_MID_START = os.getenv("MARKET_HOURS_MID_START", "12:00")
MARKET_HOURS_MID_END = os.getenv("MARKET_HOURS_MID_END", "13:00")
MARKET_HOURS_END = os.getenv("MARKET_HOURS_END", "15:00")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
STOCK_DB_15MIN_NAME = os.getenv("STOCK_DB_15MIN_NAME", "stock_db_15min")
STOCK_KLINE_15MIN_COLLECTION = os.getenv("STOCK_KLINE_15MIN_COLLECTION", "stock_kline_15min")
EMAIL = os.getenv("EMAIL")

# ---------- 硬编码变量 ----------
IS_SIMULATE_MODE = True
START_SIMULATION_TIMESTAMP = "2026-03-24 09:30:00"
MONITOR_INTERVAL_MINUTES = 10
SIMULATE_SPEED_MULTIPLIER = 200

# ---------- 告警阶梯档位常量 ----------
# 基于 PRICE_VARIANT_THRESHOLD 生成阶梯档位（步长 2%），解决阈值未生效的问题
_t = int(PRICE_VARIANT_THRESHOLD)
DOWN_ALERT_LEVELS = [-_t, -(_t + 2), -(_t + 4)]
UP_ALERT_LEVELS = [_t, _t + 2, _t + 4]

DATA_SUBDIR = "signal_catcher"

# 股票简称缓存，避免重复读取/请求
_stock_short_name_cache = {}


def _get_project_root():
    """向上3级目录找到项目根目录（本文件位于 scripts/signal_catcher/）。"""
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def _get_data_dir():
    data_dir = os.path.join(_get_project_root(), "data", DATA_SUBDIR)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _get_stock_short_name(stock_code):
    """获取股票简称。

    优先从 <code>_info.json 读取；实时模式下若不存在则调用 akshare
    stock_individual_info_em 获取并缓存到 info.json。

    Returns:
        str: 股票简称，获取失败时返回 stock_code 本身
    """
    if stock_code in _stock_short_name_cache:
        return _stock_short_name_cache[stock_code]

    data_dir = _get_data_dir()
    info_file = os.path.join(data_dir, f"{stock_code}_info.json")
    try:
        with open(info_file, "r", encoding="utf-8") as f:
            info = json.load(f)
        short_name = info.get("short_name")
        if short_name:
            _stock_short_name_cache[stock_code] = short_name
            return short_name
    except Exception:
        pass

    if not IS_SIMULATE_MODE:
        try:
            df = ak.stock_individual_info_em(symbol=stock_code)
            row = df[df["item"] == "股票简称"]
            if not row.empty:
                short_name = str(row.iloc[0]["value"])
                _stock_short_name_cache[stock_code] = short_name
                try:
                    with open(info_file, "r", encoding="utf-8") as f:
                        info = json.load(f)
                except Exception:
                    info = {}
                info["short_name"] = short_name
                try:
                    with open(info_file, "w", encoding="utf-8") as f:
                        json.dump(info, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                return short_name
        except Exception as e:
            stock_logger.error(
                "[short_name] Failed to fetch for %s: %s", stock_code, str(e)
            )

    _stock_short_name_cache[stock_code] = stock_code
    return stock_code


def request_stock_15min_data(stock_code, timestamp=None):
    """获取15分钟K线数据，模拟模式读CSV，实时模式调用akshare。

    Args:
        stock_code: 股票代码，如 "600893"
        timestamp: datetime 对象，仅模拟模式使用

    Returns:
        dict | None: 单条数据字典，无数据时返回 None
    """
    if IS_SIMULATE_MODE:
        return _request_simulate_data(stock_code, timestamp)
    else:
        return _request_realtime_data(stock_code)


def _request_simulate_data(stock_code, timestamp):
    stock_logger.debug(
        "[simulate] Querying data for stock=%s, timestamp=%s",
        stock_code, timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else None,
    )
    data_dir = _get_data_dir()
    info_file = os.path.join(data_dir, f"{stock_code}_info.json")
    csv_file = os.path.join(data_dir, f"{stock_code}_data.csv")

    # 读取 info.json 获取时间范围
    try:
        with open(info_file, "r", encoding="utf-8") as f:
            info = json.load(f)
    except Exception as e:
        stock_logger.error("[simulate] Failed to read info file %s: %s", info_file, str(e))
        return None

    start_time = info.get("start_time")
    end_time = info.get("end_time")
    if not start_time or not end_time:
        stock_logger.error("[simulate] Info file %s missing start_time or end_time", info_file)
        return None

    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    start_dt = datetime.strptime(start_time, "%Y-%m-%d")
    end_dt = datetime.strptime(end_time, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)

    if timestamp < start_dt or timestamp > end_dt:
        stock_logger.debug(
            "[simulate] Timestamp %s out of range [%s, %s] for stock=%s",
            ts_str, start_time, end_time, stock_code,
        )
        return None

    # 读取 CSV
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        stock_logger.error("[simulate] Failed to read CSV %s: %s", csv_file, str(e))
        return None

    df["datetime"] = pd.to_datetime(df["datetime"])
    # 取 datetime <= timestamp 的最近一条记录
    df_filtered = df[df["datetime"] <= timestamp].sort_values("datetime", ascending=False)
    if df_filtered.empty:
        stock_logger.debug(
            "[simulate] No data <= %s for stock=%s", ts_str, stock_code,
        )
        return None

    row = df_filtered.iloc[0]
    stock_logger.debug(
        "[simulate] Got data for stock=%s, data_time=%s, records_found=%d",
        stock_code, str(row["datetime"]), len(df_filtered),
    )
    return {
        "stock_code": stock_code,
        "datetime": str(row["datetime"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": int(row["volume"]),
        "timestamp": str(row["datetime"]),
    }


def _request_realtime_data(stock_code):
    today = datetime.now().strftime("%Y-%m-%d")
    stock_logger.debug("[realtime] Fetching akshare data for stock=%s, date=%s", stock_code, today)
    try:
        df = ak.stock_zh_a_hist_min_em(
            symbol=stock_code,
            period="15",
            adjust="qfq",
            start_date=today,
            end_date=today,
        )
    except Exception as e:
        stock_logger.error("[realtime] akshare request failed for stock=%s: %s", stock_code, str(e))
        return None

    if df is None or df.empty:
        stock_logger.debug("[realtime] No data returned for stock=%s", stock_code)
        return None

    row = df.iloc[-1]
    stock_logger.debug(
        "[realtime] Got data for stock=%s, records=%d, latest=%s",
        stock_code, len(df), str(row["时间"]),
    )
    return {
        "stock_code": stock_code,
        "datetime": str(row["时间"]),
        "open": float(row["开盘"]),
        "high": float(row["最高"]),
        "low": float(row["最低"]),
        "close": float(row["收盘"]),
        "volume": int(row["成交量"]),
        "timestamp": str(row["时间"]),
    }


def save_15min_data_to_mongo(data_dict):
    """将15分钟K线数据存入 MongoDB，以 stock_code + datetime 为唯一键 upsert。

    Returns:
        bool: 成功返回 True
    """
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception as e:
        stock_logger.error("[mongo] Failed to connect to MongoDB: %s", str(e))
        return False

    try:
        db = client[STOCK_DB_15MIN_NAME]
        collection = db[STOCK_KLINE_15MIN_COLLECTION]
        filter_doc = {
            "stock_code": data_dict["stock_code"],
            "datetime": data_dict["datetime"],
        }
        result = collection.replace_one(filter_doc, data_dict, upsert=True)
        if result.upserted_id:
            stock_logger.debug(
                "[mongo] Inserted stock=%s, datetime=%s", data_dict["stock_code"], data_dict["datetime"],
            )
        else:
            stock_logger.debug(
                "[mongo] Skipped duplicate stock=%s, datetime=%s", data_dict["stock_code"], data_dict["datetime"],
            )
        return True
    except Exception as e:
        stock_logger.error("[mongo] Write failed: %s", str(e))
        return False
    finally:
        if client:
            client.close()


def _get_today_open(stock_code, data_dict, query_date=None):
    """获取当日开盘价。

    Args:
        stock_code: 股票代码
        data_dict: 请求到的当前数据条
        query_date: 查询日期（yyyy-mm-dd），模拟模式传入当前时间戳的日期，
                    避免数据日期与查询日期不一致时取到错误的开盘价

    Returns:
        float | None: 当日开盘价
    """
    if IS_SIMULATE_MODE:
        return _get_today_open_from_csv(stock_code, data_dict, query_date)
    else:
        return _get_today_open_realtime(stock_code, data_dict)


def _get_today_open_from_csv(stock_code, data_dict, query_date=None):
    data_dir = _get_data_dir()
    csv_file = os.path.join(data_dir, f"{stock_code}_data.csv")
    # 优先使用 query_date（查询时间戳的日期），避免模拟模式下跨日期时
    # 数据仍是前一日但 query_date 已是新日期，取到错误的开盘价
    data_date = query_date if query_date else data_dict["datetime"][:10]
    try:
        df = pd.read_csv(csv_file)
        df["datetime"] = pd.to_datetime(df["datetime"])
        # 取当天第一条数据的 open
        df_today = df[df["datetime"].dt.strftime("%Y-%m-%d") == data_date]
        if df_today.empty:
            stock_logger.debug(
                "[today_open] No CSV data for stock=%s on %s", stock_code, data_date,
            )
            return None
        today_open = float(df_today.iloc[0]["open"])
        stock_logger.debug(
            "[today_open] Got today_open=%s from CSV for stock=%s", today_open, stock_code,
        )
        return today_open
    except Exception as e:
        stock_logger.error("[today_open] Failed reading CSV %s: %s", csv_file, str(e))
        return None


def _get_today_open_realtime(stock_code, data_dict):
    """实时模式下获取当日开盘价：先查 MongoDB，没有再查 akshare。"""
    data_date = data_dict["datetime"][:10]
    # 先查 MongoDB
    client = None
    mongo_open = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[STOCK_DB_15MIN_NAME]
        collection = db[STOCK_KLINE_15MIN_COLLECTION]
        doc = collection.find_one(
            {
                "stock_code": stock_code,
                "datetime": {"$regex": f"^{data_date}"},
            },
            sort=[("datetime", 1)],
        )
        if doc:
            mongo_open = float(doc.get("open", 0))
            stock_logger.debug(
                "[today_open] Got today_open=%s from MongoDB for stock=%s", mongo_open, stock_code,
            )
    except Exception as e:
        stock_logger.error("[today_open] MongoDB query failed for stock=%s: %s", stock_code, str(e))
    finally:
        if client:
            client.close()

    if mongo_open is not None:
        return mongo_open

    # 查 akshare
    try:
        df = ak.stock_zh_a_hist_min_em(
            symbol=stock_code,
            period="15",
            adjust="qfq",
            start_date=data_date,
            end_date=data_date,
        )
        if df is not None and not df.empty:
            today_open = float(df.iloc[0]["开盘"])
            stock_logger.debug(
                "[today_open] Got today_open=%s from akshare for stock=%s", today_open, stock_code,
            )
            return today_open
    except Exception as e:
        stock_logger.error("[today_open] akshare query failed for stock=%s: %s", stock_code, str(e))

    stock_logger.debug("[today_open] Failed to get today_open for stock=%s on %s", stock_code, data_date)
    return None


def check_price_variant(data_dict, today_open):
    """计算涨跌幅百分比。

    Returns:
        float | None: variant_pct，today_open 为 None 时返回 None
    """
    if today_open is None or today_open == 0:
        return None
    close = data_dict["close"]
    variant_pct = (close - today_open) / today_open * 100
    stock_logger.debug(
        "[variant] stock=%s, close=%s, today_open=%s, variant_pct=%.2f%%",
        data_dict["stock_code"], close, today_open, variant_pct,
    )
    return variant_pct


def _determine_current_level(variant_pct):
    """根据 variant_pct 确定当前所处的最高阶梯档位。

    Returns:
        int | None: 当前档位，如 -5, -7, -9, 5, 7, 9，不在任何档位则返回 None
    """
    if variant_pct < 0:
        for level in DOWN_ALERT_LEVELS:
            if variant_pct <= level:
                continue
            # variant_pct > level (less negative), return previous level
            idx = DOWN_ALERT_LEVELS.index(level)
            if idx == 0:
                return None  # variant > -5, not in any down level
            return DOWN_ALERT_LEVELS[idx - 1]
        # variant_pct <= all levels (e.g. -9.5%)
        return DOWN_ALERT_LEVELS[-1]
    else:
        for level in UP_ALERT_LEVELS:
            if variant_pct < level:
                idx = UP_ALERT_LEVELS.index(level)
                if idx == 0:
                    return None  # variant < 5, not in any up level
                return UP_ALERT_LEVELS[idx - 1]
        # variant_pct >= all levels (e.g. 9.5%)
        return UP_ALERT_LEVELS[-1]


def evaluate_alert(stock_code, variant_pct, alert_state, today_open):
    """根据阶梯告警规则判断是否需要发送告警邮件。

    Args:
        stock_code: 股票代码
        variant_pct: 当前涨跌幅百分比
        alert_state: 该股票当前的告警状态 dict
        today_open: 当日开盘价

    Returns:
        tuple[str | None, dict]: (alert_reason, updated_alert_state)
    """
    if variant_pct is None:
        return None, alert_state

    # 涨跌停极限不再发送
    if variant_pct <= LIMIT_DOWN_PCT:
        stock_logger.debug(
            "[alert] stock=%s at limit_down %.2f%%, suppressing alert", stock_code, variant_pct,
        )
        return None, alert_state
    if variant_pct >= LIMIT_UP_PCT:
        stock_logger.debug(
            "[alert] stock=%s at limit_up %.2f%%, suppressing alert", stock_code, variant_pct,
        )
        return None, alert_state

    over_flag = alert_state.get("over_5pct_flag")
    last_level = alert_state.get("last_alerted_level")

    # ---- 首次穿越阈值边界 ----
    if over_flag is None:
        if variant_pct <= DOWN_ALERT_LEVELS[0]:
            alert_state["over_5pct_flag"] = "down"
            alert_state["last_alerted_level"] = DOWN_ALERT_LEVELS[0]
            reason = f"首次下跌超{abs(DOWN_ALERT_LEVELS[0])}%%，当前涨跌幅 {variant_pct:+.2f}%%"
            stock_logger.debug(
                "[alert] stock=%s first down cross, variant=%.2f%%, flag=down, level=%d",
                stock_code, variant_pct, DOWN_ALERT_LEVELS[0],
            )
            return reason, alert_state
        elif variant_pct >= UP_ALERT_LEVELS[0]:
            alert_state["over_5pct_flag"] = "up"
            alert_state["last_alerted_level"] = UP_ALERT_LEVELS[0]
            reason = f"首次上涨超{UP_ALERT_LEVELS[0]}%%，当前涨跌幅 {variant_pct:+.2f}%%"
            stock_logger.debug(
                "[alert] stock=%s first up cross, variant=%.2f%%, flag=up, level=+%d",
                stock_code, variant_pct, UP_ALERT_LEVELS[0],
            )
            return reason, alert_state
        else:
            # |variant_pct| < 阈值，清除 last_alerted_level（保持 over_5pct_flag 为 None）
            if last_level is not None:
                alert_state["last_alerted_level"] = None
            return None, alert_state

    # ---- 回归检查（回到开盘价1%以内） ----
    if over_flag == "down" and variant_pct > -1:
        old_flag = alert_state["over_5pct_flag"]
        alert_state["over_5pct_flag"] = None
        alert_state["last_alerted_level"] = None
        reason = f"股价回归至开盘价1%%以内，当前涨跌幅 {variant_pct:+.2f}%%"
        stock_logger.debug(
            "[alert] stock=%s regression from down, variant=%.2f%%, flag %s -> None",
            stock_code, variant_pct, old_flag,
        )
        return reason, alert_state
    elif over_flag == "up" and variant_pct < 1:
        old_flag = alert_state["over_5pct_flag"]
        alert_state["over_5pct_flag"] = None
        alert_state["last_alerted_level"] = None
        reason = f"股价回归至开盘价1%%以内，当前涨跌幅 {variant_pct:+.2f}%%"
        stock_logger.debug(
            "[alert] stock=%s regression from up, variant=%.2f%%, flag %s -> None",
            stock_code, variant_pct, old_flag,
        )
        return reason, alert_state

    # ---- 方向变更处理（flag 方向与当前 variant 方向不一致） ----
    if over_flag == "down" and variant_pct > 0:
        # 已从下跌转为上涨（但尚未触发回归），由回归逻辑在前一步处理，此处为防御性代码
        current_level = _determine_current_level(variant_pct)
        if current_level is not None and current_level >= UP_ALERT_LEVELS[0]:
            stock_logger.debug(
                "[alert] stock=%s direction switch down->up, variant=%.2f%%", stock_code, variant_pct,
            )
            alert_state["over_5pct_flag"] = "up"
            alert_state["last_alerted_level"] = current_level
            reason = f"方向转为上涨，当前涨跌幅 {variant_pct:+.2f}%%"
            return reason, alert_state
        return None, alert_state
    if over_flag == "up" and variant_pct < 0:
        current_level = _determine_current_level(variant_pct)
        if current_level is not None and current_level <= DOWN_ALERT_LEVELS[0]:
            stock_logger.debug(
                "[alert] stock=%s direction switch up->down, variant=%.2f%%", stock_code, variant_pct,
            )
            alert_state["over_5pct_flag"] = "down"
            alert_state["last_alerted_level"] = current_level
            reason = f"方向转为下跌，当前涨跌幅 {variant_pct:+.2f}%%"
            return reason, alert_state
        return None, alert_state

    # ---- 阶梯告警逻辑 ----
    current_level = _determine_current_level(variant_pct)

    if current_level is None:
        # 回到阈值以内：只有当 over_5pct_flag 也为 None 时才清零 last_alerted_level。
        # 如果 over_5pct_flag 仍在（首次穿越后的阈值内振荡），保留 last_alerted_level，
        # 防止再次穿越阈值时重复告警（需求 L320：只有彻底回归才清零，为下一轮穿越做准备）。
        if last_level is not None and alert_state.get("over_5pct_flag") is None:
            stock_logger.debug(
                "[alert] stock=%s back within threshold (variant=%.2f%%), resetting last_alerted_level",
                stock_code, variant_pct,
            )
            alert_state["last_alerted_level"] = None
        elif last_level is not None:
            stock_logger.debug(
                "[alert] stock=%s back within threshold but over_5pct_flag=%s, variant=%.2f%%, keeping last_alerted_level=%s",
                stock_code, alert_state.get("over_5pct_flag"), variant_pct, last_level,
            )
        return None, alert_state

    if last_level is None:
        alert_state["last_alerted_level"] = current_level
        reason = f"当前涨跌幅 {variant_pct:+.2f}%%，触发阶梯告警档位 {current_level:+.0f}%%"
        stock_logger.debug(
            "[alert] stock=%s firing alert, variant=%.2f%%, level=%d (was None)",
            stock_code, variant_pct, current_level,
        )
        return reason, alert_state

    if current_level == last_level:
        stock_logger.debug(
            "[alert] stock=%s suppressing, variant=%.2f%%, level=%d already alerted",
            stock_code, variant_pct, current_level,
        )
        return None, alert_state

    if abs(current_level) > abs(last_level):
        alert_state["last_alerted_level"] = current_level
        reason = f"当前涨跌幅 {variant_pct:+.2f}%%，触发阶梯告警档位 {current_level:+.0f}%%"
        stock_logger.debug(
            "[alert] stock=%s firing alert, variant=%.2f%%, level=%d (was %d)",
            stock_code, variant_pct, current_level, last_level,
        )
        return reason, alert_state

    # |current_level| < |last_level| but still >= 5%: 回退，不发邮件，不改变 last_alerted_level
    stock_logger.debug(
        "[alert] stock=%s suppressing retreat, variant=%.2f%%, current_level=%d, last_level=%d",
        stock_code, variant_pct, current_level, last_level,
    )
    return None, alert_state


def send_alert_email(stock_code, stock_short_name, alert_reason, variant_pct,
                     data_dict, today_open):
    """发送告警邮件。

    Returns:
        bool: 成功返回 True
    """
    from scripts.mail.mail_utils import send_email

    subject = (
        f"[Stock Alert] {stock_code}({stock_short_name}) "
        f"price variant {variant_pct:+.2f}%"
    )
    body_lines = [
        f"股票代码: {stock_code}",
        f"股票简称: {stock_short_name}",
        f"当前价格: {data_dict['close']}",
        f"开盘价: {today_open}",
        f"涨跌幅: {variant_pct:+.2f}%",
        f"告警原因: {alert_reason}",
        f"时间: {data_dict['datetime']}",
        f"最高价: {data_dict['high']}",
        f"最低价: {data_dict['low']}",
        f"成交量: {data_dict['volume']}",
    ]
    body = "\n".join(body_lines)

    stock_logger.debug(
        "[email] Sending alert for stock=%s, reason=%s, variant=%.2f%%, to=%s",
        stock_code, alert_reason, variant_pct, EMAIL,
    )
    try:
        return send_email(subject, body, to_email=EMAIL)
    except Exception as e:
        stock_logger.error("[email] Failed to send for stock=%s: %s", stock_code, str(e))
        return False


def _is_trading_time(ts):
    """判断给定时间是否处于交易时段内。

    Args:
        ts: datetime 对象

    Returns:
        bool: True 表示在交易时段内
    """
    date_str = ts.strftime("%Y-%m-%d")
    # A_STOCK_HOLIDAYS 格式为 [[start_date, end_date], ...]
    for start_date, end_date in A_STOCK_HOLIDAYS:
        if start_date <= date_str <= end_date:
            return False
    if ts.weekday() >= 5:
        return False
    t = ts.strftime("%H:%M")
    if MARKET_HOURS_START <= t < MARKET_HOURS_MID_START:
        return True
    if MARKET_HOURS_MID_END <= t < MARKET_HOURS_END:
        return True
    return False


def _get_next_trading_timestamp(ts):
    """模拟模式：从 ts 开始递增，找到下一个交易时段内的时间点。

    Args:
        ts: 当前 datetime

    Returns:
        datetime: 下一个交易时间点
    """
    original_ts = ts
    # 最多查找 365 天，防止死循环
    max_iterations = 365 * 24 * 6  # 每天最多 144 个10分钟间隔
    iterations = 0
    while not _is_trading_time(ts) and iterations < max_iterations:
        ts += timedelta(minutes=MONITOR_INTERVAL_MINUTES)
        iterations += 1

    if not _is_trading_time(ts):
        stock_logger.error("[trading_time] Could not find next trading time after %s", original_ts)
        return original_ts + timedelta(days=1)

    if ts.date() != original_ts.date():
        stock_logger.debug(
            "[trading_time] Skipped from %s to %s (crossed date boundary)",
            original_ts.strftime("%Y-%m-%d %H:%M:%S"),
            ts.strftime("%Y-%m-%d %H:%M:%S"),
        )
    elif ts != original_ts:
        stock_logger.debug(
            "[trading_time] Skipped from %s to %s",
            original_ts.strftime("%Y-%m-%d %H:%M:%S"),
            ts.strftime("%Y-%m-%d %H:%M:%S"),
        )
    return ts


def _should_monitor_run():
    """实时模式：判断当前是否在交易时间。不在交易时间时 sleep 等待。

    Returns:
        bool: True 表示可以继续监控
    """
    if not hasattr(_should_monitor_run, "_wait_logged"):
        _should_monitor_run._wait_logged = False

    now = datetime.now()
    if _is_trading_time(now):
        _should_monitor_run._wait_logged = False  # 回到交易时间，重置等待标志
        return True
    # 首次进入等待时输出日志，避免刷屏
    if not _should_monitor_run._wait_logged:
        stock_logger.debug(
            "[trading_time] Outside trading hours at %s, waiting...",
            now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        _should_monitor_run._wait_logged = True
    # 可中断的 sleep，每秒检查一次退出标志
    for _ in range(60):
        if _shutdown_requested:
            break
        time.sleep(1)
    return False


def _reset_alert_states(alert_states):
    """收盘时重置所有股票的 alert_state。"""
    reset_count = 0
    for code, state in alert_states.items():
        if state.get("over_5pct_flag") is not None or state.get("last_alerted_level") is not None:
            state["over_5pct_flag"] = None
            state["last_alerted_level"] = None
            reset_count += 1
    if reset_count > 0:
        stock_logger.debug("[reset] Reset alert states for %d stocks", reset_count)


def run_stock_monitor_price_variant():
    """监控主循环。"""
    stock_logger.debug("=== Stock Price Variant Monitor Started ===")

    mode_name = "SIMULATE" if IS_SIMULATE_MODE else "REAL"
    stock_logger.debug(
        "[monitor] Mode=%s, stocks=%s, interval=%dmin, threshold=%.1f%%, "
        "down_levels=%s, up_levels=%s",
        mode_name,
        MONITOR_STOCK_CODES,
        MONITOR_INTERVAL_MINUTES,
        PRICE_VARIANT_THRESHOLD,
        DOWN_ALERT_LEVELS,
        UP_ALERT_LEVELS,
    )

    alert_states = {code: {"last_alerted_level": None, "over_5pct_flag": None}
                    for code in MONITOR_STOCK_CODES}

    if IS_SIMULATE_MODE:
        _run_simulate_loop(alert_states)
    else:
        _run_realtime_loop(alert_states)

    stock_logger.debug("=== Stock Price Variant Monitor Stopped ===")


def _simulate_is_stock_data_ended(stock_code, timestamp):
    """检查 timestamp 是否已超过该股票的数据截止时间。"""
    data_dir = _get_data_dir()
    info_file = os.path.join(data_dir, f"{stock_code}_info.json")
    try:
        with open(info_file, "r", encoding="utf-8") as f:
            info = json.load(f)
        end_time = info.get("end_time")
        if end_time:
            end_dt = datetime.strptime(end_time, "%Y-%m-%d") + timedelta(days=1)
            return timestamp >= end_dt
    except Exception:
        pass
    return False


def _run_simulate_loop(alert_states):
    current_timestamp = datetime.strptime(START_SIMULATION_TIMESTAMP, "%Y-%m-%d %H:%M:%S")
    current_timestamp = _get_next_trading_timestamp(current_timestamp)

    finished_stocks = set()
    round_count = 0
    last_data_timestamps = {code: current_timestamp for code in MONITOR_STOCK_CODES}
    last_market_date = None
    max_rounds = 50000  # 安全上限，防止死循环

    while round_count < max_rounds and not _shutdown_requested:
        round_count += 1

        # 收盘重置：检测是否跨入新交易日
        current_date = current_timestamp.strftime("%Y-%m-%d")
        if last_market_date is not None and current_date != last_market_date:
            _reset_alert_states(alert_states)
        last_market_date = current_date

        # 每20轮输出一次进度
        if round_count % 20 == 0:
            stock_logger.debug(
                "[monitor] Progress: round=%d, timestamp=%s, finished=%d/%d",
                round_count,
                current_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                len(finished_stocks),
                len(MONITOR_STOCK_CODES),
            )

        all_finished = True
        for stock_code in MONITOR_STOCK_CODES:
            if _shutdown_requested:
                break
            if stock_code in finished_stocks:
                continue

            data = request_stock_15min_data(stock_code, current_timestamp)
            if data is None:
                # 只有 timestamp 超过数据截止时间才标记为 finished
                if _simulate_is_stock_data_ended(stock_code, current_timestamp):
                    stock_logger.debug(
                        "[monitor] Stock %s data ended, last valid timestamp=%s",
                        stock_code,
                        last_data_timestamps[stock_code].strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    finished_stocks.add(stock_code)
                continue

            all_finished = False
            last_data_timestamps[stock_code] = current_timestamp

            today_open = _get_today_open(stock_code, data,
                                          query_date=current_timestamp.strftime("%Y-%m-%d"))
            if today_open is None:
                continue

            variant_pct = check_price_variant(data, today_open)
            if variant_pct is None:
                continue

            alert_reason, alert_states[stock_code] = evaluate_alert(
                stock_code, variant_pct, alert_states[stock_code], today_open,
            )

            if alert_reason is not None:
                stock_short_name = _get_stock_short_name(stock_code)
                send_alert_email(
                    stock_code, stock_short_name, alert_reason, variant_pct, data, today_open,
                )

        if all_finished and len(finished_stocks) >= len(MONITOR_STOCK_CODES):
            stock_logger.debug(
                "[monitor] All stocks finished, total_rounds=%d", round_count,
            )
            break

        # 检查是否超过收盘时间，重置 alert_states
        if current_timestamp.strftime("%H:%M") >= MARKET_HOURS_END:
            _reset_alert_states(alert_states)

        # 推进时间
        current_timestamp += timedelta(minutes=MONITOR_INTERVAL_MINUTES)
        current_timestamp = _get_next_trading_timestamp(current_timestamp)

        # 模拟加速：实际间隔 / 加速倍数 = sleep 秒数
        # e.g. 10min * 60 / 80 = 7.5s 每轮
        sleep_seconds = (MONITOR_INTERVAL_MINUTES * 60) / SIMULATE_SPEED_MULTIPLIER
        if sleep_seconds > 0.01:
            for _ in range(int(sleep_seconds)):
                if _shutdown_requested:
                    break
                time.sleep(1)


def _run_realtime_loop(alert_states):
    last_market_date = None
    was_in_market = False

    while True:
        if _shutdown_requested:
            stock_logger.debug("[monitor] Shutdown requested, exiting realtime loop")
            break
        if not _should_monitor_run():
            if was_in_market:
                stock_logger.debug("Market closed, monitoring paused")
            was_in_market = False
            continue

        if not was_in_market:
            stock_logger.debug("Market open, monitoring started")
        was_in_market = True

        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        if last_market_date is not None and current_date != last_market_date:
            _reset_alert_states(alert_states)
        last_market_date = current_date

        # 收盘重置
        if now.strftime("%H:%M") >= MARKET_HOURS_END:
            _reset_alert_states(alert_states)

        for stock_code in MONITOR_STOCK_CODES:
            if _shutdown_requested:
                break
            try:
                data = request_stock_15min_data(stock_code)
                if data is None:
                    continue

                save_15min_data_to_mongo(data)

                today_open = _get_today_open(stock_code, data)
                if today_open is None:
                    continue

                variant_pct = check_price_variant(data, today_open)
                if variant_pct is None:
                    continue

                alert_reason, alert_states[stock_code] = evaluate_alert(
                    stock_code, variant_pct, alert_states[stock_code], today_open,
                )

                if alert_reason is not None:
                    stock_short_name = _get_stock_short_name(stock_code)
                    send_alert_email(
                        stock_code, stock_short_name, alert_reason, variant_pct, data, today_open,
                    )
            except Exception as e:
                stock_logger.error(
                    "[monitor] Unexpected error for stock=%s, mode=REAL: %s",
                    stock_code, str(e),
                )

        # 可中断的 sleep，每 1 秒检查一次退出标志
        for _ in range(int(MONITOR_INTERVAL_MINUTES * 60)):
            if _shutdown_requested:
                break
            time.sleep(1)


def _setup_signal_handlers():
    def handler(sig, frame):
        global _shutdown_requested
        _shutdown_requested = True
        stock_logger.debug("[monitor] Received signal %s, shutting down gracefully...", sig)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main():
    # 开发阶段将日志同时输出到控制台，方便观察运行状态
    _logger = logging.getLogger("stock")
    if not any(isinstance(h, logging.StreamHandler) for h in _logger.handlers):
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter(
            "[%(asctime)s][%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        _logger.addHandler(console)

    _setup_signal_handlers()
    run_stock_monitor_price_variant()


if __name__ == "__main__":
    main()
