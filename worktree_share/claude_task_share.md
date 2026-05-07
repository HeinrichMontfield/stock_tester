支持股票涨跌幅监控 stock_signal_catcher

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
