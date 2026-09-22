"""自定义异常与日志友好的错误摘要。"""


class RiskControl(Exception):
    """疑似触发教务风控，需立即停止以免账号受限。"""


class LoginExpired(Exception):
    """登录态过期（cookie 失效），需要重新登录。"""


def brief_error(e):
    """异常摘要：只取第一行并限长，避免 Playwright 调用日志把 cookie 写进日志文件。"""
    text = str(e).splitlines()[0].strip() if str(e) else ""
    return text[:200] or type(e).__name__
