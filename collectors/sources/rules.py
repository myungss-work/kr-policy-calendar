"""공표 주기가 규칙적인 지표를 규칙으로 미리 채워 넣는다.

통계청·한국은행 지표 상당수는 '매월 n번째 영업일' 처럼 주기가 정해져 있다.
공식 공표일정을 긁어오기 전에도 달력이 비어 보이지 않게 하는 것이 목적이며,
여기서 만든 이벤트는 전부 status=TENTATIVE 다.
공식 어댑터가 같은 이벤트를 CONFIRMED 로 가져오면 그쪽이 이긴다.

⚠️ RULES 의 주기 값은 초안이다. 실제 공표일정으로 검증한 뒤 확정할 것.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..base import Event, SourceAdapter

# (제목, 카테고리, 기관, 중요도, 규칙)
# 규칙: ("nth_business_day", n) = 매월 n번째 영업일
#       ("day_of_month", d)     = 매월 d일 (주말이면 다음 영업일)
#       ("last_business_day",)  = 매월 마지막 영업일
RULES = [
    ("소비자물가동향", "INDICATOR", "통계청", 3, ("nth_business_day", 2)),
    ("고용동향", "INDICATOR", "통계청", 3, ("day_of_month", 15)),
    ("산업활동동향", "INDICATOR", "통계청", 2, ("last_business_day",)),
    ("국제수지(잠정)", "INDICATOR", "한국은행", 2, ("day_of_month", 7)),
    ("주택가격동향조사", "REALESTATE", "한국부동산원", 2, ("day_of_month", 20)),
]

MONTHS_AHEAD = 14


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _nth_business_day(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    count = 0
    while True:
        if not _is_weekend(d):
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)


def _last_business_day(year: int, month: int) -> date:
    d = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    while _is_weekend(d):
        d -= timedelta(days=1)
    return d


def _day_of_month(year: int, month: int, day: int) -> date:
    d = date(year, month, min(day, 28))
    while _is_weekend(d):
        d += timedelta(days=1)
    return d


def _resolve(rule: tuple, year: int, month: int) -> date:
    kind = rule[0]
    if kind == "nth_business_day":
        return _nth_business_day(year, month, rule[1])
    if kind == "day_of_month":
        return _day_of_month(year, month, rule[1])
    if kind == "last_business_day":
        return _last_business_day(year, month)
    raise ValueError(f"알 수 없는 규칙: {kind}")


class RuleAdapter(SourceAdapter):
    id = "rules"
    name = "정기 공표 추정"
    agency = "-"
    homepage = ""

    def fetch(self) -> date:
        return date.today().replace(day=1)

    def parse(self, start: date) -> list[Event]:
        events: list[Event] = []
        year, month = start.year, start.month
        for _ in range(MONTHS_AHEAD):
            for title, category, agency, importance, rule in RULES:
                d = _resolve(rule, year, month)
                events.append(Event(
                    title=f"{title} ({month}월 발표)",
                    category=category,
                    agency=agency,
                    date=d.isoformat(),
                    importance=importance,
                    status="TENTATIVE",
                    description="공표 주기로 추정한 잠정 일정입니다. 공식 공표일정으로 확인하세요.",
                    source_id=self.id,
                    tags=["추정"],
                ))
            month += 1
            if month > 12:
                month, year = 1, year + 1
        return events
