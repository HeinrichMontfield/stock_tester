# -*- coding: utf-8 -*-


from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError

# 连接 MongoDB
try:
    client = MongoClient("mongodb://localhost:27017/")
    # 测试连接是否真正可用
    client.admin.command('ping')
except ConnectionFailure:
    print("Connection failed. Cannot connect to MongoDB service, please check if the service is running")
except PyMongoError:
    print("Unknown error occurred during MongoDB connection")
except Exception:
    print("Unknown exception occurred during connection")

# ==========================
# 1. 查看本地有哪些数据库
# ==========================
print("All databases:")
try:
    db_names = client.list_database_names()
    print(db_names)
except PyMongoError:
    print("Failed to get database list")
except Exception:
    print("Unknown exception occurred while getting database list")
print("-" * 50)

# ==========================
# 2. 进入你的股票数据库
# ==========================
try:
    db = client["stock_db"]
except Exception:
    print("Failed to select stock database")

# ==========================
# 3. 查看有哪些表（集合）
# ==========================
print("All collections (tables):")
try:
    coll_names = db.list_collection_names()
    print(coll_names)
except PyMongoError:
    print("Failed to get collection list")
except Exception:
    print("Unknown exception occurred while getting collection list")
print("-" * 50)

# ==========================
# 4. 查看表结构 + 样例数据
# ==========================
def show_collection_info(collection_name):
    try:
        col = db[collection_name]
    except Exception:
        print("Failed to get collection object")
        return

    print(f"\nCollection: {collection_name}")
    
    # 获取数据总数
    try:
        count = col.count_documents({})
        print(f"Total documents: {count}")
    except PyMongoError:
        print("Failed to count documents")
        return
    except Exception:
        print("Unknown exception occurred while counting documents")
        return

    # 查看一条数据获取结构
    try:
        data = col.find_one()
    except PyMongoError:
        print("Failed to query single document")
        data = None
    except Exception:
        print("Unknown exception occurred while querying data")
        data = None

    if data:
        print("Collection structure (fields):")
        try:
            for key in data.keys():
                print(f"  - {key}")
        except Exception:
            print("Failed to traverse data fields")

        print("\nFirst data sample:")
        print(data)
    else:
        print("No data in the collection")

    # 查看索引
    print(f"\nIndexes:")
    try:
        indexes = col.index_information()
        for idx_name, idx_info in indexes.items():
            print(f"  {idx_name} : {idx_info['key']}")
    except PyMongoError:
        print("Failed to get index information")
    except Exception:
        print("Unknown exception occurred while getting indexes")

    print("=" * 60)

# ==========================
# 查看你的两张表
# ==========================
show_collection_info("stock_basic")   # 股票基本信息
show_collection_info("stock_kline")   # K线数据