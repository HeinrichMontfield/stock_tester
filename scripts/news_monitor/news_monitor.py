import json
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

import news_fetcher
import news_query
import news_store
from news_mail import send_news_email

KEYWORDS_STATE_FILE = os.path.join(os.path.dirname(__file__), "_keywords_state.json")

SECONDS_PER_MINUTE = 60
INTERVAL_MARKET = 10 * SECONDS_PER_MINUTE
INTERVAL_OFF_HOURS = 120 * SECONDS_PER_MINUTE
TZ_UTC8 = timezone(timedelta(hours=8))

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


def _is_market_hours(market_start: str, market_end: str) -> bool:
    """Check if current UTC+8 time is within market hours [start, end)."""
    now = datetime.now(TZ_UTC8)
    current_minutes = now.hour * 60 + now.minute

    def _parse_minutes(t: str) -> int:
        h, m = t.strip().split(":")
        return int(h) * 60 + int(m)

    return _parse_minutes(market_start) <= current_minutes < _parse_minutes(market_end)


def _seconds_until_market_start(market_start: str) -> int:
    """Seconds until next market_start in UTC+8. 0 if already past."""
    now = datetime.now(TZ_UTC8)
    h, m = market_start.strip().split(":")
    target = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return int((target - now).total_seconds())


def _handle_keyword_change(keywords: list[str]):
    """Handle newly added keywords.

    Marks old (>12h) matched news as sent immediately to silence them.
    Recent (<=12h) news are left unsent so the normal cycle picks them up
    in a single combined email with any newly fetched items.
    """
    all_unsent = news_store.get_unsent_news()
    if not all_unsent:
        print("[news_monitor] Keyword change: no unsent news to process")
        return

    cutoff = datetime.now() - timedelta(hours=12)
    old_ids = [n["_id"] for n in all_unsent
               if n.get("time", datetime.min) < cutoff and "_id" in n]
    recent_count = len(all_unsent) - len(old_ids)

    if old_ids:
        news_store.mark_email_sent(old_ids)
        print(f"[news_monitor] Keyword change: silenced {len(old_ids)} older (>12h) news, "
              f"leaving {recent_count} recent news for normal cycle")
    else:
        print(f"[news_monitor] Keyword change: all {recent_count} unsent news within 12h, "
              f"left for normal cycle")


def main():
    global running

    print("[news_monitor] Starting news monitor...")

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    load_dotenv()
    keywords_raw = os.getenv("MONITOR_KEYWORDS", "")
    keywords = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]
    print(f"[news_monitor] Monitor keywords: {keywords}")

    market_start = os.getenv("MARKET_HOURS_START", "09:00")
    market_end = os.getenv("MARKET_HOURS_END", "15:00")
    print(f"[news_monitor] Market hours: {market_start} - {market_end} (UTC+8)")

    news_store.init_db()

    prev_keywords = _load_keywords_state()
    if prev_keywords is not None and prev_keywords != keywords:
        print(f"[news_monitor] Keywords changed: {prev_keywords} -> {keywords}")
        news_store.reindex_all_keywords(keywords)
        _handle_keyword_change(keywords)
    _save_keywords_state(keywords)

    print(f"[news_monitor] Configuration loaded. {len(keywords)} keywords")

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

            in_market = _is_market_hours(market_start, market_end)
            interval = INTERVAL_MARKET if in_market else INTERVAL_OFF_HOURS
            phase = "market" if in_market else "off-hours"
            print(
                f"[news_monitor] Cycle complete [{phase}]: fetched={len(news_items)}, "
                f"new={new_count}, matched={len(matched_ids)}, sent={send_count}, "
                f"next_interval={interval}s"
            )
        except Exception as e:
            print(f"[news_monitor] Cycle error: {e}")

        if not running:
            break

        in_market = _is_market_hours(market_start, market_end)
        if in_market:
            interval = INTERVAL_MARKET
        else:
            interval = INTERVAL_OFF_HOURS
            seconds_to_start = _seconds_until_market_start(market_start)
            if seconds_to_start < interval:
                interval = seconds_to_start

        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    print("[news_monitor] News monitor stopped")


if __name__ == "__main__":
    main()
