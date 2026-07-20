"""한국은행 행사 일정 캘린더 (menuNo=200035).

실측 확인 (Claude Code 가 실제로 fetch 하여 확인, 2026-07-21 기준):

- LIST_URL: https://www.bok.or.kr/portal/singl/mainEvent/listCldr.do
    쿼리 menuNo=200035 로 "행사일정" 페이지가 뜨고, date=YYYY-MM 쿼리로
    월을 이동한다 (예: date=2026-08 요청 시 실제로 8월 달력이 온다).
    ※ menuNo=200761 ("금융통화위원회 의사록 및 의결사항")과
      menuNo=200643 ("통화정책방향 결정회의 일정 및 자료"라는 이름이지만
      실제로는 과거 기준금리 변경 이력 표)는 모두 미래 일정표가 아니므로
      쓰지 않는다. menuNo=200775 (통계공표일정)는 INDICATOR 성격의 별도
      소스 후보이며 이 어댑터 범위 밖이다.

- DOM 구조 (raw HTML 을 직접 저장해 눈으로 확인함):
    <div class="calendarSet ..."><table>...</table></div> 안의
    <tbody><tr><td> 하나가 하루다("calendarSet" 은 table 이 아니라 그 바깥
    div 의 class 다 — 처음에 table.calendarSet 로 짰다가 실측 HTML 로
    확인 후 div.calendarSet table 로 고쳤다).
      - 날짜: <td><div class="top"> <span>16</span></div> ... </td>
      - 그 날 일정이 있으면 같은 <td> 안에
          <ul><li>
            <span class="ico ico3">회<span class="hidden">회의</span></span>
            <a href="javascript:void(0);" data-toggle="modal"
               data-target="#modalBox1"
               onclick="schdulPop('319', '03', '16')">통화정책방향 회의</a>
          </li></ul>
        일정이 없는 날은 <ul> 자체가 없다.
      - onclick 의 세 인자는 (eventSn, eventSeCd, day). eventSn 은 BOK 쪽
        전역 고유 ID로 보인다(실측 관측: 311~322 가 2025-10~2026-11 에
        걸쳐 순차 증가).
      - 여러 날짜에 걸친 행사(예: "2026 BOK 국제컨퍼런스")는 각 날짜 칸에
        같은 eventSn 으로 중복 등장한다(실측: 2026-06-01, 06-02 에 같은
        eventSn='119'). 그래서 eventSn 으로 묶어 시작일~종료일 하나의
        Event 로 만든다(날짜 칸마다 별도 Event 를 만들면 안 된다).
    - 페이지 상단 <span id="yymm"><strong>2026</strong>년 <strong>07</strong>월
      </span> 에서 그 페이지가 실제로 렌더한 연/월을 읽는다. 요청한
      date= 파라미터를 그대로 믿지 않고 응답에 찍힌 값을 신뢰한다.
    - 시각(time) 정보는 이 페이지에 없다(모달 팝업 AJAX 안에 있을 수도
      있으나 미확인). 항상 종일 일정으로 둔다.

- robots.txt: `Disallow: /` 에 `Allow: /portal/` 예외가 있어 이 경로는
  허용된다(실측 확인). 기존 collectors/http.py 의 urllib.robotparser 로
  그대로 통과한다 — 아래를 직접 확인했다:
      http.allowed("https://www.bok.or.kr/portal/singl/mainEvent/listCldr.do")
        -> True
      http.allowed("https://www.bok.or.kr/admin/x")  -> False
  (작업 중 한때 "urllib.robotparser 가 최장일치를 안 해서 /portal/ 을
   차단으로 오판한다"고 보고 http.py 를 재작성했으나, 실제로 검증해 보니
   urllib 는 /portal/ 을 정상 허용하고 /admin/ 은 정상 차단한다.
   전제가 틀려서 그 재작성은 되돌렸다. http.py 는 손대지 않는다.)

- 이벤트 밀도: 2026년 한 해 기준으로 실측한 결과 통화정책방향 회의가
  9회(1,2,4,5,6,7,8,10,11월. 3,9,12월은 없음) + 컨퍼런스/세미나 등 부정기
  행사가 섞여 총 10건 안팎이다. 월 1건 안팎이라 최근 몇 달만 보면 10건을
  못 채울 수 있어, 과거 9개월 + 미래 6개월(총 16개월) 창으로 넉넉히
  수집한다.

미확인 / 남은 한계:
  - 시각(time)이 어디에도 없어 항상 종일로 처리한다.
  - eventSeCd(01 컨퍼런스/02 세미나/03 총재회의/04 포럼)를 카테고리 분류에는
    아직 안 쓴다. Event.CATEGORIES 에 "통화정책" 외에 맞는 항목이 없어
    전부 MONETARY 로 두고, importance 로만 구분한다(회의/기준금리류만 3).
  - 이 페이지가 항상 정확한 "확정" 일정인지, 아니면 예정이 바뀔 수 있는
    잠정 표인지는 BOK 쪽에 별도 확인이 없다. 다만 기관이 직접 운영하는
    공식 행사 캘린더이므로 CONFIRMED 로 둔다(불확실하면 나중에 조정).
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from .. import http
from ..base import Event, SourceAdapter

LIST_URL = "https://www.bok.or.kr/portal/singl/mainEvent/listCldr.do"
MENU_NO = "200035"

# 수집할 월 범위 (오늘 기준). 월 1건 안팎이라 넉넉히 잡아야 10건 이상 나온다.
# 요청 수 = MONTHS_BACK + MONTHS_AHEAD + 1 이고 http.py 가 요청당 1.5초를
# 쉬므로 16회 ≈ 24초.
MONTHS_BACK = 9
MONTHS_AHEAD = 6

# 제목에 이 단어가 들어가면 중요도를 올린다
HIGH_IMPORTANCE = ("금융통화위원회", "통화정책방향", "경제전망", "기준금리")

_ONCLICK = re.compile(r"schdulPop\(\s*'(\d+)'\s*,\s*'(\d+)'\s*,\s*'(\d+)'\s*\)")


def _months(today: date) -> list[str]:
    """'YYYY-MM' 목록을 만든다."""
    out = []
    total = today.year * 12 + (today.month - 1)
    for offset in range(-MONTHS_BACK, MONTHS_AHEAD + 1):
        n = total + offset
        out.append(f"{n // 12:04d}-{n % 12 + 1:02d}")
    return out


class BokAdapter(SourceAdapter):
    id = "bok"
    name = "한국은행 주요일정"
    agency = "한국은행"
    homepage = "https://www.bok.or.kr"
    optional = True  # 실제 응답으로 검증했지만, 이 페이지 구조 변경에 취약해 유지

    def fetch(self) -> list[str]:
        pages: list[str] = []
        for month in _months(date.today()):
            resp = http.get(LIST_URL, params={"menuNo": MENU_NO, "date": month})
            pages.append(resp.text)
        return pages

    def parse(self, raw: list[str]) -> list[Event]:
        # eventSn -> {"title": str, "dates": set[str]}
        grouped: dict[str, dict] = {}

        for html in raw:
            soup = BeautifulSoup(html, "html.parser")
            year, month = self._page_year_month(soup)
            if year is None or month is None:
                continue
            table = soup.select_one("div.calendarSet table")
            if not table:
                continue
            for td in table.select("tbody td"):
                day_span = td.select_one("div.top span")
                if not day_span:
                    continue
                day_text = day_span.get_text(strip=True)
                if not day_text.isdigit():
                    continue
                day = int(day_text)
                for a in td.select("ul li a[onclick]"):
                    m = _ONCLICK.search(a.get("onclick", ""))
                    if not m:
                        continue
                    event_sn = m.group(1)
                    title = a.get_text(" ", strip=True)
                    if not title:
                        continue
                    try:
                        iso = date(year, month, day).isoformat()
                    except ValueError:
                        continue
                    g = grouped.setdefault(event_sn, {"title": title, "dates": set()})
                    g["dates"].add(iso)
                    if len(title) > len(g["title"]):
                        g["title"] = title  # 더 설명적인(긴) 제목을 쓴다

        events: list[Event] = []
        for info in grouped.values():
            dates = sorted(info["dates"])
            start = dates[0]
            end = dates[-1] if len(dates) > 1 else None
            title = info["title"]
            events.append(Event(
                title=title,
                category="MONETARY",
                agency=self.agency,
                date=start,
                end_date=end,
                importance=3 if any(k in title for k in HIGH_IMPORTANCE) else 2,
                status="CONFIRMED",
                source_id=self.id,
                source_url=f"{LIST_URL}?menuNo={MENU_NO}&date={start[:7]}",
            ))
        return events

    @staticmethod
    def _page_year_month(soup: BeautifulSoup) -> tuple[int | None, int | None]:
        """페이지가 실제로 렌더한 연/월을 <span id="yymm"> 에서 읽는다."""
        el = soup.select_one("#yymm")
        if not el:
            return None, None
        strongs = [s.get_text(strip=True) for s in el.select("strong")]
        if len(strongs) < 2:
            return None, None
        try:
            return int(strongs[0]), int(strongs[1])
        except ValueError:
            return None, None
