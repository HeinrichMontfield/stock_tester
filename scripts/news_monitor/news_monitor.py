import json
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

import news_fetcher
import news_store
from news_mail import send_news_email
from scripts.utils import stock_logger

KEYWORDS_STATE_FILE = os.path.join(os.path.dirname(__file__), "_keywords_state.json")

SECONDS_PER_MINUTE = 60
INTERVAL_MARKET = 10 * SECONDS_PER_MINUTE
INTERVAL_OFF_HOURS = 120 * SECONDS_PER_MINUTE
INTERVAL_FETCH = 10 * SECONDS_PER_MINUTE
TZ_UTC8 = timezone(timedelta(hours=8))

running = True


def _signal_handler(signum, frame):
    global running
    stock_logger.debug("\n[news_monitor] Received signal %s, shutting down...", signum)
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
        stock_logger.error("[news_monitor] Failed to save keywords state: %s", e)


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
        stock_logger.debug("[news_monitor] Keyword change: no unsent news to process")
        return

    cutoff = datetime.now() - timedelta(hours=12)
    old_ids = [n["_id"] for n in all_unsent
               if n.get("time", datetime.min) < cutoff and "_id" in n]
    recent_count = len(all_unsent) - len(old_ids)

    if old_ids:
        news_store.mark_email_sent(old_ids)
        stock_logger.debug("[news_monitor] Keyword change: silenced %d older (>12h) news, "
              "leaving %d recent news for normal cycle", len(old_ids), recent_count)
    else:
        stock_logger.debug("[news_monitor] Keyword change: all %d unsent news within 12h, "
              "left for normal cycle", recent_count)


def main():
    global running

    stock_logger.debug("[news_monitor] Starting news monitor...")

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    load_dotenv()
    keywords_raw = os.getenv("MONITOR_KEYWORDS", "")
    keywords = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]
    stock_logger.debug("[news_monitor] Monitor keywords: %s", keywords)

    market_start = os.getenv("MARKET_HOURS_START", "09:00")
    market_end = os.getenv("MARKET_HOURS_END", "15:00")
    stock_logger.debug("[news_monitor] Market hours: %s - %s (UTC+8)", market_start, market_end)

    news_store.init_db()

    prev_keywords = _load_keywords_state()
    if prev_keywords is not None and prev_keywords != keywords:
        stock_logger.debug("[news_monitor] Keywords changed: %s -> %s", prev_keywords, keywords)
        news_store.reindex_all_keywords(keywords)
        _handle_keyword_change(keywords)
    _save_keywords_state(keywords)

    stock_logger.debug("[news_monitor] Configuration loaded. %d keywords", len(keywords))

    last_email_time = None

    while running:
        try:
            news_items = news_fetcher.fetch_news()

            new_count = 0
            for item in news_items:
                if not news_store.news_exists(item["id"]):
                    news_store.save_news(item, keywords)
                    new_count += 1

            in_market = _is_market_hours(market_start, market_end)
            email_interval = INTERVAL_MARKET if in_market else INTERVAL_OFF_HOURS

            now = datetime.now()
            should_send = (last_email_time is None or
                          (now - last_email_time).total_seconds() >= email_interval)

            send_count = 0
            if should_send:
                is_first_run = last_email_time is None
                stock_logger.debug("[news_monitor] should_send=True, is_first_run=%s, in_market=%s", is_first_run, in_market)
                # 始终取全部未发送新闻，不做 time 过滤。
                # 新闻 time 字段是新浪发布时间，不是抓取时间，按 time 过滤会漏掉
                # 休市后抓到的下午旧闻（发布时间早于 last_email_time）。
                unsent_news = news_store.get_unsent_news()

                send_count = len(unsent_news)
                stock_logger.debug("[news_monitor] unsent_news count: %d", send_count)
                if unsent_news:
                    send_news_email(keywords, unsent_news)
                    # 仅在真正发送邮件后才更新 last_email_time，避免空轮询导致
                    # 下次需再等满 INTERVAL_OFF_HOURS 才能发送
                    last_email_time = now

            phase = "market" if in_market else "off-hours"
            stock_logger.debug(
                "[news_monitor] Cycle complete [%s]: fetched=%d, "
                "new=%d, sent=%d, "
                "next_fetch=%ds",
                phase, len(news_items), new_count, send_count, INTERVAL_FETCH,
            )
        except Exception as e:
            stock_logger.error("[news_monitor] Cycle error: %s", e)

        if not running:
            break

        for _ in range(int(INTERVAL_FETCH)):
            if not running:
                break
            time.sleep(1)

    stock_logger.debug("[news_monitor] News monitor stopped")


if __name__ == "__main__":
    main()
