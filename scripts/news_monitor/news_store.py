import os

from dotenv import load_dotenv
from pymongo import MongoClient, errors

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("SINA_NEWS_DB_NAME")
COLLECTION_NAME = os.getenv("SINA_NEWS_COLLECTION_NAME")


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
        print(f"[news_store] Error closing MongoDB connection: {e}")


def init_db() -> None:
    """Ensure MongoDB indexes exist."""
    client, col = _get_collection()
    try:
        col.create_index("_id", unique=True)
        col.create_index("email_sent")
        col.create_index("time")
        col.create_index("matched_keywords")
        print("[news_store] MongoDB indexes initialized")
    except errors.PyMongoError as e:
        print(f"[news_store] Failed to create indexes: {e}")
    finally:
        _close(client)


def news_exists(news_id: str) -> bool:
    """Check if a news item with the given id already exists."""
    client, col = _get_collection()
    try:
        count = col.count_documents({"_id": news_id}, limit=1)
        return count > 0
    except errors.PyMongoError as e:
        print(f"[news_store] Error checking existence of {news_id}: {e}")
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
        print(f"[news_store] Skipping empty content for {news_item.get('id')}")
        return False

    matched = [kw for kw in keywords if kw in content]
    doc = {
        "_id": news_item["id"],
        "time": news_item["time"],
        "content": content,
        "matched_keywords": matched,
        "email_sent": False,
    }

    client, col = _get_collection()
    try:
        col.insert_one(doc)
        print(f"[news_store] Saved news {doc['_id']} with keywords: {matched}")
        return True
    except errors.DuplicateKeyError:
        print(f"[news_store] News {doc['_id']} already exists, skipped")
        return False
    except errors.PyMongoError as e:
        print(f"[news_store] Failed to save news {doc['_id']}: {e}")
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
        print(f"[news_store] Error querying {news_id}: {e}")
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
        print(f"[news_store] Error getting content for {news_id}: {e}")
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
        print(f"[news_store] Error searching by keyword '{keyword}': {e}")
        return []
    finally:
        _close(client)


def get_unsent_news() -> list[dict]:
    """Get all news items where email_sent is false."""
    client, col = _get_collection()
    try:
        cursor = col.find({"email_sent": False, "matched_keywords": {"$ne": []}})
        return list(cursor)
    except errors.PyMongoError as e:
        print(f"[news_store] Error getting unsent news: {e}")
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
        print(f"[news_store] Marked {result.modified_count} news as email_sent")
    except errors.PyMongoError as e:
        print(f"[news_store] Error marking email_sent: {e}")
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
        print(f"[news_store] Reindexed matched_keywords for {updated} documents")
    except errors.PyMongoError as e:
        print(f"[news_store] Error during reindex: {e}")
    finally:
        _close(client)
