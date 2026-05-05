from datetime import datetime

import news_store
from mail.mail_utils import send_email


def build_email_subject(keywords: list[str], fetch_time: str) -> str:
    """Build email subject line.

    Format: [keyword1-keyword2]-[fetch_time]
    """
    kw_part = "-".join(keywords)
    return f"[{kw_part}]-[{fetch_time}]"


def build_email_body(news_list: list[dict]) -> str:
    """Build plain-text email body from news items.

    Each item formatted as:
        news_time
        news_content
    Separated by blank lines.
    """
    parts = []
    for item in news_list:
        t = item.get("time", "")
        if isinstance(t, datetime):
            t = t.strftime("%Y-%m-%d %H:%M")
        content = item.get("content", "")
        parts.append(f"{t}\r\n{content}")
    return "\r\n\r\n".join(parts)


def send_news_email(keywords: list[str], unsent_news: list[dict]) -> bool:
    """Build and send email for unsent news items.

    Marks items as email_sent on success.
    """
    if not unsent_news:
        print("[news_mail] No unsent news to email")
        return True

    fetch_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    subject = build_email_subject(keywords, fetch_time)
    body = build_email_body(unsent_news)

    print(f"[news_mail] Sending email with {len(unsent_news)} news items")
    success = send_email(subject, body)

    if success:
        news_ids = [item["_id"] for item in unsent_news if "_id" in item]
        if news_ids:
            news_store.mark_email_sent(news_ids)
        print("[news_mail] Email sent and news marked as sent")
    else:
        print("[news_mail] Failed to send email")

    return success
