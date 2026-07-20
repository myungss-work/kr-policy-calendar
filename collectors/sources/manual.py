"""data/manual.json 에 직접 적어 넣은 일정을 읽는다.

수집기가 못 긁는 일정, 뉴스로 먼저 알게 된 일정, 개인 일정을 여기에 넣는다.
locked=true 로 두면 다른 소스가 같은 이벤트를 가져와도 이 값이 유지된다.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..base import Event, SourceAdapter

MANUAL_FILE = Path(__file__).resolve().parents[2] / "docs" / "data" / "manual.json"


class ManualAdapter(SourceAdapter):
    id = "manual"
    name = "직접 입력"
    agency = "-"
    homepage = ""

    def fetch(self) -> list[dict]:
        if not MANUAL_FILE.exists():
            return []
        with MANUAL_FILE.open(encoding="utf-8") as f:
            return json.load(f).get("events", [])

    def parse(self, raw: list[dict]) -> list[Event]:
        events = []
        for row in raw:
            row = dict(row)
            row.setdefault("source_id", self.id)
            row.setdefault("locked", True)
            row.setdefault("agency", self.agency)
            events.append(Event(**row))
        return events
