"""정부·기관 사이트에 등장하는 온갖 날짜 표기를 YYYY-MM-DD 로 정규화한다.

기관마다 표기가 제각각이라 여기가 가장 잘 깨지는 지점이다.
새로운 표기를 만나면 반드시 tests/test_dates.py 에 케이스를 추가할 것.
"""
from __future__ import annotations

import re
from datetime import date, datetime

# 요일 표기는 괄호로 감싸인 경우만 제거한다.
# 괄호 없이 지우면 "8월"의 '월'까지 날려버려 날짜 파싱이 통째로 깨진다.
_WEEKDAY = r"[(（\[]\s*[월화수목금토일]\s*[)）\]]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 2026-08-27, 2026.08.27, 2026/08/27, 2026. 8. 27.
    (re.compile(r"(\d{4})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})\s*\.?"), "ymd"),
    # 2026년 8월 27일
    (re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"), "ymd"),
    # 8월 27일 (연도 없음 -> 기준연도 사용)
    (re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일"), "md"),
    # 08.27 / 8.27 (연도 없음)
    (re.compile(r"\b(\d{1,2})\s*[./]\s*(\d{1,2})\b"), "md"),
]

_TIME = re.compile(r"(\d{1,2})\s*[:시]\s*(\d{1,2})?")


def parse_date(text: str, base_year: int | None = None) -> str | None:
    """문자열에서 첫 번째 날짜를 찾아 YYYY-MM-DD 로 반환. 못 찾으면 None."""
    if not text:
        return None
    cleaned = re.sub(_WEEKDAY, " ", text)
    base_year = base_year or date.today().year

    for pattern, kind in _PATTERNS:
        m = pattern.search(cleaned)
        if not m:
            continue
        try:
            if kind == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                y, mo, d = base_year, int(m.group(1)), int(m.group(2))
            return date(y, mo, d).isoformat()
        except ValueError:
            continue  # 2월 30일 같은 케이스 -> 다음 패턴 시도
    return None


def parse_date_range(text: str, base_year: int | None = None) -> tuple[str, str | None] | None:
    """'2026.10.05 ~ 10.24' 같은 기간 표기를 (시작, 종료)로 반환."""
    if not text:
        return None
    parts = re.split(r"\s*[~\-–—]\s*(?![0-9]{1,2}[.\-/][0-9]{1,2}[.\-/])", text, maxsplit=1)
    start = parse_date(parts[0], base_year)
    if not start:
        return None
    end = None
    if len(parts) == 2:
        end = parse_date(parts[1], base_year=int(start[:4]))
        if end and end < start:
            end = None
    return start, end


def parse_time(text: str) -> str | None:
    """'08:00', '오전 9시', '14시 30분' -> 'HH:MM'."""
    if not text:
        return None
    m = _TIME.search(text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if "오후" in text and hour < 12:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def now_kst_iso() -> str:
    from datetime import timedelta, timezone

    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
