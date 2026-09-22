"""活跃时段与随机间隔：控制请求节奏，降低被风控识别的概率。"""
import time


def parse_hhmm(text):
    """'6:30' -> 390 (当天 0:00 起的分钟数)。失败返回 None。"""
    try:
        hour, minute = text.strip().split(":", 1)
        return int(hour) * 60 + int(minute)
    except Exception:
        return None


def now_minutes():
    local = time.localtime()
    return local.tm_hour * 60 + local.tm_min


def in_active_hours(spec):
    """spec 如 '6:30-1:00' → 当前时刻是否在活跃段内。

    支持跨天：start>=end 时视为 [start,24:00)∪[00:00,end)。
    例如 6:30-1:00 = 6:30~次日1:00 活跃，1:00~6:30 暂停。
    空则全天放行。
    """
    if not spec or not spec.strip():
        return True
    try:
        start_text, end_text = spec.split("-", 1)
        start = parse_hhmm(start_text)
        end = parse_hhmm(end_text)
        if start is None or end is None:
            return True
    except Exception:
        return True
    now = now_minutes()
    if start < end:
        return start <= now < end
    return now >= start or now < end


def coerce_range(value, fallback):
    """把配置里的 [lo, hi] 规整为正整数区间，损坏时回退到 fallback。"""
    try:
        lo, hi = int(value[0]), int(value[1])
    except Exception:
        lo, hi = fallback
    if hi < lo:
        lo, hi = hi, lo
    return max(1, lo), max(1, hi)


def batch_range(cfg):
    """轮内每笔请求的间隔范围（秒）。"""
    return coerce_range(cfg.get("batch_interval"), (5, 15))


def round_wait(is_day, cfg):
    """每轮之间的等待范围（秒）：白天短、夜间长。"""
    key = "round_interval_day" if is_day else "round_interval_night"
    fallback = (300, 600) if is_day else (1200, 1800)
    return coerce_range(cfg.get(key), fallback)
