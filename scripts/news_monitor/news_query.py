import os
import datetime

from dotenv import load_dotenv
from pymongo import MongoClient, errors

from scripts.utils import stock_logger

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
NEWS_SOURCE = os.getenv("NEWS_SOURCE", "sina")
if NEWS_SOURCE == "cls":
    DB_NAME = os.getenv("CLS_NEWS_DB_NAME", "stock_news_cls")
    COLLECTION_NAME = os.getenv("CLS_NEWS_COLLECTION_NAME", "news_articles_cls")
else:
    DB_NAME = os.getenv("SINA_NEWS_DB_NAME", "stock_news")
    COLLECTION_NAME = os.getenv("SINA_NEWS_COLLECTION_NAME", "news_articles")


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
        stock_logger.debug("[news_query] Invalid time format: %s", e)
        return []

    stock_logger.debug("[news_query] Searching news: keyword='%s', from=%s, to=%s", keyword, start_time, end_time)

    client = MongoClient(MONGO_URI)
    col = client[DB_NAME][COLLECTION_NAME]
    try:
        cursor = col.find(
            {"matched_keywords": keyword, "time": {"$gte": start_dt, "$lte": end_dt}},
            {"_id": 1},
        )
        result = [doc["_id"] for doc in cursor]
        stock_logger.debug("[news_query] Found %d matching news", len(result))
        return result
    except errors.PyMongoError as e:
        stock_logger.error("[news_query] Query error: %s", e)
        return []
    finally:
        client.close()
