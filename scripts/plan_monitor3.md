# plan_monitor3.md — stock_monitor_price_variant.py 执行计划

## 1. 文件位置
新建文件：`scripts/signal_catcher/stock_monitor_price_variant.py`

## 2. 全局变量与配置

### 2.1 从 `.env` 读取的配置

以下变量需在 `.env` 中新增或已存在：

| 变量名 | 用途 | 示例值 |
|--------|------|--------|
| `MONITOR_STOCK_CODES` | 监控股票列表，逗号分隔 | `600893,000001` |
| `PRICE_VARIANT_THRESHOLD` | 首次告警阈值（%），触发 ±5% 阶梯告警的起点 | `3.0` |
| `MARKET_HOURS_START` | 早市开盘时间 | `09:00` |
| `MARKET_HOURS_MID_START` | 中午休市开始 | `11:30` |
| `MARKET_HOURS_MID_END` | 午市开盘时间 | `13:00` |
| `MARKET_HOURS_END` | 收盘时间 | `15:00` |
| `MONGO_URI` | MongoDB 连接地址 | `mongodb://localhost:27017/` |
| `STOCK_DB_15MIN_NAME` | 15分钟K线数据库名 | `stock_db_15min` |
| `STOCK_KLINE_15MIN_COLLECTION` | 15分钟K线集合名 | `stock_kline_15min` |

其中 `MARKET_HOURS_MID_START`、`MARKET_HOURS_MID_END`、`PRICE_VARIANT_THRESHOLD` 需新增到 `.env`。

### 2.2 硬编码在 py 文件中的变量

```python
# 模拟模式开关
IS_SIMULATE_MODE = True

# 模拟模式起始时间戳
START_SIMULATION_TIMESTAMP = "2026-01-02 09:30:00"

# 定时任务间隔（分钟）
MONITOR_INTERVAL_MINUTES = 10

# 模拟模式加速倍率
SIMULATE_SPEED_MULTIPLIER = 20

# 接收通知的邮箱
使用 os.getenv 读取 @.env 中的 EMAIL
```

### 2.3 告警阶梯档位常量（硬编码 or 写入 `stock_common_consts.py`）

```python
# 下跌阶梯档位
DOWN_ALERT_LEVELS = [-5, -7, -9]
# 上涨阶梯档位
UP_ALERT_LEVELS = [5, 7, 9]
# 涨跌停极限
LIMIT_DOWN_PCT = -10
LIMIT_UP_PCT = 10
```

### 2.4 `stock_common_consts.py` 中新增

```python
# 休市节假日期列表，格式: "yyyy-mm-dd"
A_STOCK_HOLIDAYS = [
    "2026-01-01",  # 元旦
    # ... 需手动维护
]
```

## 3. 函数设计

### 3.1 `_get_project_root()`
复用已有模式，向上4级目录找到项目根目录。

### 3.2 `request_stock_15min_data(stock_code, timestamp=None) -> dict | None`
**核心数据获取接口。**

- **IS_SIMULATE_MODE = True 时：**
  1. 读取 `/data/signal_catcher/<stock_code>_info.json`，获取已有数据的 time range。
  2. 如果 `timestamp` 不在数据覆盖的时间范围内 → 打印日志，返回 `None`。
  3. 读取 `/data/signal_catcher/<stock_code>_data.csv`。
  4. 取 `datetime <= timestamp` 的最近一条记录（按 datetime 降序取第一条）。
  5. 返回 dict 结构：
     ```python
     {
         "stock_code": "600893",
         "datetime": <数据中的datetime>,
         "open": ...,
         "high": ...,
         "low": ...,
         "close": ...,
         "volume": ...,
         "timestamp": <该条数据的实际时间戳 (datetime)>,
     }
     ```

- **IS_SIMULATE_MODE = False 时：**
  1. 调用 `ak.stock_zh_a_hist_min_em(symbol=stock_code, period="15", adjust="qfq", start_date=today, end_date=today)` 获取当天实时数据。
  2. 取最新一条记录。
  3. 返回同样结构的 dict，其中 `timestamp` 为数据本身的 datetime。
  4. 如果无数据则返回 `None`。

