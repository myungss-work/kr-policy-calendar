"""국회 의사일정 (열린국회정보 OpenAPI, ALLSCHEDULE - 국회일정 통합 서비스).

인증키가 필요합니다. https://open.assembly.go.kr 에서 발급한 뒤
GitHub 저장소 Settings > Secrets and variables > Actions 에
ASSEMBLY_API_KEY 로 등록하세요. 키가 없으면 이 소스는 조용히 건너뜁니다.

  ※ 테스트 요령: KEY 파라미터를 아예 빼고 호출하면 sample 모드로 실제 row 가
    5~10건 내려온다. 키 없이도 parse() 를 실데이터로 검증할 수 있다.
    다만 건수가 제한되므로 운영에는 쓸 수 없다.

실측으로 확인된 것 (실제 응답으로 직접 확인):
  - SERVICE_ID="ALLSCHEDULE" 실존. 과거 값 "nzgjnvnraowoaudtd" 는 ERROR-310
    ("해당하는 서비스를 찾을 수 없습니다")이 나오는 실존하지 않는 값이었다.
    무작위 문자열과 같은 응답이 나오는 것으로 대조 검증했다. 되돌리지 말 것.
  - 성공 응답:
      {"ALLSCHEDULE":[
         {"head":[{"list_total_count":N},{"RESULT":{"CODE":"INFO-000",...}}]},
         {"row":[...]}]}
  - row 필드: SCH_KIND, SCH_CN, SCH_DT, SCH_TM, CONF_DIV, CMIT_NM,
    CONF_SESS, CONF_DGR, EV_INST_NM, EV_PLC. (이 목록 밖의 필드를 지어내지 말 것.
    과거 코드의 MEETING_DATE/MTG_DATE/TITLE/SCH_NM 등은 실재하지 않는다.)
  - SCH_DT 는 "2026-07-24" 하이픈 표기, SCH_TM 은 "14:00" 표기.
  - ⚠️ SCH_TM 에 자유텍스트가 온다. 실측값: "본회의 산회 직후".
    parse_time 이 None 을 돌려주므로 '시각 없는 종일 일정'으로 처리된다.
  - 필터: SCH_DT 는 "2026-07" 처럼 월 접두사 부분매칭이 된다(7월 382건).
    SCH_KIND 는 정확매칭. START_SCH_DT/END_SCH_DT 는 무시되는 가짜 파라미터다.
  - 필터 없이 부르면 list_total_count = 92,000 이다. 한 페이지만 긁으면
    임의의 조각을 가져오게 되므로 반드시 월 단위로 좁혀서 순회한다.
  - SCH_KIND 분포: 위원회 19,522 / 국회행사 27,891 / 본회의 1,199 /
    의장단(부의장) 29. '상임위원회', '국정감사', '공청회' 등으로 조회하면
    INFO-200(데이터 없음)이다. 즉 그런 SCH_KIND 값은 존재하지 않는다.

미확인 / 한계:
  - 국회 일정은 회기 단위로 임박해서 공개된다. 실측상 다음 달(2026-08)은
    본회의·위원회 모두 INFO-200 이었다. 이 소스로는 몇 달 앞 달력을 채울 수
    없다. 소스의 성질이지 파서 버그가 아니다.
  - 정식 키로 받는 응답이 sample 응답과 완전히 같은 구조인지는 미확인.
  - optional=True 를 정식 키로 검증하기 전까지 유지한다.
"""
from __future__ import annotations

import os
from datetime import date

from .. import http
from ..base import Event, SourceAdapter
from ..dates import parse_date, parse_time

BASE_URL = "https://open.assembly.go.kr/portal/openapi"
SERVICE_ID = "ALLSCHEDULE"  # 실존 확인됨
PAGE_SIZE = 300

# 정책 달력에 실을 일정 종류. '국회행사'(개별 의원실 주최 포럼·세미나 27,891건)와
# '의장단'은 정책 일정이 아니라 노이즈이므로 제외한다.
WANTED_KINDS = ("본회의", "위원회")

# 수집할 월 범위 (오늘 기준). 지난달까지 포함해 뒤늦게 정정된 일정을 잡고,
# 앞으로는 회기 공개 시점을 감안해 넉넉히 본다.
# 요청 수 = (MONTHS_BACK + MONTHS_AHEAD + 1) * len(WANTED_KINDS) 이고
# http.py 가 요청당 1.5초를 쉬므로 아래 값이면 14회 ≈ 21초.
MONTHS_BACK = 1
MONTHS_AHEAD = 5

DATE_FIELDS = ("SCH_DT",)
TIME_FIELDS = ("SCH_TM",)


def _months(today: date) -> list[str]:
    """'YYYY-MM' 목록을 만든다."""
    out = []
    total = today.year * 12 + (today.month - 1)
    for offset in range(-MONTHS_BACK, MONTHS_AHEAD + 1):
        n = total + offset
        out.append(f"{n // 12:04d}-{n % 12 + 1:02d}")
    return out


