import imaplib
import email
import subprocess
import os
import smtplib
import sys
import time
import socket
import select
import signal
import threading
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from dotenv import load_dotenv

from scripts.utils import stock_logger

# 加载环境变量
load_dotenv()

# 邮件配置
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
SUBJECT_PREFIX = os.getenv("SUBJECT_PREFIX")
TRIGGER_KEYWORD = os.getenv("TRIGGER_KEYWORD")
KDJ_SCRIPT_PATH = os.getenv("KDJ_SCRIPT_PATH")
HTML_OUTPUT_FOLDER = os.getenv("HTML_OUTPUT_FOLDER")
ZIP_FILE_NAME = os.getenv("ZIP_FILE_NAME", "kdj_result.zip")
WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), "stockmail_kdj_worker.py")

# 打印关键配置（调试用，上线后可删除）
stock_logger.debug(f"[Main] Config - EMAIL: {EMAIL}")
stock_logger.debug(f"[Main] Config - SUBJECT_PREFIX: {SUBJECT_PREFIX}")
stock_logger.debug(f"[Main] Config - TRIGGER_KEYWORD: {TRIGGER_KEYWORD}")
stock_logger.debug(f"[Main] Config - WORKER_SCRIPT: {WORKER_SCRIPT}")


SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT")
IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_PORT = os.getenv("IMAP_PORT")

IDLE_TIMEOUT = 25 * 60

_current_mail = None
_current_worker = None
_processed_ids: set[bytes] = set()


def _cleanup():
    """释放 IMAP 连接和 worker 子进程"""
    global _current_mail, _current_worker
    stock_logger.debug("\n[Main] Shutting down...")
    if _current_worker and _current_worker.poll() is None:
        _current_worker.terminate()
        try:
            _current_worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _current_worker.kill()
            _current_worker.wait()
        stock_logger.debug("[Main] Worker process terminated")
    if _current_mail:
        try:
            _current_mail.logout()
            stock_logger.debug("[Main] IMAP logged out")
        except Exception:
            pass


