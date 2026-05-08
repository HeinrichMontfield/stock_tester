# 支持股票涨跌幅监控 monitor_price_variant

# (1)函数接口 request_stock_15min_history 请求15分钟k线历史数据，并存储 csv 格式。
函数写入文件 @scripts/signal_catcher/testcase/stock_get_15min_history_data.py
## 输入：
股票代码：例如 600893
时间范围：输入参数 start_time, end_time，输入格式:yyyy-mm-dd

## 输出:
股票数据存储文件名：例如 600893_data.csv
股票信息额外存储文件名: 600893_info.json
额外存储文件信息中包含当前最新的 start_time, end_time。如果进行了多次拉取，那么对数据的时间范围进行合并。
数据存储目录:/data/signal_catcher/

## 函数内部逻辑:
根据输入的股票代码，先读取 <code>_info.json 文件，看之前获取的时间区间。
如果新的输入时间区间已在已获取的时间区间内，则直接打印日志然后返回。

如果更新的输入时间不在范围内那么，需要补全成连续区间。
例如，新的 end_time_new < 之前的 start_time_old，那么要获取新的 start_time_new 到原来的 start_time_old。
例如，新的 start_time_new > 之前的 end_time_old，那么要获取原来的 end_time_old 到新的 end_time_new。
将调整过后的 start_time_new 和 end_time_new 转换成 stock_zh_a_hist_min_em 能接受的 start_date 和 end_date 参数格式。
使用 akshare 获取15分钟级别k线数据
df = ak.stock_zh_a_hist_min_em(
    symbol=stock_code,
    period="15",
    adjust="qfq",
    start_date=start_date,
    end_date=datetime.now().strftime("%Y-%m-%d")
)

将获取到的数据存储为 csv 文件，并更新 <code>_info.json 文件中的时间区间。
可以参考样例代码 @scripts/code_sample.py

# (2) 函数接口 draw_stock_15min_history 调用 plotly 绘制 k 线图
函数写入文件 @scripts/signal_catcher/testcase/stock_draw_15min_history.py
## 输入：
股票代码：例如 600893
时间范围：输入参数 start_time, end_time，输入格式:yyyy-mm-dd
如果时间范围没有输入参数，那么默认绘制 csv 文件中全部时间范围的数据。

## 输出:
绘制 k 线图，并保存为 html 文件，文件名：<股票代码>_<start_time>_<end_time>_15min.html
文件存储目录:/data/temp/

## 函数内部逻辑
去 /data/signal_catcher/ 目录下查找对应股票代码的 csv 文件，并读取数据。
取数据在输入的时间范围内。
使用 plotly 绘制 k 线图，并保存为 html 文件。

# （3）文件 monitor_stock_price_variant.py 运行后监控股票15分钟价格和当天开盘价的变化，当变化超过阈值时发邮件通知
函数写入文件 @scripts/signal_catcher/stock_monitor_price_variant.py
## 文件内部各个函数功能描述：

### request_stock_15min_data
调用 request_stock_15min_data 接口获取最新的股票价格信息。
在 stock_monitor_price_variant.py 中增加一个变量 IS_SIMULATE_MODE，当它=true时，request_stock_15min_data 使用历史数据。
并且 IS_SIMULATE_MODE = true 时，request_stock_15min_data 会额外输入 timestamp 参数，以获取 <= timestamp 的最近一个历史数据，以及它的数据本身的 timestamp。
当 IS_SIMULATE_MODE=false时，request_stock_15min_data 使用 stock_zh_a_hist_min_em 访问网络实时数据，返回数据结构体以及数据的 timestamp。

request_stock_15min_data 读取历史数据时，使用 @scripts/signal_catcher/testcase/stock_get_15min_history_data.py 存储在 /data/signal_catcher/ 的 csv 数据。
如果指定的 START_SIMULATION_TIMESTAMP 不在 /data/signal_catcher 中对应股票 info 文件有记录的时间范围时，直接返回空数据接口和一个 timestamp=None。

### run_stock_monitor_price_variant
调用 run_stock_monitor_price_variant 函数开启监控。
run_stock_monitor_price_variant 每 10 分钟调用一次 request_stock_15min_data 函数获取最新的股票价格信息。
当处于 IS_SIMULATE_MODE=true 时，run_stock_monitor_price_variant 会直接以 20 倍速（每隔0.5分钟）调用 request_stock_15min_data 函数获取历史数据。
此时，从读取变量 START_SIMULATION_TIMESTAMP 开始，每次（每隔0.5分钟）输入一个间隔 10 分钟的 timestamp 给request_stock_15min_data 获取历史数据。
当经过一段模拟后，发给 request_stock_15min_data 的 timestamp 会超过数据存储的时间范围，此时 request_stock_15min_data 会返回 timestamp = None，那么就终止模拟并打印日志。

### save_15min_data_to_mongo
当 IS_SIMULATE_MODE=false 时，则按照系统时间每隔 10分钟，调用一次 request_stock_15min_data 函数获取实时数据，如果实时数据的 timestamp 已经存储，那么就不再存储。
如果实时数据的 timestamp 尚未存储，那么就调用 save_15min_data_to_mongo 写入 mongo 数据库。
mongo 数据库新建库和collection，使用 @.env 中 STOCK_DB_15MIN_NAME，STOCK_KLINE_15MIN_COLLECTION。
mongo地址继续使用 @.env 中 MONGO_URI。

### main 函数
调用 run_stock_monitor_price_variant 函数开启监控。