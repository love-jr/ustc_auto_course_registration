"""邮件通知（QQ SMTP）。

相同内容在 dedup_seconds 内只发一次，避免失败类事件刷屏。
SMTP 密码优先取 email.password，其次读 password_env 指定的环境变量。
"""
import os
import smtplib
import time
from email.message import EmailMessage

DEFAULT_DEDUP_SECONDS = 600


class Notifier:
    def __init__(self, cfg):
        self.email = cfg.get("email") or {}
        self._sent_at = {}   # message -> 上次发送时间（monotonic）

    @property
    def enabled(self):
        return bool(self.email.get("enabled"))

    def _password(self):
        env_key = self.email.get("password_env", "")
        return self.email.get("password") or (os.environ.get(env_key, "") if env_key else "")

    def send(self, message, dedup_seconds=DEFAULT_DEDUP_SECONDS):
        print("[通知]", message)
        if not self.enabled:
            return
        now = time.monotonic()
        last = self._sent_at.get(message)
        if last is not None and now - last < dedup_seconds:
            return
        self._sent_at[message] = now
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[USTC抢课] {message.splitlines()[0][:80]}"
            msg["From"] = self.email["from"]
            msg["To"] = ", ".join(self.email.get("to", []))
            msg.set_content(message)
            self._deliver(msg)
        except Exception as e:
            print("  邮件通知失败:", type(e).__name__, e)

    def _deliver(self, msg):
        host = self.email["smtp_host"]
        password = self._password()
        if self.email.get("smtp_ssl", True):
            port = int(self.email.get("smtp_port", 465))
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                server.login(self.email["username"], password)
                server.send_message(msg)
        else:
            port = int(self.email.get("smtp_port", 587))
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                server.login(self.email["username"], password)
                server.send_message(msg)
