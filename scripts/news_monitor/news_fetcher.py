import datetime

import pandas as pd

import akshare as ak

from scripts.utils import stock_logger


def fetch_news() -> list[dict]:
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
