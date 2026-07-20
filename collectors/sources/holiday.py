"""공휴일 (공공데이터포털 특일 정보 API).

data.go.kr 에서 '특일 정보' 활용신청 후 받은 키를 DATA_GO_KR_KEY 로 등록하세요.
키가 없으면 건너뜁니다. 공휴일은 달력 배경 표시와 영업일 계산에 쓰입니다.

⚠️ 키 등록 시 주의: data.go.kr 은 Encoding 키와 Decoding 키를 각각 발급합니다.
    이 모듈은 requests 의 params= 로 서비스키를 넘기므로 requests 가 자체적으로
    URL 인코딩을 합니다. 여기에 Encoding 키를 넣으면 이중 인코딩이 되어 인증에
    실패합니다. 반드시 **Decoding 키**를 DATA_GO_KR_KEY 로 등록하세요.

⚠️ 오퍼레이션 선택: getRestDeInfo 를 쓴다 (getHoliDeInfo 로 바꾸지 말 것).
    getHoliDeInfo 는 국경일(제헌절 포함, 실제 휴무 아님) 5개만 반환해 목적과
    다르다. getRestDeInfo 가 법정공휴일 + 대체공휴일 + 임시공휴일을 포함한
    '실제 쉬는 날' 목록을 준다.

⚠️ 임시공휴일 반영 지연 (미확인, 추정): 정부가 갑작스럽게 발표하는 임시공휴일은
    이 API 에 반영되기까지 시간이 걸릴 수 있다. 확정되는 즉시
    docs/data/manual.json 에 사람이 선반영해 두는 것이 안전하다.

⚠️ 실호출 미검증: DATA_GO_KR_KEY 가 없는 환경에서 코드 리뷰만으로 수리했다.
    실제 API 응답으로 아래 방어 로직(resultCode, JSON/XML 폴백, isHoliday)을
    확인하기 전까지 optional=True 를 유지한다.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import date

import requests

from .. import http
from ..base import Event, SourceAdapter

ENDPOINT = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"


class HolidayAdapter(SourceAdapter):
    id = "holiday"
    name = "공휴일"
    agency = "한국천문연구원"
    homepage = "https://www.data.go.kr"
    optional = True  # 실호출 미검증. 검증 전까지 절대 False 로 바꾸지 말 것.

    def fetch(self) -> list[dict]:
        key = os.environ.get("DATA_GO_KR_KEY")
        if not key:
            raise RuntimeError("DATA_GO_KR_KEY 가 설정되지 않아 건너뜁니다.")

        rows: list[dict] = []
        this_year = date.today().year
        for year in (this_year, this_year + 1):
            params = {
                "serviceKey": key, "solYear": year,
                "numOfRows": 100, "_type": "json",
            }
            resp = http.get(ENDPOINT, params=params)
            body = self._parse_body(resp)

            header = body.get("response", {}).get("header") or {}
            code = header.get("resultCode")
            if code != "00":
                msg = header.get("resultMsg", "resultMsg 없음")
                preview = resp.text[:300].replace("\n", " ")
                raise RuntimeError(
                    "공공데이터포털 특일정보 API 오류 "
                    f"(solYear={year}, resultCode={code!r}, resultMsg={msg!r}): "
                    f"raw={preview!r}"
                )

            items = (
                body.get("response", {}).get("body", {})
                .get("items", {}) or {}
            ).get("item", [])
            if isinstance(items, dict):
                items = [items]
            rows.extend(items)

        # resultCode 가 "00" 이어도 item 이 비어 오는 경우가 있다(스펙 변경,
        # 응답 구조 변경 등). 그대로 0건을 넘기면 pipeline.merge 가 기존
        # 공휴일을 전부 CANCELLED 로 바꾼다. 2개년을 조회했는데 공휴일이
        # 한 건도 없는 것은 정상일 수 없으므로 예외로 드러낸다.
        # optional=True 라 SKIP 되어 기존 데이터가 보존된다.
        if not rows:
            raise RuntimeError(
                f"{this_year}~{this_year + 1}년 공휴일이 한 건도 조회되지 "
                "않았습니다. 응답 구조가 바뀌었을 수 있어 기존 데이터를 "
                "보존합니다."
            )
        return rows

    @staticmethod
    def _parse_body(resp: requests.Response) -> dict:
        """_type=json 을 요청하지만, 문서상 공식 제공형식은 XML이라
        플랫폼이 JSON 을 무시하고 XML 을 돌려줄 수 있다. JSON 파싱이 실패하면
        XML 로 한 번 더 시도하고, 둘 다 실패하면 원인 파악용 메시지를 낸다.
        """
        try:
            return resp.json()
        except ValueError:
            pass

        try:
            return HolidayAdapter._parse_xml(resp.text)
        except ET.ParseError as exc:
            preview = resp.text[:300].replace("\n", " ")
            raise RuntimeError(
                "특일정보 API 응답을 JSON/XML 어느 쪽으로도 해석하지 못했습니다. "
                f"content-type={resp.headers.get('Content-Type')!r} "
                f"body[:300]={preview!r}"
            ) from exc

    @staticmethod
    def _parse_xml(text: str) -> dict:
        """<response><header>...</header><body><items><item>...</item>...
        </items></body></response> 형태를 JSON 응답과 같은 모양의 dict 로 바꾼다.
        header/body 가 없는 예상 밖 에러 포맷이면 빈 값으로 채워 상위에서
        resultCode 검증이 실패로 처리되게 한다."""
        root = ET.fromstring(text)

        header: dict[str, str | None] = {}
        header_el = root.find("header")
        if header_el is not None:
            for child in header_el:
                header[child.tag] = child.text

        items: list[dict] = []
        body_el = root.find("body")
        if body_el is not None:
            items_el = body_el.find("items")
            if items_el is not None:
                for item_el in items_el.findall("item"):
                    item = {child.tag: child.text for child in item_el}
                    items.append(item)

        return {"response": {"header": header, "body": {"items": {"item": items}}}}

    def parse(self, raw: list[dict]) -> list[Event]:
        events: list[Event] = []
        for row in raw:
            locdate = str(row.get("locdate", ""))
            if len(locdate) != 8:
                continue

            # isHoliday: "Y"/"N". 값이 없으면(필드 부재) 관대하게 통과시킨다 -
            # 필드 부재로 공휴일 전체가 사라지는 사고를 막기 위해서다.
            is_holiday = row.get("isHoliday")
            if is_holiday is not None and str(is_holiday).strip().upper() == "N":
                continue

            events.append(Event(
                title=str(row.get("dateName", "공휴일")).strip(),
                category="MARKET",
                agency=self.agency,
                date=f"{locdate[:4]}-{locdate[4:6]}-{locdate[6:]}",
                # 설날·추석 연휴는 같은 dateName("설날")으로 연속 3일이 각각
                # 별도 row 로 온다. 기본 dedupe_key 는 연-월 단위라 세 건이
                # 같은 키가 되어 하루만 남고 뭉개진다(실측 확인). 공휴일은
                # 날짜 자체가 정체성이므로 일 단위로 구분한다.
                day_level_identity=True,
                importance=1,
                status="CONFIRMED",
                description="공휴일 (증시 휴장)",
                source_id=self.id,
                tags=["공휴일"],
            ))
        return events
