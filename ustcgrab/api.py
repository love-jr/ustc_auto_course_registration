"""教务接口传输层。

接口契约（全部为 application/x-www-form-urlencoded，来自真实抓包）：
  GET  /for-std/course-select                     -> 302 到 .../{sid}/turn/{tid}/select
  POST /ws/for-std/course-select/addable-lessons   body: turnId, studentId            （--list 列课用）
  POST /ws/for-std/course-select/selected-lessons  body: turnId, studentId            （已选课）
  POST /ws/for-std/course-select/add-request       body: studentAssoc, lessonAssoc,
                                                      courseSelectTurnAssoc, scheduleGroupAssoc, virtualCost
                                                  -> 返回 requestId
  POST /ws/for-std/course-select/add-drop-response body: studentId, requestId         -> 确认选课

节流：轮内每笔请求之间随机等待，模拟人一次快速查看/操作多门课，
避免固定节拍被识别为脚本。选课确认步骤关闭节流以保持事务连续。
"""
import json
import random
import re
import time
from urllib.parse import urlencode

from .errors import LoginExpired, RiskControl
from . import fields

BASE = "https://jw.ustc.edu.cn"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_RISK_MARKERS = ("请求过于频繁", "访问频繁", "操作频繁", "请求频繁", "风控",
                 "账号异常", "账号受限", "禁止访问", "拒绝访问", "频繁访问",
                 "too many requests", "rate limit", "access denied")

_LOGIN_PAGE_MARKERS = ("<html", "/login", "passport.ustc", "id.ustc", "cas/login")


class _Throttle:
    """轮内请求节流状态。"""

    def __init__(self):
        self.last_at = 0.0
        self.low = 5.0
        self.high = 15.0

    def set_interval(self, low, high):
        self.low, self.high = low, high

    def wait(self):
        target = random.uniform(self.low, self.high)
        delay = target - (time.monotonic() - self.last_at)
        if delay > 0:
            time.sleep(delay)

    def mark(self):
        self.last_at = time.monotonic()


throttle = _Throttle()


def referer(sid, tid):
    return f"{BASE}/for-std/course-select/{sid}/turn/{tid}/select"


def post(context, path, pairs, referer_url, throttle_enabled=True):
    """发 form-urlencoded POST，返回 Playwright 的 APIResponse。"""
    if throttle_enabled:
        throttle.wait()
    response = context.request.post(
        BASE + path,
        data=urlencode(pairs),
        headers={
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "referer": referer_url,
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        timeout=30000,
    )
    throttle.mark()
    return response


def looks_like_login_page(body, status):
    low = (body or "").lower()
    return status in (401, 403) or any(m in low for m in _LOGIN_PAGE_MARKERS)


def check_risk(status, text):
    """识别可能触发风控的响应，命中即抛 RiskControl 立即停止。"""
    low = (text or "").lower()
    if status == 429 or any(m.lower() in low for m in _RISK_MARKERS):
        raise RiskControl(f"疑似风控 HTTP {status}: {(text or '')[:160]!r}")


def _json_or_raise(response, endpoint):
    body = response.text()
    if looks_like_login_page(body, response.status):
        raise LoginExpired(f"登录态已过期（{endpoint} status={response.status}）")
    try:
        return response.json()
    except Exception as e:
        raise RuntimeError(f"{endpoint} 返回非 JSON(status={response.status})") from e


def list_lessons(context, sid, tid, page=None, size=None):
    pairs = [("turnId", tid), ("studentId", sid)]
    if page is not None:
        pairs.append(("page", page))
    if size is not None:
        pairs.append(("size", size))
    response = post(context, "/ws/for-std/course-select/addable-lessons",
                    pairs, referer(sid, tid))
    return _json_or_raise(response, "addable-lessons")


def list_selected_lessons(context, sid, tid):
    """读取当前已选课程，用于识别已经成功的目标和时间冲突。"""
    response = post(context, "/ws/for-std/course-select/selected-lessons",
                    [("turnId", tid), ("studentId", sid)], referer(sid, tid))
    return _json_or_raise(response, "selected-lessons")


def list_all_lessons(context, sid, tid, max_pages=30, size=100):
    """自动翻页取全部可选课。按 lessonId 去重；分页参数无效时会自动停止。"""
    seen, order = {}, []
    for page in range(1, max_pages + 1):
        items = fields.iter_items(list_lessons(context, sid, tid, page=page, size=size))
        if not items:
            break
        new = 0
        for item in items:
            lid = fields.lesson_id(item)
            if lid and lid not in seen:
                seen[lid] = item
                order.append(item)
                new += 1
        # 当前教务接口会直接返回全部课程（1170 条），避免无意义的重复请求。
        if len(items) > size or new == 0 or len(items) < size:
            break
    return order


def add_request(context, sid, tid, lesson_id):
    return post(context, "/ws/for-std/course-select/add-request",
                [("studentAssoc", sid), ("lessonAssoc", str(lesson_id)),
                 ("courseSelectTurnAssoc", tid), ("scheduleGroupAssoc", ""),
                 ("virtualCost", "0")], referer(sid, tid))


def add_drop_response(context, sid, tid, request_id):
    return post(context, "/ws/for-std/course-select/add-drop-response",
                [("studentId", sid), ("requestId", request_id)], referer(sid, tid),
                throttle_enabled=False)


def parse_add_result(response):
    """add-drop-response 结果解析。

    真实结构：{success, errorMessage:{textZh,...}, ...}
    返回 (是否成功, 提示消息)。
    """
    text = response.text()
    try:
        data = response.json()
    except Exception:
        data = None
    if isinstance(data, dict):
        ok = bool(data.get("success", data.get("ok", False)))
        error = data.get("errorMessage")
        if isinstance(error, dict):
            msg = (error.get("textZh") or error.get("text") or error.get("textEn")
                   or json.dumps(error, ensure_ascii=False))
        else:
            msg = (data.get("msg") or data.get("message")
                   or json.dumps(data, ensure_ascii=False))
        # 接口偶发 success=false 但文案表示已选上，按成功处理。
        if not ok and ("成功" in msg or "已选" in msg):
            ok = True
        return ok, msg
    ok = ("true" in text.lower()) or ("成功" in text) or ("已选" in text)
    return ok, text[:200]


def grab(context, sid, tid, lesson_id):
    """执行一次选课：add-request 拿 requestId，再 add-drop-response 确认。"""
    first = add_request(context, sid, tid, lesson_id)
    body = first.text()
    check_risk(first.status, body)
    request_id = body.strip().strip('"')
    if not _UUID_RE.match(request_id):
        if looks_like_login_page(body, first.status):
            raise LoginExpired(f"登录态已过期（add-request status={first.status}）")
        return False, f"add-request 未返回 requestId(status={first.status}): {body[:160]}"

    second = add_drop_response(context, sid, tid, request_id)
    body2 = second.text()
    check_risk(second.status, body2)
    if looks_like_login_page(body2, second.status):
        raise LoginExpired(f"登录态已过期（add-drop-response status={second.status}）")
    return parse_add_result(second)