def _signal_handler(sig, frame):
    _cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def connect():
    """连接到IMAP服务器"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL, PASSWORD)
        mail.select("INBOX")
        stock_logger.debug("[Main] Connected to 163 IMAP server successfully")
        return mail
    except Exception as e:
        stock_logger.error("[Main] Connection failed: %s", str(e))
        return None


def decode_str(s):
    """解码邮件标题"""
    val, charset = decode_header(s)[0]
    if charset:
        val = val.decode(charset)
    return val


def run_worker_process():
    """
    启动独立子进程运行stockmail_kdj_worker，并实时监控输出与退出状态
    """
    global _current_worker
    stock_logger.debug("[Main] Starting new KDJ worker process...")

    # 启动子进程（捕获 stdout + stderr）
    process = subprocess.Popen(
        [sys.executable, WORKER_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )
    _current_worker = process

    stock_logger.debug(f"[Main] Worker process started, PID: {process.pid}")

    # 定义线程读取输出，避免阻塞
    def read_output(pipe, prefix):
        for line in iter(pipe.readline, ''):
            if line:
                stock_logger.debug(f"[{prefix}] {line.strip()}")
        pipe.close()

    # 启动线程读取标准输出
    stdout_thread = threading.Thread(target=read_output, args=(process.stdout, "Worker"), daemon=True)
    stderr_thread = threading.Thread(target=read_output, args=(process.stderr, "Worker-ERR"), daemon=True)

    stdout_thread.start()
    stderr_thread.start()

    # 等待进程结束
    exit_code = process.wait()

    # 等待输出线程结束
    stdout_thread.join(timeout=3)
    stderr_thread.join(timeout=3)

    _current_worker = None

    # 状态汇总
    if exit_code == 0:
        stock_logger.debug(f"[Main] Worker process (PID: {process.pid}) finished successfully")
    else:
        stock_logger.error("[Main] Worker process (PID: %d) failed with exit code: %d", process.pid, exit_code)


def run_task():
    """触发任务：启动子进程执行worker（异步不阻塞邮件监听）"""
    task_thread = threading.Thread(target=run_worker_process, daemon=True)
    task_thread.start()


def process_new_mail(mail, mail_id):
    """处理新邮件"""
    if mail_id in _processed_ids:
        stock_logger.debug(f"[Main] Mail {mail_id} already processed, skip")
        return
    try:
        status, data = mail.fetch(mail_id, "(RFC822)")
        _processed_ids.add(mail_id)
        msg = email.message_from_bytes(data[0][1])
        subject = decode_str(msg["Subject"])
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ("text/plain", "text/html"):
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                        if content_type == "text/plain":
                            break
                    except Exception:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
            except Exception:
                pass

        stock_logger.debug(f"[Main] New email arrived: {subject}")

        # 标题前缀检查 + 关键词检查
        if SUBJECT_PREFIX and not subject.startswith(SUBJECT_PREFIX):
            stock_logger.debug(f"[Main] Subject prefix mismatch, skip")
            return

        if TRIGGER_KEYWORD in subject or TRIGGER_KEYWORD in body:
            stock_logger.debug(f"[Main] Email body:\n{body}")
            stock_logger.debug("[Main] Trigger keyword detected, start task execution")
            run_task()
            try:
                mail.store(mail_id, '+FLAGS', '\\Seen')
                stock_logger.debug(f"[Main] Mail {mail_id} marked as read")
            except Exception as e:
                stock_logger.error("[Main] Failed to mark mail %s as read: %s", mail_id, e)
        else:
            stock_logger.debug("[Main] Trigger keyword not found in email")

    except Exception as e:
        stock_logger.error("[Main] Failed to process email: %s", str(e))


def idle_listen(mail):
    """IMAP IDLE 模式监听新邮件（兼容版）

    163.com 不支持 IDLE，发送原始 IDLE 命令会导致 IMAP 状态从 SELECTED 退回 AUTH，
    后续 SEARCH 命令都会失败。调用方必须在 idle_listen() 返回后重新 select INBOX。
    """
    try:
        mail.send(b"IDLE\r\n")
        resp = mail.readline()
        stock_logger.debug(f"[Main] IDLE start response: {resp.strip() if resp else 'None'}")
        if resp and (b"+" in resp or b"idling" in resp.lower()):
            return True
        stock_logger.debug(f"[Main] Unexpected IDLE response: {resp.strip() if resp else 'None'}")
        return False
    except Exception as e:
        stock_logger.debug(f"[Main] IDLE mode failed: {str(e)}")
        return False


def check_unread(mail):
    """检查未读邮件，同时检查最近5分钟的邮件（防止网页版自动标为已读）"""
    try:
        status, ids = mail.search(None, "UNSEEN")
        unread = ids[0].split()
        stock_logger.debug(f"[Main] UNSEEN search returned {len(unread)} email(s)")
        return unread
    except Exception as e:
        stock_logger.debug(f"[Main] UNSEEN search failed: {e}")
        return []


def check_recent(mail, minutes=10):
    """检查最近N分钟内的邮件（按时间搜索，不依赖已读/未读状态）"""
    try:
        since_time = datetime.now().strftime("%d-%b-%Y")
        status, ids = mail.search(None, f'(SINCE "{since_time}")')
        recent = ids[0].split()
        stock_logger.debug(f"[Main] SINCE search ({since_time}) returned {len(recent)} email(s)")
        return recent
    except Exception as e:
        stock_logger.debug(f"[Main] SINCE search failed: {e}")
        return []


def idle_loop():
    """主循环：持续监听邮件（修复IDLE逻辑）"""
    global _current_mail
    stock_logger.debug("[Main] Email monitor started (IDLE mode)")
    while True:
        mail = connect()
        if not mail:
            stock_logger.debug("[Main] Reconnect after 60s...")
            time.sleep(60)
            continue

        _current_mail = mail

        try:
            while True:
                # 第一步：检查未读邮件 + 最近邮件（防止网页版自动标为已读）
                unread = check_unread(mail)
                if unread:
                    stock_logger.debug(f"[Main] Found {len(unread)} unread emails")
                    for mid in unread:
                        process_new_mail(mail, mid)
                else:
                    # 未读为空时，额外检查最近10分钟的邮件
                    recent = check_recent(mail, minutes=10)
                    if recent:
                        stock_logger.debug(f"[Main] No unread but found {len(recent)} recent emails, checking...")
                        for mid in recent:
                            process_new_mail(mail, mid)
                    else:
                        stock_logger.debug("[Main] No unread or recent emails found")

                # 第二步：进入 IDLE 模式监听新邮件
                stock_logger.debug("[Main] Waiting for new emails (IDLE)...")
                if idle_listen(mail):
                    # 持续监听 IDLE 响应，直到超时或有新邮件
                    idle_start = time.time()
                    mail_fd = mail.socket().fileno()
                    try:
                        while time.time() - idle_start < IDLE_TIMEOUT:
                            read_list, _, _ = select.select([mail_fd], [], [], 5)
                            if read_list:
                                resp = mail.readline()
                                if resp:
                                    resp_lower = resp.lower()
                                    if b"exists" in resp_lower or b"recent" in resp_lower:
                                        stock_logger.debug(f"[Main] New email signal detected: {resp.strip()}")
                                        break
                        else:
                            # IDLE 超时
                            pass
                    finally:
                        # 退出 IDLE，确保发送 DONE
                        try:
                            mail.send(b"DONE\r\n")
                            mail.readline()
                        except Exception:
                            pass
                else:
                    # IDLE 启动失败，退化为轮询模式
                    stock_logger.debug(f"[Main] {datetime.now().strftime('%H:%M:%S')} IDLE unavailable, fallback to polling in 30s...")
                    time.sleep(30)

                # IDLE 的原始命令会破坏 IMAP 状态，重新 select INBOX
                try:
                    mail.select("INBOX")
                except Exception:
                    pass

        except Exception as e:
            stock_logger.error("[Main] Connection lost: %s", str(e))
            try:
                mail.logout()
            except:
                pass
            _current_mail = None
            stock_logger.debug("[Main] Reconnect after 30s...")
            time.sleep(30)


if __name__ == "__main__":
    idle_loop()