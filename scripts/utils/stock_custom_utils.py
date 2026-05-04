# -*- coding: utf-8 -*-

import baostock as bs
import pandas as pd
from scripts.utils.stock_common_consts import DATA_ANALYZED_FILEPATH
import os

def get_stock_basic_info(code):
    """
    查询股票基本信息

    Parameters:
    -----------
    code : str
        股票代码，格式如 'sz.002050'

    Returns:
    --------
    pd.DataFrame
        包含股票基本信息的DataFrame
    """
    basic_info = bs.query_stock_basic(code=code)
    if basic_info.error_code != '0':
        print(f"Query failed! Error code: {basic_info.error_code}, Error message: {basic_info.error_msg}")
        return pd.DataFrame()
    return basic_info.get_data()


def get_stock_code_name(basic_info_df):
    """
    从股票基本信息DataFrame中提取股票中文名称

    Parameters:
    -----------
    basic_info_df : pd.DataFrame
        由 get_stock_basic_info 返回的DataFrame

    Returns:
    --------
    str
        股票中文名称，获取失败返回 None
    """
    if basic_info_df is None or basic_info_df.empty:
        print("Stock basic information is empty, cannot get name")
        return None
    return basic_info_df.loc[0, "code_name"]


def save_fig_to_data_analyzed(fig, filename, output_dir=None):
    """Save a plotly figure to the specified directory (or DATA_ANALYZED_FILEPATH by default).

    Parameters:
    -----------
    fig : plotly.graph_objects.Figure
        The figure to save.
    filename : str
        The output filename (e.g. 'chart.html').
    output_dir : str, optional
        Custom output directory. Defaults to DATA_ANALYZED_FILEPATH.
    """
    target_dir = output_dir if output_dir else DATA_ANALYZED_FILEPATH
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, filename)
    fig.write_html(filepath)
    print(f"Chart saved to {filepath}")