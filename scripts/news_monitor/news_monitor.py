import json
import os
import signal
import sys
import time

from dotenv import load_dotenv

import news_fetcher
import news_query
import news_store
from news_mail import send_news_email

KEYWORDS_STATE_FILE = os.path.join(os.path.dirname(__file__), "_keywords_state.json")

running = True


def _signal_handler(signum, frame):
    global running
    print(f"\n[news_monitor] Received signal {signum}, shutting down...")
    running = False


def _load_keywords_state() -> list[str] | None:
    """Load previously saved keywords from state file."""
    try:
        with open(KEYWORDS_STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_keywords_state(keywords: list[str]):
    """Save current keywords to state file."""
    try:
        with open(KEYWORDS_STATE_FILE, "w") as f:
            json.dump(keywords, f)
    except Exception as e:
        print(f"[news_monitor] Failed to save keywords state: {e}")


def main():
    global running

    print("[news_monitor] Starting news monitor...")

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    load_dotenv()
    keywords_raw = os.getenv("MONITOR_KEYWORDS", "")
    keywords = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]
    print(f"[news_monitor] Monitor keywords: {keywords}")

    news_store.init_db()

    prev_keywords = _load_keywords_state()
    if prev_keywords is not None and prev_keywords != keywords:
        print(f"[news_monitor] Keywords changed: {prev_keywords} -> {keywords}")
        news_store.reindex_all_keywords(keywords)
    _save_keywords_state(keywords)

    print(f"[news_monitor] Configuration loaded. {len(keywords)} keywords, interval: 600s")

    while running:
        try:
            news_items = news_fetcher.fetch_news()

            new_count = 0
            for item in news_items:
                if not news_store.news_exists(item["id"]):
                    news_store.save_news(item, keywords)
                    new_count += 1

            matched_ids = set()
            for kw in keywords:
                now = time.strftime("%Y-%m-%d-%H-%M-%S")
                past = time.strftime("%Y-%m-%d-00-00-00")
                ids = news_query.search_stock_news(kw, past, now)
                matched_ids.update(ids)

            unsent_news = news_store.get_unsent_news()
            send_count = len(unsent_news)
            if unsent_news:
                send_news_email(keywords, unsent_news)

            print(
                f"[news_monitor] Cycle complete: fetched={len(news_items)}, "
                f"new={new_count}, matched={len(matched_ids)}, sent={send_count}"
            )
        except Exception as e:
            print(f"[news_monitor] Cycle error: {e}")

        if not running:
            break

        for _ in range(600):
            if not running:
                break
            time.sleep(1)

    print("[news_monitor] News monitor stopped")


if __name__ == "__main__":
    main()
