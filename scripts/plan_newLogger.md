# Plan: Replace all `print()` with `stock_logger.stock_logger.debug()` in scripts (excluding akshare)

## Files to modify

| # | File | Prints | Notes |
|---|------|--------|-------|
| 1 | `scripts/utils/stock_custom_utils.py` | 3 | `print(f"...")` style |
| 2 | `scripts/database_ops/db_requestdata.py` | 7 | `print(f"...")` style |
| 3 | `scripts/database_ops/stock_request_data.py` | 4 | `print("...")` + `print(variable)` |
| 4 | `scripts/database_ops/stock_debugmongo.py` | 26 | `print("...")` + `print(variable)` |
| 5 | `scripts/draw/stockdraw_basegraph.py` | 8 | mixed styles |
| 6 | `scripts/draw/stockdraw_kdj1.py` | 15 | some with `file=sys.stderr` |
| 7 | `scripts/mail/mail_utils.py` | 10 | `print(f"...")` style |
| 8 | `scripts/mail/stockmail_kdj_worker.py` | N/A | Uses `_log()`/`_log_err()` helpers; replace those internals |
| 9 | `scripts/mail/stockmail_central.py` | 57 | `print(f"...")` style |
| 10 | `scripts/news_monitor/news_mail.py` | 5 | `print(f"...")` style |
| 11 | `scripts/news_monitor/news_fetcher.py` | 3 | `print(f"...")` style |
| 12 | `scripts/news_monitor/news_monitor.py` | 16 | `print(f"...")` style |
| 13 | `scripts/news_monitor/news_query.py` | 3 | `print(f"...")` style |
| 14 | `scripts/news_monitor/news_store.py` | 17 | `print(f"...")` style |
| **Total** | | **~178** | |

## Implementation steps

### Step 1: Add `LOG_FOLDER` to `.env`
Add `LOG_FOLDER=/Users/mac/virtualenvs/venv_baostock/log` to `.env`.

### Step 2: Create `scripts/utils/stock_logger.py`
- Reads `LOG_FOLDER` from env via `dotenv` + `os.getenv`
- Creates the log directory if it doesn't exist
- Uses Python `logging` module underneath with daily rotating files
- Exposes:
  - `stock_logger.debug(fmt, *args)` — printf-style `%s` formatting, delegates to `logging.debug`
  - `stock_logger.error(fmt, *args)` — for stderr equivalents, delegates to `logging.error`
- Log format: `[YYYY-MM-DD HH:MM:SS][LEVEL] message`
- Log file: `LOG_FOLDER/stock_{YYYY-MM-DD}.log`
- Also outputs to stdout for backward compatibility during transition

### Step 3: Replace prints in each file

Replace rules:
- `print(f"...{var}...")` → `stock_logger.stock_logger.debug("...%s...", var)`
- `print("...")` → `stock_logger.stock_logger.debug("...")`
- `print(var)` → `stock_logger.stock_logger.debug("%s", var)`
- `print(..., file=sys.stderr)` → `stock_logger.stock_logger.error("...")`
- `_log(msg)` → `stock_logger.stock_logger.debug("%s", msg)`
- `_log_err(msg)` → `stock_logger.stock_logger.error("%s", msg)`

Order: Start from leaf dependencies (utils → database_ops → draw → news_monitor → mail).
