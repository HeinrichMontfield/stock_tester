import akshare as ak
import time
from datetime import datetime

def get_15min_quote(stock_code):
    """
    用 stock_zh_a_hist_min_em 获取最新15分钟K线：开盘、最新价、涨跌幅
    :param stock_code: 6位股票代码（如 "000001"）
    :return: dict{open, last, change_pct} 或 None
    """
    try:
        # 获取最新15分钟K线（东方财富，不复权，取最新1根）
        df = ak.stock_zh_a_hist_min_em(
            symbol=stock_code,
            period="15",  # 15分钟周期
            adjust="",    # 不复权
            start_date="",
            end_date=""
        )
        if df.empty:
            return None
        
        # 取最新一根15分钟K线
        latest = df.iloc[-1]
        open_price = float(latest["开盘"])
        last_price = float(latest["收盘"])  # 15分钟K线收盘=当前最新价
        change_pct = round((last_price - open_price) / open_price * 100, 2)
        
        return {
            "open": round(open_price, 2),
            "last": round(last_price, 2),
            "change_pct": change_pct
        }
    except Exception as e:
        print(f"获取15分钟K线失败: {e}")
        return None

if __name__ == "__main__":
    TARGET_STOCK = "000001"  # 替换为你的6位股票代码
    REFRESH_INTERVAL = 15 * 60  # 15分钟刷新一次（900秒）
    
    print(f"========== 监控 {TARGET_STOCK} | 15分钟K线 | 每15分钟刷新 ==========\n")
    
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        quote = get_15min_quote(TARGET_STOCK)
        
        if quote:
            print(f"【{now}】")
            print(f"15分钟K线开盘: {quote['open']} | 最新价: {quote['last']} | 涨跌幅: {quote['change_pct']}%\n")
        else:
            print(f"【{now}】 无数据（非交易时间/代码错误/限流）\n")
        
        time.sleep(REFRESH_INTERVAL)