"""USTC 教务系统登录（Playwright + storage_state）。Windows / Linux 通用。

登录态用 auth.json（Playwright storage_state，纯 JSON，含 cookie + localStorage，
跨平台可靠）。本机 `python grabbing.py --login` 生成，拷到别的机器即可。
不使用 .browser_data（Chromium profile），跨平台更稳。

无图形界面的机器（如 Linux 服务器）无法人工登录：请先在有浏览器的机器
`--login` 生成 auth.json，再拷过来。
"""
import os
import re
import time

from .config import AUTH_JSON

BASE = "https://jw.ustc.edu.cn"

_LOGIN_FAIL_MARKERS = ("验证码", "密码错误", "用户名或密码", "账号或密码", "账号被锁定",
                       "captcha", "invalid", "用户名错误", "验证失败", "请重新输入")


def open_context(headless=False, storage_state=None):
    """启动浏览器 context，返回 (playwright, context)。

    用 launch() + new_context(storage_state=...) 而非 launch_persistent_context()，
    因为后者不接受 storage_state 参数。登录态完全由 auth.json 承载（跨平台）。
    """
    from playwright.sync_api import sync_playwright
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    kwargs = dict(viewport={"width": 1280, "height": 800}, locale="zh-CN")
    if storage_state:
        kwargs["storage_state"] = storage_state
    return playwright, browser.new_context(**kwargs)


def storage_state_path():
    """auth.json 存在时返回路径，否则 None（表示从未登录过）。"""
    return AUTH_JSON if os.path.exists(AUTH_JSON) else None


def save_auth(context):
    """导出登录态到 auth.json（cookie + localStorage）。返回是否成功。"""
    try:
        context.storage_state(path=AUTH_JSON)
        return True
    except Exception as e:
        print("导出 auth.json 失败:", e)
        return False


def _first_page(context):
    return context.pages[0] if context.pages else context.new_page()


def auto_login(context, username=None, password=None, timeout_s=90):
    """尝试普通账号密码登录；遇到验证码或二次认证时返回 False。

    真实流程：jw/ucas-sso/login -> 302 到 id.ustc.edu.cn/cas/login（Angular 表单）。
    提交后即便已进入教务系统，URL 可能短暂仍停留在 id.ustc.edu.cn，
    因此成功判定不只看 URL，还检查页面是否已出现教务系统内容。
    """
    username = username or os.environ.get("USTC_USERNAME")
    password = password or os.environ.get("USTC_PASSWORD")
    if not username or not password:
        return False
    page = _first_page(context)
    try:
        page.goto(BASE + "/ucas-sso/login", wait_until="domcontentloaded")
    except Exception:
        return False

    # SSO 会话可能仍有效：页面会直接跳到教务主页（没有 #nameInput），
    # 此时应判定为已登录，而不是登录失败。
    if _login_succeeded(page):
        _settle_on_jw(page)
        return True

    try:
        page.wait_for_selector("#nameInput", timeout=15000)
    except Exception:
        if _login_succeeded(page):
            _settle_on_jw(page)
            return True
        return False

    try:
        _fill_credentials(page, username, password)
    except Exception:
        return False

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _login_succeeded(page):
            _settle_on_jw(page)
            return True
        if _login_failed(page):
            return False
        page.wait_for_timeout(1000)
    return False


def _fill_credentials(page, username, password):
    page.locator("#nameInput").fill(username)
    page.locator("input[type='password']").first.fill(password)
    # Angular 受控输入：fill 后补发 input 事件，确保双向绑定生效。
    for selector in ("#nameInput", "input[type='password']"):
        page.eval_on_selector(
            selector, "el => el.dispatchEvent(new Event('input', {bubbles: true}))")
    page.locator("#submitBtn").click()


