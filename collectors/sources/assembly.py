"""국회 의사일정 (열린국회정보 OpenAPI).

인증키가 필요합니다. https://open.assembly.go.kr 에서 발급한 뒤
GitHub 저장소 Settings > Secrets and variables > Actions 에
ASSEMBLY_API_KEY 로 등록하세요. 키가 없으면 이 소스는 조용히 건너뜁니다.

⚠️ 미검증 어댑터입니다. SERVICE_ID 와 응답 필드명은 실제 호출로 확인하세요.
    OpenAPI 목록에서 '의사일정' 서비스를 찾아 ID 와 필드명을 맞추면 됩니다.
"""
from __future__ import annotations

import os

from .. import http
from ..base import Event, SourceAdapter
from ..dates import parse_date, parse_time

BASE_URL = "https://open.assembly.go.kr/portal/openapi"
SERVICE_ID = "nzgjnvnraowoaudtd"  # 검증 필요
PAGE_SIZE = 300

# 응답 필드 후보 (기관 API 는 필드명이 자주 다르므로 여러 개를 시도한다)
DATE_FIELDS = ("MEETING_DATE", "MTG_DATE", "SCH_DT", "DT")
TITLE_FIELDS = ("MEETING_NM", "TITLE", "SCH_NM", "COMMITTEE_NM")
TIME_FIELDS = ("MEETING_TIME", "MTG_TIME", "SCH_TM")


class AssemblyAdapter(SourceAdapter):
    id = "assembly"
    name = "국회 의사일정"
    agency = "국회"
    homepage = "https://open.assembly.go.kr"
    optional = True

    def fetch(self) -> list[dict]:
        key = os.environ.get("ASSEMBLY_API_KEY")
        if not key:
            raise RuntimeError("ASSEMBLY_API_KEY 가 설정되지 않아 건너뜁니다.")

        params = {"KEY": key, "Type": "json", "pIndex": 1, "pSize": PAGE_SIZE}
        payload = http.get(f"{BASE_URL}/{SERVICE_ID}", params=params).json()

        # 열린국회정보 응답은 {SERVICE_ID: [{head:...}, {row: [...]}]} 형태다
        blocks = payload.get(SERVICE_ID) or []
        for block in blocks:
            if isinstance(block, dict) and "row" in block:
                return block["row"]
        return []

    def parse(self, raw: list[dict]) -> list[Event]:
        events: list[Event] = []
        for row in raw:
            day = self._first(row, DATE_FIELDS, parse_date)
            title = self._first(row, TITLE_FIELDS)
            if not day or not title:
                continue
            events.append(Event(
                title=title,
                category="ASSEMBLY",
                agency=self.agency,
                date=day,
                time=self._first(row, TIME_FIELDS, parse_time),
                importance=3 if "본회의" in title or "국정감사" in title else 1,
                day_level_identity=True,  # 같은 달에 같은 이름 회의가 여러 번 있다
                status="CONFIRMED",
                source_id=self.id,
                source_url=self.homepage,
            ))
        return events

    @staticmethod
    def _first(row: dict, fields: tuple[str, ...], transform=None):
        for f in fields:
            value = row.get(f)
            if value:
                return transform(str(value)) if transform else str(value).strip()
        return None
