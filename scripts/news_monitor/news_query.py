import os
import datetime

from dotenv import load_dotenv
from pymongo import MongoClient, errors

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("SINA_NEWS_DB_NAME")
COLLECTION_NAME = os.getenv("SINA_NEWS_COLLECTION_NAME")


def search_stock_news(keyword: str, start_time: str, end_time: str) -> list[str]:
    """Search news by keyword within a time range.

    Args:
        keyword: Keyword to match against matched_keywords.
        start_time: Start time string in format yyyy-mm-dd-hh-mm-ss.
        end_time: End time string in format yyyy-mm-dd-hh-mm-ss.

    Returns:
        List of matching news ids.
    """
    try:
        start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d-%H-%M-%S")
        end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d-%H-%M-%S")
    except ValueError as e:
        print(f"[news_query] Invalid time format: {e}")
        return []

    print(f"[news_query] Searching news: keyword='{keyword}', from={start_time}, to={end_time}")

    client = MongoClient(MONGO_URI)
    col = client[DB_NAME][COLLECTION_NAME]
    try:
        cursor = col.find(
            {"matched_keywords": keyword, "time": {"$gte": start_dt, "$lte": end_dt}},
            {"_id": 1},
        )
        result = [doc["_id"] for doc in cursor]
        print(f"[news_query] Found {len(result)} matching news")
        return result
    except errors.PyMongoError as e:
        print(f"[news_query] Query error: {e}")
        return []
    finally:
        client.close()
