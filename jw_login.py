#!/usr/bin/env python3
# encoding=utf8
"""USTC 教务系统登录模块（兼容入口）。

实现已迁移到 ustcgrab.login。本文件保留旧的导入路径，
使 `import jw_login` 的既有用法（含 grabbing.py 的历史版本、外部脚本）继续可用。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ustcgrab.config import AUTH_JSON, ENV_PATH  # noqa: E402,F401
from ustcgrab.login import (  # noqa: E402,F401
    BASE,
    auto_login,
    ensure_login,
    open_context,
    resolve_student_turn,
    save_auth,
)

__all__ = [
    "AUTH_JSON", "BASE", "ENV_PATH",
    "auto_login", "ensure_login", "open_context", "resolve_student_turn", "save_auth",
]