**日志要求**：
- debug: 模拟模式开始查询时输出 stock_code 和 `timestamp` 参数值
- debug: 实时模式请求 akshare 时输出 stock_code 和查询日期
- debug: 模拟模式下 timestamp 不在数据时间范围内时，输出 info 中记录的范围和请求的 timestamp
- debug: 成功获取数据时，输出 stock_code 和数据条数、最新数据时间
- error: 读取 CSV / info.json 失败时，输出文件路径和异常信息
- error: akshare 请求失败时，输出 stock_code 和异常信息

### 3.3 `save_15min_data_to_mongo(data_dict) -> bool`
1. 连接 MongoDB (`MONGO_URI`)。
2. 使用 db `STOCK_DB_15MIN_NAME`，collection `STOCK_KLINE_15MIN_COLLECTION`。
3. 以 `stock_code` + `datetime` 作为唯一键（upsert），避免重复存储。
4. 写入 data_dict 中的全部字段。
5. 返回 True/False。

**日志要求**：
- debug: 存储成功时输出 stock_code 和 datetime
- debug: 重复数据跳过时（upsert matched existing），输出 stock_code 和 datetime
- error: MongoDB 连接或写入失败时，输出异常信息

### 3.4 `_get_today_open(stock_code, data_dict) -> float | None`
获取当日开盘价。

- **IS_SIMULATE_MODE = True**：从 `/data/signal_catcher/<stock_code>_data.csv` 中取当天第一条数据的 `open`。
- **IS_SIMULATE_MODE = False**：
  1. 先查 MongoDB（`STOCK_DB_15MIN_NAME` / `STOCK_KLINE_15MIN_COLLECTION`）中该股票当天的第一条记录，取 `open`。
  2. 如果 MongoDB 中没有，调用 `ak.stock_zh_a_hist_min_em` 取当天第一条15min数据的 `open`。
- 返回 `today_open`，若获取不到则返回 `None`。

**日志要求**：
- debug: 输出获取到的 `today_open` 值和数据来源（CSV / MongoDB / akshare）
- error: 从 CSV / MongoDB / akshare 获取失败时，输出 stock_code 和异常信息
- debug: 获取不到任何当日数据时（返回 None），输出 stock_code 和当天日期

### 3.5 `check_price_variant(data_dict, today_open) -> float | None`
计算涨跌幅百分比。
1. 从 data_dict 中取 `close`。
2. `variant_pct = (close - today_open) / today_open * 100`。
3. 返回 `variant_pct`。如果 `today_open` 为 None 则返回 `None`。

**日志要求**：
- debug: 输出 stock_code、close、today_open、计算得到的 variant_pct（保留2位小数）

### 3.6 `evaluate_alert(stock_code, variant_pct, alert_state, today_open) -> tuple[str | None, dict]`
根据阶梯告警规则判断是否需要发送邮件，返回 `(alert_reason, updated_alert_state)`。

逻辑按照"待补充确认第6条"的阶梯告警规则和超5%标记回归规则实现，关键点：
1. 计算当前所处的阶梯档位。
2. 与 `alert_state["last_alerted_level"]` 比较，决定是否发送。
3. 管理 `alert_state["over_5pct_flag"]` 的标记/清除/回归通知。
4. 涨跌停极限（±10%）不再发送。
5. `alert_reason` 为 None 时不发邮件，否则包含告警原因文本。

**日志要求**：
- debug: 触发告警时，输出 stock_code、variant_pct、current_level、alert_reason
- debug: 抑制告警时（档位已告警过），输出 stock_code、variant_pct、last_alerted_level 和抑制原因
- debug: 超5%标记（over_5pct_flag）状态变更时，输出 stock_code、旧状态、新状态
- debug: 回归通知触发时，输出 stock_code、variant_pct 和 today_open
- debug: 触及涨跌停极限不再发送时，输出 stock_code 和 variant_pct
- debug: 收盘重置 alert_states 时，输出被重置的股票数量

