import datetime
import os

import pandas as pd

import akshare as ak
from dotenv import load_dotenv

from scripts.utils import stock_logger

load_dotenv()
NEWS_SOURCE = os.getenv("NEWS_SOURCE", "sina")


def fetch_news() -> list[dict]:
    """Fetch latest news based on NEWS_SOURCE env config."""
    if NEWS_SOURCE == "cls":
        return _fetch_news_cls()
    return _fetch_news_sina()


def _fetch_news_sina() -> list[dict]:
    """Fetch latest news from sina finance via akshare.

    Returns:
        List of dicts with keys: id, time (datetime), content.
        Returns empty list on failure.
    """
    stock_logger.debug("[news_fetcher] Fetching news from sina finance...")
    try:
        df: pd.DataFrame = ak.stock_info_global_sina()
    except Exception as e:
        stock_logger.error("[news_fetcher] Failed to fetch news: %s", e)
        return []

    news_list = []
    for _, row in df.iterrows():
        time_str = str(row.get("时间", ""))
        content = row.get("内容", "")

        if pd.isna(content) or not str(content).strip():
            continue

        content = str(content).strip()
        news_id = "sina_" + time_str.replace(" ", "-").replace(":", "-")

        try:
            news_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            stock_logger.debug("[news_fetcher] Skipping news with unparseable time: %s", time_str)
            continue

        news_list.append({
            "id": news_id,
            "time": news_time,
            "content": content,
        })

    stock_logger.debug("[news_fetcher] Fetched %d news items", len(news_list))
    return news_list


def _fetch_news_cls() -> list[dict]:
    """Fetch latest news from cls.cn (财联社) via akshare.

    CLS DataFrame columns: 标题, 内容, 发布日期(datetime.date), 发布时间(datetime.time).
    Returns list of dicts with keys: id, time (datetime), content, title.
    Returns empty list on failure.
    """
    stock_logger.debug("[news_fetcher] Fetching news from cls.cn...")
    try:
        df: pd.DataFrame = ak.stock_info_global_cls()
    except Exception as e:
        stock_logger.error("[news_fetcher] Failed to fetch CLS news: %s", e)
        return []

    news_list = []
    for i, (_, row) in enumerate(df.iterrows()):
        title = str(row.get("标题", "")).strip() if not pd.isna(row.get("标题", "")) else ""
        content = str(row.get("内容", "")).strip() if not pd.isna(row.get("内容", "")) else ""

        if not content and not title:
            continue

        pub_date = row.get("发布日期")
        pub_time = row.get("发布时间")

        if pd.isna(pub_date) or pd.isna(pub_time):
            stock_logger.debug("[news_fetcher] Skipping CLS news with missing date/time")
            continue

        try:
            news_time = datetime.datetime.combine(
                pub_date.to_pydatetime().date() if hasattr(pub_date, 'to_pydatetime') else pub_date,
                pub_time.to_pydatetime().time() if hasattr(pub_time, 'to_pydatetime') else pub_time,
            )
        except (ValueError, TypeError, AttributeError):
            stock_logger.debug("[news_fetcher] Skipping CLS news with unparseable time: %s %s", pub_date, pub_time)
            continue

        time_str = news_time.strftime("%Y-%m-%d-%H-%M-%S")
        news_id = f"cls_{time_str}_{i}"

        news_list.append({
            "id": news_id,
            "time": news_time,
            "content": content,
            "title": title,
        })

    stock_logger.debug("[news_fetcher] Fetched %d CLS news items", len(news_list))
    return news_list
