#!/usr/bin/env python3
# encoding=utf8
"""Windows 后台启动器：无控制台窗口运行 grabbing.py（供开机自启动使用）。

等价于：python grabbing.py --headless --log run.log
双击或由计划任务用 pythonw.exe 调用，不会弹出黑窗口。
"""
import os
import sys
import runpy

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
sys.argv = ["grabbing.py", "--headless", "--log", "run.log"]
runpy.run_path(os.path.join(HERE, "grabbing.py"), run_name="__main__")
