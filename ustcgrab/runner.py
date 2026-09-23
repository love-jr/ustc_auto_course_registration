"""登录 → 列课 → 监控抢课主循环。

核心思路：每轮按 priority 直接 POST add-request / add-drop-response。
容量和已选人数不作为提交前置条件，因为真实系统可能出现已选人数超过
limitCount 的课程。叠加：事务间隔、随机睡眠、活跃时段、失败熔断和登录失效通知。
"""
import os
import random
import socket
import sys
import time

from . import api, courses as courses_mod, fields, login, pacing
from .config import load_config
from .errors import LoginExpired, RiskControl, brief_error
from .notify import Notifier

NETWORK_HINTS = ("err_name_not_resolved", "enotfound", "econnreset", "etimedout",
                 "err_internet_disconnected", "err_connection", "err_network",
                 "net::err", "getaddrinfo", "socket disconnected", "tls")

NETWORK_WAIT_LIMIT_S = 600
LOGIN_NETWORK_RETRY_LIMIT = 60
LOGIN_SOFT_FAIL_LIMIT = 3
LOGIN_RETRY_DELAY_S = 60


def network_ready(host="jw.ustc.edu.cn"):
    """DNS 能否解析教务域名，用于开机自启时等待网络就绪。"""
    try:
        socket.getaddrinfo(host, 443)
        return True
    except Exception:
        return False


def is_network_error(e):
    return any(h in str(e).lower() for h in NETWORK_HINTS)


def default_headless():
    """默认是否无头：Windows/macOS 有桌面→False；Linux 无 $DISPLAY→True。"""
    if sys.platform in ("win32", "darwin"):
        return False
    return not bool(os.environ.get("DISPLAY"))


def print_lessons(items, limit=20):
    if not items:
        print("（无数据）")
        return
    print("字段示例(第一条keys):", list(items[0].keys()))
    print(f"{'lessonId':<10}{'容量':<6}{'课程名':<28}老师")
    for item in items[:limit]:
        print(f"{fields.lesson_id(item):<10}{str(fields.limit_of(item)):<6}"
              f"{fields.course_name(item):<28}{fields.teacher_text(item)}")


def _wait_for_network():
    """开机自启可能早于网络就绪：先等 DNS 可用，再尝试登录。"""
    waited = 0
    while not network_ready() and waited < NETWORK_WAIT_LIMIT_S:
        if waited == 0:
            print("网络未就绪，等待网络恢复后再登录...")
        time.sleep(10)
        waited += 10
    if waited:
        print(f"网络已就绪（等待 {waited}s）。")


def _login_with_retry(context, cfg, headless, need_turn):
    """登录失败自动重试：网络类错误一直等网络恢复；疑似网络抖动也容忍几次。"""
    attempt = 0
    soft_fail = 0
    while True:
        attempt += 1
        try:
            return login.ensure_login(
                context, headless=headless,
                forced_sid=cfg.get("studentAssoc") or None,
                forced_tid=cfg.get("courseSelectTurnAssoc") or None,
                need_turn=need_turn)
        except Exception as e:
            brief = brief_error(e)
            if (is_network_error(e) or not network_ready()) and attempt < LOGIN_NETWORK_RETRY_LIMIT:
                print(f"[{time.strftime('%H:%M:%S')}] 网络异常（第 {attempt} 次）：{brief}")
                print(f"    {LOGIN_RETRY_DELAY_S}s 后重试登录...")
                time.sleep(LOGIN_RETRY_DELAY_S)
                continue
            # 网络貌似正常但登录仍失败：可能是网络抖动导致，容忍几次
            soft_fail += 1
            if soft_fail <= LOGIN_SOFT_FAIL_LIMIT:
                print(f"[{time.strftime('%H:%M:%S')}] 登录未成功（第 {soft_fail} 次）：{brief}")
                print(f"    {LOGIN_RETRY_DELAY_S}s 后重试登录...")
                time.sleep(LOGIN_RETRY_DELAY_S)
                continue
            print(f"登录失败：{type(e).__name__}: {brief}")
            return None


def recover_login(context):
    """会话失效后尝试普通账号密码登录；需要 MFA 时交给通知和人工处理。"""
    if not login.auto_login(context):
        return False
    return login.save_auth(context)


