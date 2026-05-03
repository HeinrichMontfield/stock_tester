
# 代码风格
所有日志必须使用英文。
所有 import 必须在文件头。除非形成循环import时才能在函数内进行 import。

# 项目可用的 python packages
baostock          0.9.1
dnspython         2.8.0
narwhals          2.20.0
numpy             2.4.4
packaging         26.2
pandas            3.0.2
pandas-ta-classic 0.5.44
pip               24.0
plotly            6.7.0
pymongo           4.17.0
python-dateutil   2.9.0.post0
setuptools        65.5.0
six               1.17.0

# 项目结构
本项目为纯python，位于 /Users/mac/virtualenvs/venv_baostock/ 中。
venv_baostock 是一个 python 虚拟环境文件夹。
非第三方package的，自己编写的脚本文件都放在 ./scripts。
数据库访问操作在文件夹 ./scripts/database_ops。
整个库都可通用的函数在文件夹 ./scripts/utils。
