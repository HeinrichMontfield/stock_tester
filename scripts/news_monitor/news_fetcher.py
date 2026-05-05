import datetime

import pandas as pd

import akshare as ak


def fetch_news() -> list[dict]:
    """Fetch latest news from sina finance via akshare.

    Returns:
        List of dicts with keys: id, time (datetime), content.
        Returns empty list on failure.
    """
    print("[news_fetcher] Fetching news from sina finance...")
    try:
        df: pd.DataFrame = ak.stock_info_global_sina()
    except Exception as e:
        print(f"[news_fetcher] Failed to fetch news: {e}")
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
            print(f"[news_fetcher] Skipping news with unparseable time: {time_str}")
            continue

        news_list.append({
            "id": news_id,
            "time": news_time,
            "content": content,
        })

    print(f"[news_fetcher] Fetched {len(news_list)} news items")
    return news_list