### 3.7 `send_alert_email(stock_code, alert_reason, variant_pct, data_dict, today_open) -> bool`
1. 构造邮件标题：`[Stock Alert] {stock_code} price variant {variant_pct:+.2f}%`
2. 构造邮件正文：包含股票代码、当前价格、开盘价、涨跌幅、告警原因（alert_reason）、时间等信息。
3. 调用 `scripts/mail/mail_utils.py` 的 `send_email()` 发送。

**日志要求**：
- debug: 发送邮件前输出 stock_code、alert_reason、variant_pct、收件人
- error: 邮件发送失败时，输出 stock_code 和异常信息

### 3.8 `_is_trading_time(ts: datetime) -> bool`
判断给定时间是否处于交易时段内。
1. 检查 `ts.strftime("%Y-%m-%d")` 是否在 `A_STOCK_HOLIDAYS` 中 → 返回 False。
2. 检查星期几（`ts.weekday()`），周六(5)、周日(6) → 返回 False。
3. 检查时间是否在 `MARKET_HOURS_START` ~ `MARKET_HOURS_MID_START` 或 `MARKET_HOURS_MID_END` ~ `MARKET_HOURS_END` 之间 → 返回 True，否则 False。

**日志要求**：
无（纯判断函数，仅返回布尔值，日志由调用方输出）。

### 3.9 `_get_next_trading_timestamp(ts: datetime) -> datetime`
用于模拟模式跳过非交易时段。
1. 从 `ts` 开始递增，每次 +10 分钟（`MONITOR_INTERVAL_MINUTES`）。
2. 找到下一个 `_is_trading_time()` 返回 True 的时间点。
3. 返回该时间点。

**日志要求**：
- debug: 跳过非交易时段时，输出跳过的起始时间和跳至的目标时间
- debug: 跨自然日时（包括周末、节假日），输出跨过的日期范围

### 3.10 `_should_monitor_run() -> bool`
用于实时模式判断当前是否在交易时间。
- 调用 `_is_trading_time(datetime.now())`。
- 不在交易时间时 `time.sleep(60)` 后重新检查，不调用 `request_stock_15min_data`。

**日志要求**：
- debug: 进入非交易时段等待时，输出当前时间和下一次开市时间（仅在首次进入等待时输出，避免刷屏）

### 3.11 `run_stock_monitor_price_variant()`
**监控主循环。**

公共逻辑：
- 维护 `alert_states: dict[str, dict]`，key 为 stock_code，value 为 alert_state（见第6条的结构）。
- 每轮循环对每个 `MONITOR_STOCK_CODES` 调用数据获取和告警评估。
- 收盘时（超过 `MARKET_HOURS_END`）调用 `_reset_alert_states()` 清除所有股票的 alert_state。

- **IS_SIMULATE_MODE = True 时：**
  1. 设置 `current_timestamp = datetime.strptime(START_SIMULATION_TIMESTAMP, "%Y-%m-%d %H:%M:%S")`。
  2. 如果当前时间点不是交易时间，调用 `_get_next_trading_timestamp` 跳过休市时段。
  3. 进入循环：
     - 对每个 stock 调用 `request_stock_15min_data(stock, current_timestamp)`。
     - 如果某个 stock 返回 `None`（时间戳超出数据范围），标记该 stock 为已结束。
     - 所有 stock 都已结束 → 打印日志，退出循环。
     - 数据有效 → `_get_today_open()` → `check_price_variant()` → `evaluate_alert()`。
     - 如果 `alert_reason` 不为 None → `send_alert_email()`。
     - `current_timestamp += timedelta(minutes=10)`，并通过 `_get_next_trading_timestamp` 跳过休市。
     - `time.sleep(30)`。

