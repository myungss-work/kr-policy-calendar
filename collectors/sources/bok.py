"""한국은행 주요 행사·공표 일정.

⚠️ 미검증 어댑터입니다.
    LIST_URL 과 아래 셀렉터는 실제 페이지 구조로 확인하기 전까지 초안입니다.
    Claude Code 에서 `python -m collectors.run --only bok --dry-run` 으로
    실제 응답을 찍어보고 셀렉터를 고친 뒤 optional=False 로 바꾸세요.

한국은행은 ECOS OpenAPI(통계)를 제공하지만 '일정'은 별도 API 가 없어
공지/일정 페이지를 읽습니다. API 가 확인되면 그쪽으로 갈아타는 게 맞습니다.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from .. import http
from ..base import Event, SourceAdapter
from ..dates import parse_date, parse_time

LIST_URL = "https://www.bok.or.kr/portal/main/contents.do?menuNo=200761"

# 제목에 이 단어가 들어가면 중요도를 올린다
HIGH_IMPORTANCE = ("금융통화위원회", "통화정책방향", "경제전망", "기준금리")


class BokAdapter(SourceAdapter):
    id = "bok"
    name = "한국은행 주요일정"
    agency = "한국은행"
    homepage = "https://www.bok.or.kr"
    optional = True  # 셀렉터 검증 전까지는 실패해도 전체 실행을 막지 않는다

    def fetch(self) -> str:
        return http.get(LIST_URL).text

    def parse(self, raw: str) -> list[Event]:
        soup = BeautifulSoup(raw, "html.parser")
        events: list[Event] = []

        # 일정표는 보통 <table> 또는 <li> 목록이다. 둘 다 시도한다.
        rows = soup.select("table tbody tr") or soup.select("ul.schedule li")
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.select("td, th, span, p")]
            if not cells:
                continue
            text = " ".join(cells)
            day = parse_date(text)
            if not day:
                continue
            title = self._pick_title(cells)
            if not title:
                continue

            link = row.select_one("a[href]")
            url = link["href"] if link else LIST_URL
            if url.startswith("/"):
                url = self.homepage + url

            events.append(Event(
                title=title,
                category="MONETARY",
                agency=self.agency,
                date=day,
                time=parse_time(text),
                importance=3 if any(k in title for k in HIGH_IMPORTANCE) else 2,
                status="CONFIRMED",
                source_id=self.id,
                source_url=url,
            ))
        return events

    @staticmethod
    def _pick_title(cells: list[str]) -> str:
        """날짜가 아닌 셀 중 가장 긴 것을 제목으로 본다."""
        candidates = [c for c in cells if c and not parse_date(c) and len(c) > 3]
        return max(candidates, key=len, default="")
