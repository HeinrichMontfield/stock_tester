
# 代码风格
所有日志必须使用英文。
所有 import 必须在文件头。除非形成循环import时才能在函数内进行 import。
完成代码修改后，不要尝试执行代码，由我来手动执行测试结果。
你只能对修改这几个文件夹：[项目workspace]/scripts，[项目workspace]/data。对于其他文件夹都只能进行读取。

# 项目可用的 python packages
见 @requirements.txt。

# 项目结构
本项目为纯python，位于 /Users/mac/virtualenvs/venv_baostock/ 中。
venv_baostock 是一个 python 虚拟环境文件夹。
非第三方package的，自己编写的脚本文件都放在 ./scripts。
数据库访问操作在文件夹 ./scripts/database_ops。
整个库都可通用的函数在文件夹 ./scripts/utils。