- **IS_SIMULATE_MODE = False 时：**
  1. 进入无限循环：
     - `_should_monitor_run()` — 非交易时间则 sleep 后 continue。
     - 对每个 stock 调用 `request_stock_15min_data(stock)`。
     - 数据有效 → `save_15min_data_to_mongo()` → `_get_today_open()` → `check_price_variant()` → `evaluate_alert()`。
     - `alert_reason` 不为 None → `send_alert_email()`。
     - `time.sleep(MONITOR_INTERVAL_MINUTES * 60)`。

**日志要求**（监控主循环级别）：
- debug: 监控启动时输出模式（SIMULATE / REAL）、监控股票列表、配置参数摘要（间隔、阈值、阶梯档位）
- debug: 模拟模式下每 20 轮（即模拟约 10 分钟间隔）输出一次当前进度：current_timestamp、已处理轮次、各 stock 数据状态
- debug: 模拟模式下某 stock 因数据超范围结束时，输出 stock_code 和最后成功的 timestamp
- debug: 模拟模式所有 stock 结束退出时，输出总轮次和模拟持续时间
- info: 实时模式在开盘时输出 `Market open, monitoring started`；收盘时输出 `Market closed, monitoring paused`
- error: 主循环内未预期的异常，输出 traceback 和当前上下文（stock_code、timestamp、模式），不中断循环

### 3.12 `main()`
直接调用 `run_stock_monitor_price_variant()`。

**日志要求**：
- debug: 程序启动时输出 `=== Stock Price Variant Monitor Started ===`
- debug: 程序退出时输出 `=== Stock Price Variant Monitor Stopped ===`

## 4. 依赖

```python
import akshare as ak
import pandas as pd
import json
import os
import time
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
from scripts.utils import stock_logger
from scripts.utils.stock_common_consts import (
    A_STOCK_HOLIDAYS,
    LIMIT_DOWN_PCT,
    LIMIT_UP_PCT,
)
from scripts.mail.mail_utils import send_email
```

## 5. 文件结构示意

```
scripts/signal_catcher/
├── stock_signal_catcher.py          # 已有
├── stock_monitor_price_variant.py   # 新建
└── testcase/
    ├── stock_get_15min_history_data.py  # 已有
    └── stock_draw_15min_history.py      # 已有
```

---

## 待补充确认的信息

1. **涨跌幅对比基准是什么？** 需求说的是"当天开盘价"，但15分钟K线的开盘价是每个15分钟周期的开盘价，并非当日开盘价。获取当日开盘价的方式：是从CSV中取当天第一条数据，还是调用 `ak.stock_zh_a_hist_min_em` 取日K，还是从 stock_zh_a_hist_min_em 当天第一条15min数据的 open？
A: 在 IS_SIMULATE_MODE = true 时从CSV中取当天第一条数据。
IS_SIMULATE_MODE = false 时，用 stock_zh_a_hist_min_em 当天第一条15min数据的 open，可以先查一下有没有已经存入 mongo 了。

2. **监控哪些股票？** `MONITOR_STOCK_CODES` 是一个固定列表，还是从配置文件/数据库读取？目前计划用硬编码列表。
A: 使用硬编码在 @.env 中的一个变量。

3. **阈值是多少？** `PRICE_VARIANT_THRESHOLD` 的具体百分比值需要你指定，目前暂定 3%。
A: 使用硬编码在 @.env 中的一个变量。

4. **模拟模式的时间戳起始值** `START_SIMULATION_TIMESTAMP` 从哪里来？是硬编码、环境变量还是命令行参数？
A: 使用硬编码在 stock_monitor_price_variant.py 中的一个变量。

