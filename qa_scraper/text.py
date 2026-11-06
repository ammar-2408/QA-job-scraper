"""Text helpers: HTML -> readable plain text, and date parsing."""
from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime, timedelta, timezone

from bs4 import BeautifulSoup

from . import config

_INLINE_TAGS = ("span", "b", "strong", "i", "em", "u", "a", "font", "sup", "sub", "small",
                "mark", "abbr", "cite", "code", "s", "strike", "big", "label", "ins", "del")
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")


def html_to_text(raw: str) -> str:
    """Posting HTML -> plain text. Inline tags are unwrapped first so text split
    across <a>/<span>/<b> stays on one line; list items get a bullet."""
    if not raw:
        return ""
    soup = BeautifulSoup(html_lib.unescape(raw), "lxml")
    for li in soup.find_all("li"):
        li.insert(0, "• ")
    for tag in soup.find_all(_INLINE_TAGS):
        tag.unwrap()
    soup.smooth()
    text = _ZERO_WIDTH.sub("", soup.get_text("\n"))
    lines = [" ".join(l.replace("\xa0", " ").split()) for l in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    # "• " on its own line followed by the item text -> join them
    text = re.sub(r"•\s*\n+", "• ", text)
    return text[: config.MAX_DESC]


def today() -> date:
    return datetime.now(timezone.utc).date()


def iso_date(value) -> str:
    """Accept an ISO string, epoch seconds/ms, or a datetime; return YYYY-MM-DD or ''."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        secs = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(secs, tz=timezone.utc).strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%d %b %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


_RELATIVE = re.compile(r"(\d+)\+?\s*(day|days|hour|hours|week|weeks|month|months)\b", re.I)


def relative_date(text: str) -> str:
    """'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' -> YYYY-MM-DD.
    '30+ Days Ago' is returned as 30 days back (it is definitely too old)."""
    t = (text or "").lower()
    if not t:
        return ""
    d = today()
    if "today" in t or "just posted" in t or "hour" in t:
        return d.isoformat()
    if "yesterday" in t:
        return (d - timedelta(days=1)).isoformat()
    m = _RELATIVE.search(t)
    if not m:
        return ""
    n, unit = int(m.group(1)), m.group(2).lower()
    days = n * {"day": 1, "week": 7, "month": 30}[unit.rstrip("s")] if not unit.startswith("hour") else 0
    return (d - timedelta(days=days)).isoformat()


def days_between(iso: str) -> int | None:
    if not iso:
        return None
    try:
        return (today() - date.fromisoformat(iso)).days
    except ValueError:
        return None
