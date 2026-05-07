import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

from scripts.utils import stock_logger

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")


def send_email(subject: str, body: str, to_email: str = None) -> bool:
    """Send a plain-text email via SMTP_SSL.

    Args:
        subject: Email subject line.
        body: Plain text email body.
        to_email: Recipient address. Defaults to EMAIL (self).

    Returns:
        True if sent successfully, False otherwise.
    """
    if to_email is None:
        to_email = EMAIL

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    server = None
    stock_logger.debug("[mail_utils] Connecting to SMTP server %s:%s...", SMTP_SERVER, SMTP_PORT)
    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
        stock_logger.debug("[mail_utils] SMTP SSL connection established")
    except Exception as e:
        stock_logger.error("[mail_utils] Failed to connect to SMTP server: %s", e)
        return False

    try:
        server.login(EMAIL, PASSWORD)
        stock_logger.debug("[mail_utils] SMTP login successful")
    except smtplib.SMTPAuthenticationError as e:
        stock_logger.error("[mail_utils] SMTP login failed: authentication error: %s", e)
        return False
    except Exception as e:
        stock_logger.error("[mail_utils] SMTP login failed: %s", e)
        return False

    try:
        msg_str = msg.as_string()
        server.sendmail(EMAIL, to_email, msg_str)
        stock_logger.debug("[mail_utils] Email sent to %s", to_email)
    except Exception as e:
        stock_logger.error("[mail_utils] Failed to send email: %s", e)
        return False
    finally:
        if server:
            try:
                server.quit()
                stock_logger.debug("[mail_utils] SMTP connection closed")
            except Exception as e:
                stock_logger.debug("[mail_utils] Error closing SMTP connection: %s", e)

    return True