def _settle_on_jw(page):
    """登录成功后回到教务主域，确保后续请求携带完整 cookie。"""
    try:
        if "jw.ustc.edu.cn" not in (page.url or ""):
            page.goto(BASE + "/for-std/course-select", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
    except Exception:
        pass


def _body_text(page):
    try:
        return page.inner_text("body")[:4000].lower()
    except Exception:
        return ""


def _login_failed(page):
    """检测明确的登录失败信号（验证码/密码错误等），避免无谓等待。"""
    text = _body_text(page)
    return bool(text) and any(m in text for m in _LOGIN_FAIL_MARKERS)


def _login_succeeded(page):
    """登录成功的判定：离开统一认证域，或页面已出现教务系统菜单。"""
    url = (page.url or "").lower()
    auth_hosts = ("id.ustc.edu.cn", "passport.ustc.edu.cn")
    if not any(h in url for h in auth_hosts) and "/login" not in url and "cas/login" not in url:
        return True
    try:
        # URL 可能未及时变化，但页面内容已切到教务系统主界面。
        return page.locator("a[href='/for-std/course-select']").count() > 0
    except Exception:
        return False


def _looks_like_login(url):
    low = (url or "").lower()
    return "passport.ustc.edu.cn" in low or "id.ustc.edu.cn" in low or "/login" in low


def _quick_sid(url):
    """从选课相关 URL 尽量取出 studentId；取不到返回 None（仅 --login 场景用）。"""
    match = re.search(r"/for-std/course-select/(?:turns/)?(\d+)", url or "")
    return match.group(1) if match else None


def ensure_login(context, headless=False, login_timeout_s=900,
                 forced_sid=None, forced_tid=None, need_turn=True):
    """确保已登录；未登录则等待人工登录。

    need_turn=False 时（如 --login 仅生成 auth.json）只验证登录，不解析选课轮次，
    返回 (sid 或 None, None)。
    """
    page = _first_page(context)
    page.goto(BASE + "/for-std/course-select", wait_until="domcontentloaded")

    if _looks_like_login(page.url):
        # 优先用 .env 的账号密码自动登录，避免每次都人工登录。
        print("登录态失效，尝试使用 .env 账号密码自动登录...")
        if auto_login(context):
            page = _first_page(context)
            save_auth(context)   # 持久化，避免下次再登录
            print("自动登录成功，登录态已保存。")
            return (_quick_sid(page.url), None) if not need_turn \
                else resolve_student_turn(page, forced_sid, forced_tid)

        if headless:
            raise RuntimeError(
                "未登录且自动登录失败（可能需要验证码/扫码），headless 模式无法人工登录。\n"
                "请在有图形界面的机器运行 `python grabbing.py --login` 生成 auth.json，\n"
                "再把 auth.json 拷到本项目下，然后以 headless 运行。")
        print("=" * 60)
        print("自动登录未成功（可能需要验证码或扫码），请在弹出的浏览器窗口中完成登录。")
        print("（账号密码 / 微信扫码均可）。登录成功后脚本会自动继续。")
        print("=" * 60)
        deadline = time.time() + login_timeout_s
        while _looks_like_login(page.url):
            if time.time() > deadline:
                raise TimeoutError("登录超时（15 分钟），请重新运行。")
            page.wait_for_timeout(2000)
        print("检测到登录成功，继续...\n")

    if not need_turn:
        return _quick_sid(page.url), None
    return resolve_student_turn(page, forced_sid, forced_tid)


def resolve_student_turn(page, forced_sid=None, forced_tid=None):
    """解析 studentId / turnId。forced 值优先。"""
    page.goto(BASE + "/for-std/course-select", wait_until="domcontentloaded")
    url = page.url

    sid, tid = None, None
    match = re.search(r"/for-std/course-select/(\d+)/turn/(\d+)", url)
    if match:
        sid, tid = match.group(1), match.group(2)
    else:
        only_sid = re.search(r"/for-std/course-select/turns/(\d+)", url)
        if only_sid:
            sid = only_sid.group(1)

    sid = forced_sid or sid
    tid = forced_tid or tid
    if not tid and sid:
        tid = _extract_turn_id(page)

    if not sid:
        raise RuntimeError(
            f"无法解析学号 studentId：{url}\n请在 config.json 显式设置 studentAssoc。")
    if not tid:
        raise RuntimeError(
            f"无法确定选课轮次 turnId（当前页：{url}）。\n"
            "请在 config.json 显式设置 courseSelectTurnAssoc（从选课页 URL .../turn/{turnId}/select 取）。")
    return sid, tid


def _extract_turn_id(page):
    """从 turns 列表页找第一个指向 /turn/{id} 的链接，返回 turnId。"""
    try:
        hrefs = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))")
    except Exception:
        return None
    for href in hrefs:
        if not href:
            continue
        match = re.search(r"/turn/(\d+)", href)
        if match:
            return match.group(1)
    return None
