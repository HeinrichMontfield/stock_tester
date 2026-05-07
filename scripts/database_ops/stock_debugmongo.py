# -*- coding: utf-8 -*-

import os

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError

from scripts.utils import stock_logger

load_dotenv()

# 连接 MongoDB
try:
    client = MongoClient(os.getenv("MONGO_URI"))
    # 测试连接是否真正可用
    client.admin.command('ping')
except ConnectionFailure:
    stock_logger.debug("Connection failed. Cannot connect to MongoDB service, please check if the service is running")
except PyMongoError:
    stock_logger.debug("Unknown error occurred during MongoDB connection")
except Exception:
    stock_logger.debug("Unknown exception occurred during connection")

# ==========================
# 1. 查看本地有哪些数据库
# ==========================
stock_logger.debug("All databases:")
try:
    db_names = client.list_database_names()
    stock_logger.debug(db_names)
except PyMongoError:
    stock_logger.debug("Failed to get database list")
except Exception:
    stock_logger.debug("Unknown exception occurred while getting database list")
stock_logger.debug("-" * 50)

# ==========================
# 2. 进入你的股票数据库
# ==========================
try:
    db = client["stock_db"]
except Exception:
    stock_logger.debug("Failed to select stock database")

# ==========================
# 3. 查看有哪些表（集合）
# ==========================
stock_logger.debug("All collections (tables):")
try:
    coll_names = db.list_collection_names()
    stock_logger.debug(coll_names)
except PyMongoError:
    stock_logger.debug("Failed to get collection list")
except Exception:
    stock_logger.debug("Unknown exception occurred while getting collection list")
stock_logger.debug("-" * 50)

# ==========================
# 4. 查看表结构 + 样例数据
# ==========================
def show_collection_info(collection_name):
    try:
        col = db[collection_name]
    except Exception:
        stock_logger.debug("Failed to get collection object")
        return

    stock_logger.debug(f"\nCollection: {collection_name}")
    
    # 获取数据总数
    try:
        count = col.count_documents({})
        stock_logger.debug(f"Total documents: {count}")
    except PyMongoError:
        stock_logger.debug("Failed to count documents")
        return
    except Exception:
        stock_logger.debug("Unknown exception occurred while counting documents")
        return

    # 查看一条数据获取结构
    try:
        data = col.find_one()
    except PyMongoError:
        stock_logger.debug("Failed to query single document")
        data = None
    except Exception:
        stock_logger.debug("Unknown exception occurred while querying data")
        data = None

    if data:
        stock_logger.debug("Collection structure (fields):")
        try:
            for key in data.keys():
                stock_logger.debug(f"  - {key}")
        except Exception:
            stock_logger.debug("Failed to traverse data fields")

        stock_logger.debug("\nFirst data sample:")
        stock_logger.debug(data)
    else:
        stock_logger.debug("No data in the collection")

    # 查看索引
    stock_logger.debug(f"\nIndexes:")
    try:
        indexes = col.index_information()
        for idx_name, idx_info in indexes.items():
            stock_logger.debug(f"  {idx_name} : {idx_info['key']}")
    except PyMongoError:
        stock_logger.debug("Failed to get index information")
    except Exception:
        stock_logger.debug("Unknown exception occurred while getting indexes")

    stock_logger.debug("=" * 60)

# ==========================
# 查看你的两张表
# ==========================
show_collection_info("stock_basic")   # 股票基本信息
show_collection_info("stock_kline")   # K线数据