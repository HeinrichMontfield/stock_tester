import os
import sys
import subprocess
import zipfile
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def _log(msg):
    """Print message to stdout and flush immediately to ensure correct log ordering."""
    print(msg)
    sys.stdout.flush()


def _log_err(msg):
    """Print error message to stderr and flush immediately."""
    print(msg, file=sys.stderr)
    sys.stderr.flush()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve_path(path):
    if path and not os.path.isabs(path):
        return os.path.join(PROJECT_ROOT, path)
    return path


KDJ_SCRIPT_PATH = _resolve_path(os.getenv("KDJ_SCRIPT_PATH"))
HTML_OUTPUT_FOLDER = _resolve_path(os.getenv("HTML_OUTPUT_FOLDER"))
ZIP_FILE_NAME = os.getenv("ZIP_FILE_NAME", "kdj_result.zip")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT")


def execute_kdj_script(timestamp):
    """Execute KDJ script with timestamp as output_folder argument.

    Passes the already-resolved HTML_OUTPUT_FOLDER as an env var so the
    KDJ script uses the same absolute path instead of re-resolving it.
    """
    _log("[Worker] Task started: executing KDJ script")
    if not os.path.exists(KDJ_SCRIPT_PATH):
        raise Exception(f"KDJ script not found at path: {KDJ_SCRIPT_PATH}")

    try:
        env = os.environ.copy()
        env["HTML_OUTPUT_FOLDER"] = HTML_OUTPUT_FOLDER
        result = subprocess.run(
            [sys.executable, KDJ_SCRIPT_PATH, timestamp],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=PROJECT_ROOT,
            env=env,
        )
    except FileNotFoundError:
        raise Exception(f"Python interpreter not found: {sys.executable}")
    except Exception as e:
        raise Exception(f"Failed to launch KDJ script subprocess: {str(e)}")

    if result.stdout:
        _log(f"[Worker] KDJ script stdout: {result.stdout.strip()}")

    if result.returncode != 0:
        stderr_msg = result.stderr.strip() if result.stderr else "no stderr output"
        raise Exception(f"KDJ script exited with code {result.returncode}: {stderr_msg}")

    _log("[Worker] KDJ script executed successfully")
    return True


def zip_html_files(timestamp):
    """Compress HTML files from the timestamped subfolder, save zip to parent folder."""
    _log("[Worker] Starting to compress HTML files")
    source_folder = os.path.join(HTML_OUTPUT_FOLDER, timestamp)

    if not os.path.exists(HTML_OUTPUT_FOLDER):
        raise Exception(
            f"HTML output parent folder not found: {HTML_OUTPUT_FOLDER}. "
            "Check HTML_OUTPUT_FOLDER in .env."
        )

    if not os.path.exists(source_folder):
        parent_contents = os.listdir(HTML_OUTPUT_FOLDER) if os.path.exists(HTML_OUTPUT_FOLDER) else []
        raise Exception(
            f"HTML output subfolder not found: {source_folder}. "
            f"Parent folder contents: {parent_contents}. "
            "The KDJ script may not have generated output for this timestamp."
        )

    zip_path = os.path.join(HTML_OUTPUT_FOLDER, ZIP_FILE_NAME)

    html_files = [f for f in os.listdir(source_folder) if f.lower().endswith(".html")]
    if not html_files:
        all_files = os.listdir(source_folder)
        raise Exception(f"No HTML files found in {source_folder}. Files present: {all_files}")

    _log(f"[Worker] Found {len(html_files)} HTML file(s) to compress")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in html_files:
                file_path = os.path.join(source_folder, filename)
                try:
                    zf.write(file_path, filename)
                    _log(f"[Worker] Added to zip: {filename}")
                except Exception as e:
                    raise Exception(f"Failed to add file to zip: {filename}: {str(e)}")
    except PermissionError:
        raise Exception(f"Permission denied when creating zip file: {zip_path}")
    except OSError as e:
        raise Exception(f"Failed to create zip file {zip_path}: {str(e)}")

    zip_size = os.path.getsize(zip_path)
    _log(f"[Worker] HTML files compressed to: {zip_path} ({zip_size} bytes)")
    return zip_path


def send_result_email(zip_path):
    """Send result email with zip attachment."""
    _log("[Worker] Starting to send result email")
    if not os.path.exists(zip_path):
        raise Exception(f"Zip file not found: {zip_path}")

    try:
        with open(zip_path, "rb") as f:
            part = MIMEBase("application", "zip")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(zip_path)}")
    except Exception as e:
        raise Exception(f"Failed to prepare email attachment from {zip_path}: {str(e)}")

    msg = MIMEMultipart()
    msg["From"] = EMAIL
    msg["To"] = EMAIL
    msg["Subject"] = f"KDJ Result {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    msg.attach(part)

    server = None
    _log(f"[Worker] Connecting to SMTP server {SMTP_SERVER}:{SMTP_PORT}...")
    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
        _log(f"[Worker] SMTP SSL connection established to {SMTP_SERVER}:{SMTP_PORT}")
    except Exception as e:
        raise Exception(f"Failed to connect to SMTP server {SMTP_SERVER}:{SMTP_PORT}: {type(e).__name__}: {str(e)}")

    try:
        _log(f"[Worker] Logging in to SMTP server as {EMAIL}...")
        server.login(EMAIL, PASSWORD)
        _log("[Worker] SMTP login successful")
    except smtplib.SMTPAuthenticationError as e:
        raise Exception(f"SMTP login failed for {EMAIL}: authentication error ({type(e).__name__}: {str(e)}). Check EMAIL/PASSWORD in .env.")
    except smtplib.SMTPException as e:
        raise Exception(f"SMTP login failed for {EMAIL}: {type(e).__name__}: {str(e)}")
    except Exception as e:
        raise Exception(f"SMTP login failed for {EMAIL}: unexpected {type(e).__name__}: {str(e)}")

    try:
        msg_str = msg.as_string()
        _log(f"[Worker] Sending email, message size: {len(msg_str)} bytes...")
        server.sendmail(EMAIL, EMAIL, msg_str)
        _log("[Worker] SMTP sendmail accepted")
    except smtplib.SMTPException as e:
        raise Exception(f"Failed to send email to {EMAIL}: {type(e).__name__}: {str(e)}")
    except Exception as e:
        raise Exception(f"Failed to send email to {EMAIL}: unexpected {type(e).__name__}: {str(e)}")
    finally:
        if server:
            try:
                server.quit()
                _log("[Worker] SMTP connection closed")
            except Exception as e:
                _log(f"[Worker] Error closing SMTP connection: {type(e).__name__}: {str(e)}")

    _log("[Worker] Result email sent successfully")
    return True


def main():
    """Task main flow: execute → zip → email → cleanup."""
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    zip_path = None
    try:
        execute_kdj_script(timestamp)
        zip_path = zip_html_files(timestamp)
        send_result_email(zip_path)
        os.remove(zip_path)
        _log(f"[Worker] Removed zip file: {zip_path}")
        _log("[Worker] All tasks completed successfully")
        return 0
    except Exception as e:
        _log_err(f"[Worker-ERR] Task failed at step, error: {str(e)}")
        if zip_path and os.path.exists(zip_path):
            try:
                os.remove(zip_path)
                _log(f"[Worker] Removed zip file after failure: {zip_path}")
            except Exception as rm_err:
                _log_err(f"[Worker-ERR] Failed to remove zip file {zip_path}: {str(rm_err)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
