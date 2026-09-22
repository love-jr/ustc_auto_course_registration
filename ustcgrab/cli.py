"""命令行入口：解析参数、接管日志输出。"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Tee:
    """同时写多个流（屏幕 + 日志文件）。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for stream in self.streams:
            try:
                stream.write(s)
                stream.flush()
            except Exception:
                pass

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                pass


def build_parser():
    parser = argparse.ArgumentParser(
        description="USTC 教务系统 监控式抢课（Windows / Linux 通用）")
    parser.add_argument("--lesson", help="目标课 lessonId，优先于配置文件")
    parser.add_argument("--name", help="目标课课程名（模糊匹配）")
    parser.add_argument("-m", "--mode", choices=["spam", "monitor", "grab"],
                        help="spam 自动提交(推荐) | monitor 仅刷新 | grab 同 spam")
    parser.add_argument("-t", "--interval", type=int, help="查询基准间隔（秒）")
    parser.add_argument("--headless", action="store_true", help="强制无头模式")
    parser.add_argument("--login", action="store_true",
                        help="仅登录建立登录态后退出（需图形界面）")
    parser.add_argument("--list", action="store_true",
                        help="列出可选课再退出（查 lessonId / 容量）")
    parser.add_argument("--log", help="同时把输出写入该日志文件")
    return parser


def main(argv=None):
    from . import runner

    args = build_parser().parse_args(argv)
    log_fp = None
    if args.log:
        log_path = args.log if os.path.isabs(args.log) else os.path.join(HERE, args.log)
        log_fp = open(log_path, "a", encoding="utf-8")
        sys.stdout = _Tee(sys.__stdout__, log_fp)
    args.log_fp = log_fp
    try:
        runner.run(args)
    finally:
        if log_fp:
            try:
                sys.stdout = sys.__stdout__
            except Exception:
                pass
