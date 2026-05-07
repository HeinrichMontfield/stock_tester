import akshare as ak
import pandas as pd
from datetime import datetime

def save_stock_15min_history(stock_code, start_date):
    """
    Fetch and save 15-minute historical K-line data for backtesting
    Save data to CSV file
    """
    print(f"Start fetching 15-minute historical data for stock {stock_code}")

    # Fetch 15-minute K-line data
    try:
        df = ak.stock_zh_a_hist_min_em(
            symbol=stock_code,
            period="15",
            adjust="qfq",
            start_date=start_date,
            end_date=datetime.now().strftime("%Y-%m-%d")
        )
    except Exception as e:
        print(f"Fetch data failed: {str(e)}")
        return None

    if df.empty:
        print("No data received from data source")
        return None

    print(f"Data fetch completed, total records: {len(df)}")

    # Format data for backtesting
    df_output = df[["时间", "开盘", "最高", "最低", "收盘", "成交量"]].copy()
    df_output.columns = ["datetime", "open", "high", "low", "close", "volume"]

    # Save to CSV file
    file_name = f"{stock_code}_15min_history.csv"
    df_output.to_csv(file_name, index=False, encoding="utf-8-sig")

    print(f"Data saved to file: {file_name}")
    return file_name

def load_history_data(file_path):
    """
    Load historical data from CSV for backtesting test cases
    """
    print(f"Start loading data from file: {file_path}")
    try:
        df = pd.read_csv(file_path)
        df["datetime"] = pd.to_datetime(df["datetime"])
        print(f"Data load successful, total records: {len(df)}")
        return df
    except Exception as e:
        print(f"Load data failed: {str(e)}")
        return None

if __name__ == "__main__":
    # Configuration
    STOCK_CODE = "000001"
    START_DATE = "2025-01-01"

    print("=== Historical Data Fetch Service Started ===")

    # Fetch and save data
    csv_file = save_stock_15min_history(STOCK_CODE, START_DATE)

    # Load data for backtesting
    if csv_file:
        test_data = load_history_data(csv_file)
        print("Data is ready for backtesting test cases")
        print("First 5 records preview:")
        print(test_data.head())
    else:
        print("Data preparation failed, service exit")

    print("=== Historical Data Fetch Service Finished ===")