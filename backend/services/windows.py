"""Delivery-window text -> minutes since midnight. Understands '09:00-11:00', 'Today 18:00-21:00', '9-11', '18:00 to 21:00'."""
import re

_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(?:[\u2013\u2014\-]|to)\s*(\d{1,2})(?::(\d{2}))?", re.I)
DAY_START, DAY_END = 8 * 60, 22 * 60


def parse_window(text, default=(DAY_START, DAY_END)):
    m = _RE.search(text or "")
    if not m:
        return default
    a = int(m.group(1)) * 60 + int(m.group(2) or 0)
    b = int(m.group(3)) * 60 + int(m.group(4) or 0)
    if not (0 <= a < 24 * 60 and a < b <= 24 * 60):
        return default
    return a, b


def clock(minutes) -> str:
    m = int(round(minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"