class Monitor:
    """监控循环：持有课程列表和已选状态，逐轮尝试选课。"""

    def __init__(self, context, sid, tid, cfg, notifier):
        self.context = context
        self.sid = sid
        self.tid = tid
        self.cfg = cfg
        self.notifier = notifier
        self.courses = []
        self.mode = cfg["mode"]
        self.day_hours = (cfg.get("day_hours") or "").strip()
        self.refresh_seconds = max(300, int(cfg.get("refresh_seconds", 900)))
        self.max_errors = max(3, int(cfg.get("max_errors", 20)))
        self.consecutive_errors = 0
        self.last_refresh = 0.0

    def prepare(self):
        """设置请求节奏并拉取全部可选课，供 --list 展示或 bind 绑定。"""
        api.throttle.set_interval(*pacing.batch_range(self.cfg))
        return api.list_all_lessons(self.context, self.sid, self.tid)

    def bind(self, items):
        selected = api.list_selected_lessons(self.context, self.sid, self.tid)
        self.courses = courses_mod.resolve_courses(items, self.cfg.get("courses", []))
        courses_mod.refresh_selected(self.courses, selected)
        courses_mod.apply_conflict_policy(self.courses, selected)
        print_lessons([c["item"] for c in self.courses])
        for left, right in courses_mod.conflict_pairs(self.courses):
            print("⚠️", f"目标课程时间冲突：{courses_mod.label(left)} ↔ "
                        f"{courses_mod.label(right)}；按 priority 先尝试高优先级课程")
        for course in self.courses:
            if course["selected"]:
                print(f"已选：{courses_mod.label(course)}")
            elif course["blocked"]:
                print("⚠️", f"跳过：{courses_mod.label(course)} 与当前已选课程时间冲突")
        self.last_refresh = time.monotonic()
        self._print_plan()

    def _print_plan(self):
        batch_lo, batch_hi = pacing.batch_range(self.cfg)
        day_lo, day_hi = pacing.round_wait(True, self.cfg)
        night_lo, night_hi = pacing.round_wait(False, self.cfg)
        print(f"\n监控抢课：{len(self.courses)} 门课程 | 元数据刷新 {self.refresh_seconds}s "
              f"| 模式={self.mode} | 熔断={self.max_errors}")
        print(f"轮内：每笔 {batch_lo}–{batch_hi}s 快速依次尝试（模拟手动点选）")
        print(f"轮间：白天 {self.day_hours or '全天'} 等 {day_lo}–{day_hi}s；"
              f"夜间等 {night_lo}–{night_hi}s")
        print("逻辑：每轮按 priority 直接提交所有未成功课程；失败下轮继续；风控信号即停。\n")

    def _apply_state(self, selected):
        """按已选快照重算每门课的 selected / blocked。"""
        courses_mod.refresh_selected(self.courses, selected)
        courses_mod.apply_conflict_policy(self.courses, selected)

    def _sync_selected(self):
        selected = api.list_selected_lessons(self.context, self.sid, self.tid)
        self._apply_state(selected)
        return selected

    def _refresh_metadata(self, selected):
        """周期性刷新课程元数据（容量等可能变化），复用本轮已选快照。"""
        refreshed = api.list_all_lessons(self.context, self.sid, self.tid)
        by_id = {fields.lesson_id(item): item for item in refreshed}
        for course in self.courses:
            if course["id"] in by_id:
                course["item"] = by_id[course["id"]]
        self._apply_state(selected)

    def _attempt_all(self, ts, selected):
        """按 priority 依次尝试所有未成功课程。

        轮内短间隔、不退避，模拟人一次查看并快速抢几门；成功后立即按
        「已选 + 本轮已选快照」重算冲突策略。selected 沿用本轮开头抓取的快照，
        与原行为保持一致。
        """
        pending = courses_mod.pending_by_priority(self.courses)
        if pending:
            print(f"[{ts}] 本轮尝试 {len(pending)} 门："
                  + "、".join(fields.course_name(c["item"]) for c in pending))
        for course in pending:
            if course["selected"] or course["blocked"]:
                continue
            ok, msg = api.grab(self.context, self.sid, self.tid, course["id"])
            print(f"[{time.strftime('%H:%M:%S')}] {courses_mod.label(course)} "
                  f"选课结果: ok={ok} | {msg}")
            if ok:
                course["selected"] = True
                courses_mod.apply_conflict_policy(self.courses, selected)
                self.notifier.send(f"选课成功：{courses_mod.label(course)}")
        print(f"[{time.strftime('%H:%M:%S')}] 本轮结束")

    def _all_done(self):
        return all(c["selected"] or c["blocked"] for c in self.courses)

    def run(self):
        """返回退出原因字符串。"""
        rounds = 0
        while True:
            rounds += 1
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            is_day = pacing.in_active_hours(self.day_hours)
            try:
                selected = self._sync_selected()
                if time.monotonic() - self.last_refresh >= self.refresh_seconds:
                    self._refresh_metadata(selected)
                    self.last_refresh = time.monotonic()
                    print(f"[{ts}] 已刷新课程信息和已选状态")

                if self.mode in ("spam", "grab"):
                    self._attempt_all(ts, selected)
                else:
                    print(f"[{ts}] 监控模式，仅刷新状态，不提交选课请求")
                self.consecutive_errors = 0

            except RiskControl as e:
                print(f"[{ts}] ⛔ 疑似触发教务风控：{e}")
                print("    为避免账号受限，脚本主动停止。请降低频率或改手动，稍后再试。")
                self.notifier.send(f"疑似触发风控，脚本已自动停止：{e}")
                return "risk"

            except LoginExpired as e:
                print(f"[{ts}] #{rounds} ⚠️ {e}")
                print("    尝试使用 .env 账号密码自动重新登录...")
                if recover_login(self.context):
                    print("    自动重新登录成功，继续监控（不打扰用户）。")
                    self.consecutive_errors = 0
                    continue
                print("    自动登录失败（可能需要验证码/扫码），已邮件告警并停止。")
                self.notifier.send("登录态失效且自动登录失败，需要人工重新登录（可能需验证码/扫码）")
                return "login-expired"

            except Exception as e:
                brief = brief_error(e)
                if is_network_error(e):
                    # 网络抖动/中断不消耗熔断次数，否则断网久了会被误停。
                    print(f"[{ts}] #{rounds} 网络异常（不计熔断）：{brief}")
                else:
                    self.consecutive_errors += 1
                    print(f"[{ts}] #{rounds} 异常 {type(e).__name__}: {brief}")
                    if self.consecutive_errors >= self.max_errors:
                        print(f"连续 {self.consecutive_errors} 次异常，触发熔断，停止。"
                              "请检查网络/登录态。")
                        self.notifier.send("监控熔断停止（连续异常）")
                        return "circuit-breaker"

            if self._all_done():
                self.notifier.send("所有可执行目标课程均已处理，监控结束")
                return "done"

            # 轮间等待：白天短、夜间长；随机以避免固定节拍。
            low, high = pacing.round_wait(is_day, self.cfg)
            time.sleep(random.uniform(low, high))


