"""공휴일 (공공데이터포털 특일 정보 API).

data.go.kr 에서 '특일 정보' 활용신청 후 받은 키를 DATA_GO_KR_KEY 로 등록하세요.
키가 없으면 건너뜁니다. 공휴일은 달력 배경 표시와 영업일 계산에 쓰입니다.
"""
from __future__ import annotations

import os
from datetime import date

from .. import http
from ..base import Event, SourceAdapter

ENDPOINT = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"


class HolidayAdapter(SourceAdapter):
    id = "holiday"
    name = "공휴일"
    agency = "한국천문연구원"
    homepage = "https://www.data.go.kr"
    optional = True

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
            body = http.get(ENDPOINT, params=params).json()
            items = (
                body.get("response", {}).get("body", {})
                .get("items", {}) or {}
            ).get("item", [])
            if isinstance(items, dict):
                items = [items]
            rows.extend(items)
        return rows

    def parse(self, raw: list[dict]) -> list[Event]:
        events: list[Event] = []
        for row in raw:
            locdate = str(row.get("locdate", ""))
            if len(locdate) != 8:
                continue
            events.append(Event(
                title=str(row.get("dateName", "공휴일")).strip(),
                category="MARKET",
                agency=self.agency,
                date=f"{locdate[:4]}-{locdate[4:6]}-{locdate[6:]}",
                importance=1,
                status="CONFIRMED",
                description="공휴일 (증시 휴장)",
                source_id=self.id,
                tags=["공휴일"],
            ))
        return events