5. **实时模式下是否需要处理非交易时段？** 比如周末、节假日、盘前盘后是否跳过循环等待？
A:
@.env 中有每天开市时间 MARKET_HOURS_START，以及中午休市 MARKET_HOURS_MID_START，中午重新开市时间 MARKET_HOURS_MID_END，休市时间 MARKET_HOURS_END 。
@scripts/utils/stock_common_consts.py 中有 A_STOCK_HOLIDAYS 存储所有休市节假日期。
到这些时候如果时 IS_SIMULATE_MODE = false，则保持 run_stock_monitor_price_variant 的运行，但是不要 request_stock_15min_data，等待休市结束再开始。
如果 IS_SIMULATE_MODE = true，则直接跳过这些时间，从数据库找到下一个可用的 timestamp，更新新的 timestamp，然后从 csv 读取新的时间的数据。

6. **邮件通知频率控制？** 是否需要加去重逻辑（如同一股票同一方向涨跌幅短时间内不重复发邮件）？
A: 需要。每只股票维护一个告警状态结构，记录已告警的档位和方向标记，避免边界振荡导致高频触发。

**涨跌停阈值常量**（写入 `@scripts/utils/stock_common_consts.py`）：
```python
LIMIT_DOWN_PCT = -10   # 跌停阈值
LIMIT_UP_PCT = 10      # 涨停阈值
```

**每只股票维护的告警状态**（内存 dict，非持久化）：
```python
alert_state = {
    "last_alerted_level": None,   # 已告警的最高阶梯档位，如 -5, -7, -9, +5, +7, +9
    "over_5pct_flag": None,       # "down" 或 "up"，表示当前是否处于超5%状态
}
```

**阶梯告警规则（防振荡）**：

下跌方向阶梯档位：-5%, -7%, -9%。上涨方向阶梯档位：+5%, +7%, +9%。

每次检查时，计算当前 variant_pct，确定当前所处的最高阶梯档位：
- 选择原则：取 variant_pct 超出且未超过下一档的当前最高档。例如 variant_pct = -6.3%，当前档位为 -5%。variant_pct = -7.8%，当前档位为 -7%。
- 如果当前档位 == `last_alerted_level` → 不发邮件（已告警过该档位）。
- 如果当前档位 "超过" `last_alerted_level`（例如 last=-5，当前=-7） → 发邮件，更新 `last_alerted_level` 为当前档位。
- 如果当前档位 "回退" 到更低的档位（例如 last=-7，当前=-5） → 不发邮件，但也不清除 `last_alerted_level`。只有回到 ±5% 以内时（|variant_pct| < 5），才清零 `last_alerted_level = None`，重置阶梯告警状态，为下一轮穿越做准备。

这样股价在 -7% 附近反复振荡（-6.8% ↔ -7.2%）时，只在首次穿越 -7% 时发送一次。只有回退到 -5% 以内清零后再重新穿越，或继续跌到 -9%，才会再次发送。

**超5%标记与回归告警规则（防振荡）**：

- 当 variant_pct 首次下跌超过 -5%（即 variant_pct <= -5% 且 `over_5pct_flag` 为 None）：
  发送告警，设置 `over_5pct_flag = "down"`，`last_alerted_level = -5`。
- 当 `over_5pct_flag == "down"` 且当日现价回到接近开盘价 1% 以内（现价/开盘价 > 0.99）：
  发送回归通知，清除 `over_5pct_flag = None`，清零 `last_alerted_level = None`。
- 当 variant_pct 首次上涨超过 +5%（即 variant_pct >= 5% 且 `over_5pct_flag` 为 None）：
  发送告警，设置 `over_5pct_flag = "up"`，`last_alerted_level = +5`。
- 当 `over_5pct_flag == "up"` 且当日现价回到接近开盘价 1% 以内（现价/开盘价 < 1.01）：
  发送回归通知，清除 `over_5pct_flag = None`，清零 `last_alerted_level = None`。
- `over_5pct_flag` 被清除后，当天不会再就同一方向触发"首次超过5%"的告警，除非股价再次穿越 ±5% 边界（此时 flag 为 None，会重新触发）。

**每日收盘重置**：
收盘时（或下一交易日开盘前），清空所有股票的 `alert_state`（`last_alerted_level = None`, `over_5pct_flag = None`）。