def run(args):
    """CLI 主流程。args 为 argparse 结果。"""
    cfg = load_config()
    if args.lesson:
        cfg["courses"] = [{"lessonAssoc": args.lesson, "priority": 1}]
    if args.name:
        cfg["courses"] = [{"name": args.name, "priority": 1}]
    if args.mode:
        cfg["mode"] = args.mode
    if args.interval:
        # -t 覆盖白天每轮等待：以该值为中心 ±30% 作为白天随机区间
        base = max(30, int(args.interval))
        cfg["round_interval_day"] = [int(base * 0.7), int(base * 1.3)]

    headless = cfg.get("headless", default_headless())
    if args.headless:
        headless = True
    if args.login:
        headless = False

    notifier = Notifier(cfg)
    playwright, context = login.open_context(
        headless=headless, storage_state=login.storage_state_path())
    try:
        _wait_for_network()
        result = _login_with_retry(context, cfg, headless, need_turn=not args.login)
        if result is None:
            notifier.send("登录失败且自动登录未成功，可能需要人工处理（验证码/扫码）")
            if headless:
                print("提示：请在 .env 配置 USTC_USERNAME 和 USTC_PASSWORD；"
                      "如需验证码或扫码，请运行 --login。")
            return
        sid, tid = result
        print(f"已登录。studentId={sid}  turnId={tid}")

        if args.login:
            login.save_auth(context)
            print("登录态已保存到 ./auth.json（cookie，跨平台）。")
            print("下一步：点进选课页，地址栏 .../turn/<数字>/select 中的 <数字> "
                  "即 courseSelectTurnAssoc；")
            print("        再把 studentAssoc / courseSelectTurnAssoc / lessonAssoc "
                  "填入 config.json。")
            return

        monitor = Monitor(context, sid, tid, cfg, notifier)
        items = monitor.prepare()
        if args.list:
            print_lessons(items)
            return
        monitor.bind(items)
        monitor.run()
    finally:
        _cleanup(context, playwright, getattr(args, "log_fp", None))


def _cleanup(context, playwright, log_fp):
    """三处资源清理彼此独立，任一失败不影响其余。"""
    for close in (context.close, playwright.stop, log_fp.close if log_fp else None):
        if close is None:
            continue
        try:
            close()
        except Exception:
            pass
