#!/usr/bin/env python3
# encoding=utf8
"""USTC 教务系统：监控式抢课（Windows / Linux 通用）。

实现已拆分到 ustcgrab 包，本文件保留为命令行入口，用法不变：

  python grabbing.py --login            # 本机：登录并生成 auth.json
  python grabbing.py --list             # 列出可选课（用于查 lessonId / 容量）
  python grabbing.py                    # 按 config.json 监控抢课
  python grabbing.py --lesson 123456 -t 60 --log run.log

模块划分见 ustcgrab/__init__.py。配置项说明见 README.md。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ustcgrab.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