class AssemblyAdapter(SourceAdapter):
    id = "assembly"
    name = "국회 의사일정"
    agency = "국회"
    homepage = "https://open.assembly.go.kr"
    optional = True  # 정식 키로 미검증. 검증 전까지 False 로 바꾸지 말 것.

    def fetch(self) -> list[dict]:
        key = os.environ.get("ASSEMBLY_API_KEY")
        if not key:
            raise RuntimeError("ASSEMBLY_API_KEY 가 설정되지 않아 건너뜁니다.")

        rows: list[dict] = []
        empty_queries = 0
        total_queries = 0

        for month in _months(date.today()):
            for kind in WANTED_KINDS:
                total_queries += 1
                got = self._fetch_page(key, month, kind)
                if not got:
                    empty_queries += 1
                rows.extend(got)

        # 모든 조회가 비었다면 정상적인 '일정 없음' 인지 파서/스펙 고장인지
        # 구분할 수 없다. 조용히 0건을 넘기면 기존 국회 일정이 전부
        # CANCELLED 로 잡히므로, 예외로 드러내 SKIP 되게 한다(optional=True).
        if empty_queries == total_queries:
            raise RuntimeError(
                f"국회 일정 조회 {total_queries}건이 모두 비었습니다. "
                "스펙 변경이나 파서 고장일 수 있어 기존 데이터를 보존합니다."
            )
        return rows

    def _fetch_page(self, key: str, month: str, kind: str) -> list[dict]:
        """한 달 + 한 종류를 가져온다. 데이터가 없으면 빈 리스트."""
        collected: list[dict] = []
        page = 1
        while True:
            params = {
                "KEY": key, "Type": "json", "pIndex": page, "pSize": PAGE_SIZE,
                "SCH_DT": month, "SCH_KIND": kind,
            }
            payload = http.get(f"{BASE_URL}/{SERVICE_ID}", params=params).json()

            # 데이터가 없으면 최상위에 RESULT 가 온다 (실측).
            #   INFO-200 = 해당하는 데이터가 없습니다  -> 정상적인 빈 결과
            #   ERROR-*  = 키 무효/필수값 누락/서비스 없음 -> 예외
            result = payload.get("RESULT")
            if isinstance(result, dict):
                code = str(result.get("CODE", ""))
                if code.startswith("INFO-2"):
                    return collected
                raise RuntimeError(
                    f"열린국회정보 API 오류 (SERVICE_ID={SERVICE_ID}, "
                    f"{month}/{kind}, CODE={code!r}): {result.get('MESSAGE')!r}"
                )

            blocks = payload.get(SERVICE_ID)
            if not isinstance(blocks, list):
                raise RuntimeError(
                    f"예상치 못한 응답 구조입니다 ({SERVICE_ID!r} 키 없음). "
                    f"raw={str(payload)[:300]!r}"
                )

            head_code, total = self._read_head(blocks)
            if head_code is not None and head_code != "INFO-000":
                raise RuntimeError(
                    f"열린국회정보 API 오류 ({month}/{kind}, "
                    f"head CODE={head_code!r})"
                )

            rows = self._read_rows(blocks)
            collected.extend(rows)

            if not rows or total is None or len(collected) >= total:
                return collected
            page += 1

    @staticmethod
    def _read_head(blocks: list) -> tuple[str | None, int | None]:
        """head 에서 결과코드와 전체 건수를 뽑는다. 없으면 (None, None)."""
        code = None
        total = None
        for block in blocks:
            if not (isinstance(block, dict) and "head" in block):
                continue
            for entry in block["head"]:
                if not isinstance(entry, dict):
                    continue
                if "list_total_count" in entry:
                    total = entry["list_total_count"]
                result = entry.get("RESULT")
                if isinstance(result, dict):
                    code = result.get("CODE")
        return code, total

    @staticmethod
    def _read_rows(blocks: list) -> list[dict]:
        for block in blocks:
            if isinstance(block, dict) and "row" in block:
                return block["row"] or []
        return []

    def parse(self, raw: list[dict]) -> list[Event]:
        events: list[Event] = []
        for row in raw:
            day = self._first(row, DATE_FIELDS, parse_date)
            title = self._title(row)
            if not day or not title:
                continue

            place = (row.get("EV_PLC") or "").strip()
            session = (row.get("CONF_SESS") or "").strip()
            description = " · ".join(p for p in (session, place) if p)

            events.append(Event(
                title=title,
                category="ASSEMBLY",
                agency=self.agency,
                date=day,
                time=self._first(row, TIME_FIELDS, parse_time),
                importance=3 if row.get("SCH_KIND") == "본회의" else 2,
                day_level_identity=True,  # 같은 달에 같은 이름 회의가 여러 번 있다
                status="CONFIRMED",
                description=description,
                source_id=self.id,
                source_url=self.homepage,
            ))
        return events

    @staticmethod
    def _title(row: dict) -> str:
        """사람이 읽을 수 있는 제목을 만든다.

        SCH_CN 만 쓰면 위원회 회의 제목이 '제437회국회(임시회) 제2차 전체회의'
        가 되어 어느 위원회인지 사라진다. dedupe_key 가 제목 기반이라
        같은 날 열린 다른 위원회 회의끼리 키가 충돌해 하나로 뭉개진다.
        그래서 위원회명(CMIT_NM)을 반드시 제목에 넣는다.
        """
        body = (row.get("SCH_CN") or "").strip()
        prefix = (row.get("CMIT_NM") or row.get("SCH_KIND") or "").strip()
        if not body:
            return prefix
        if prefix and prefix not in body:
            return f"{prefix} {body}"
        return body

    @staticmethod
    def _first(row: dict, fields: tuple[str, ...], transform=None):
        for f in fields:
            value = row.get(f)
            if value:
                return transform(str(value)) if transform else str(value).strip()
        return None
