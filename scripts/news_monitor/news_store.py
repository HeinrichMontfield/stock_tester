import os

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


def _get_collection():
    """Create a new connection and return the collection object."""
    client = MongoClient(MONGO_URI, connectTimeoutMS=5000, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    return client, db[COLLECTION_NAME]


def _close(client: MongoClient):
    """Close the MongoDB connection."""
    try:
        client.close()
    except Exception as e:
        stock_logger.debug("[news_store] Error closing MongoDB connection: %s", e)


def init_db() -> None:
    """Ensure MongoDB indexes exist."""
    client, col = _get_collection()
    try:
        col.create_index("email_sent")
        col.create_index("time")
        col.create_index("matched_keywords")
        stock_logger.debug("[news_store] MongoDB indexes initialized")
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Failed to create indexes: %s", e)
    finally:
        _close(client)


def news_exists(news_id: str) -> bool:
    """Check if a news item with the given id already exists."""
    client, col = _get_collection()
    try:
        count = col.count_documents({"_id": news_id}, limit=1)
        return count > 0
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Error checking existence of %s: %s", news_id, e)
        return False
    finally:
        _close(client)


def save_news(news_item: dict, keywords: list[str]) -> bool:
    """Save a news item to MongoDB.

    Checks content for matching keywords and stores matched_keywords.
    Does not store if content is empty.
    """
    content = news_item.get("content", "")
    if not content or not content.strip():
        stock_logger.debug("[news_store] Skipping empty content for %s", news_item.get('id'))
        return False

    matched = [kw for kw in keywords if kw in content]
    doc = {
        "_id": news_item["id"],
        "time": news_item["time"],
        "content": content,
        "matched_keywords": matched,
        "email_sent": False,
    }
    title = news_item.get("title", "")
    if title:
        # CLS新闻有独立标题字段，保存到MongoDB
        doc["title"] = title

    client, col = _get_collection()
    try:
        col.insert_one(doc)
        stock_logger.debug("[news_store] Saved news %s with keywords: %s", doc['_id'], matched)
        return True
    except errors.DuplicateKeyError:
        stock_logger.debug("[news_store] News %s already exists, skipped", doc['_id'])
        return False
    except errors.PyMongoError as e:
        stock_logger.error("[news_store] Failed to save news %s: %s", doc['_id'], e)
        return False
    finally:
        _close(client)


def get_news_basic(news_id: str) -> dict | None:
    """Get basic info for a news item by id.

    Returns dict with time, content_summary (first 100 chars), email_sent.
    """
    client, col = _get_collection()
    try:
        doc = col.find_one({"_id": news_id}, {"_id": 0, "time": 1, "content": 1, "email_sent": 1})
        if doc:
            content = doc.get("content", "")
            doc["content_summary"] = content[:100]
            del doc["content"]
        return doc
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Error querying %s: %s", news_id, e)
        return None
    finally:
        _close(client)


def get_news_content(news_id: str) -> str | None:
    """Get full content of a news item by id."""
    client, col = _get_collection()
    try:
        doc = col.find_one({"_id": news_id}, {"_id": 0, "content": 1})
        return doc.get("content") if doc else None
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Error getting content for %s: %s", news_id, e)
        return None
    finally:
        _close(client)


def search_by_content(keyword: str) -> list[dict]:
    """Search news by exact match on matched_keywords array."""
    client, col = _get_collection()
    try:
        cursor = col.find({"matched_keywords": keyword}, {"_id": 0})
        return list(cursor)
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Error searching by keyword '%s': %s", keyword, e)
        return []
    finally:
        _close(client)

# get_unsent_news() 和 get_unsent_news_since() 返回的是 MongoDB 完整文档，每个 item 都自带 matched_keywords 字段（如 ["keyword1", "keyword2"]）。
def get_unsent_news() -> list[dict]:
    """Get all news items where email_sent is false."""
    client, col = _get_collection()
    try:
        total = col.count_documents({})
        with_false = col.count_documents({"email_sent": False})
        with_nonempty = col.count_documents({"matched_keywords": {"$ne": []}})
        both = col.count_documents({"email_sent": False, "matched_keywords": {"$ne": []}})
        stock_logger.debug("[news_store] get_unsent_news debug: total=%d, email_sent=False=%d, "
              "matched_nonempty=%d, both=%d", total, with_false, with_nonempty, both)
        cursor = col.find({"email_sent": False, "matched_keywords": {"$ne": []}})
        return list(cursor)
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Error getting unsent news: %s", e)
        return []
    finally:
        _close(client)


def get_unsent_news_since(cutoff_time) -> list[dict]:
    """Get unsent news with matched keywords since a cutoff time."""
    client, col = _get_collection()
    try:
        cursor = col.find({
            "email_sent": False,
            "matched_keywords": {"$ne": []},
            "time": {"$gte": cutoff_time},
        })
        return list(cursor)
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Error getting unsent news since %s: %s", cutoff_time, e)
        return []
    finally:
        _close(client)


def mark_email_sent(news_ids: list[str]) -> None:
    """Batch mark news items as email_sent=true."""
    if not news_ids:
        return
    client, col = _get_collection()
    try:
        result = col.update_many(
            {"_id": {"$in": news_ids}},
            {"$set": {"email_sent": True}},
        )
        stock_logger.debug("[news_store] Marked %d news as email_sent", result.modified_count)
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Error marking email_sent: %s", e)
    finally:
        _close(client)


def reindex_all_keywords(keywords: list[str]) -> None:
    """Recalculate matched_keywords for all documents."""
    client, col = _get_collection()
    try:
        cursor = col.find({}, {"_id": 1, "content": 1})
        updated = 0
        for doc in cursor:
            matched = [kw for kw in keywords if kw in doc.get("content", "")]
            col.update_one({"_id": doc["_id"]}, {"$set": {"matched_keywords": matched}})
            updated += 1
        stock_logger.debug("[news_store] Reindexed matched_keywords for %d documents", updated)
    except errors.PyMongoError as e:
        stock_logger.debug("[news_store] Error during reindex: %s", e)
    finally:
        _close(client)
