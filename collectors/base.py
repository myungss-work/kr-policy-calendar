"""소스 어댑터 공통 인터페이스와 Event 스키마."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Iterable

CATEGORIES = {
    "MONETARY": "통화정책",
    "INDICATOR": "경제지표",
    "REALESTATE": "부동산",
    "FISCAL": "재정·예산",
    "ASSEMBLY": "국회",
    "FINANCE": "금융·감독",
    "MARKET": "시장일정",
    "GLOBAL": "해외",
    "CUSTOM": "직접입력",
}

STATUSES = {"CONFIRMED", "TENTATIVE", "CANCELLED"}


@dataclass
class Event:
    title: str
    category: str
    agency: str
    date: str                      # YYYY-MM-DD
    source_id: str
    end_date: str | None = None
    time: str | None = None        # "HH:MM", 없으면 종일
    importance: int = 2            # 1~3
    status: str = "CONFIRMED"
    description: str = ""
    source_url: str = ""
    tags: list[str] = field(default_factory=list)
    locked: bool = False           # True면 자동 수집이 덮어쓰지 않음
    id: str = ""
    dedupe_key: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"알 수 없는 카테고리: {self.category}")
        if self.status not in STATUSES:
            raise ValueError(f"알 수 없는 상태: {self.status}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.date):
            raise ValueError(f"날짜 형식 오류: {self.date}")
        self.importance = max(1, min(3, int(self.importance)))
        if not self.dedupe_key:
            self.dedupe_key = self.make_dedupe_key()
        if not self.id:
            self.id = hashlib.sha1(self.dedupe_key.encode()).hexdigest()[:16]

    # 하위 클래스/어댑터가 True 로 두면 키에 날짜(일)까지 포함한다.
    # 같은 달에 같은 이름의 회의가 여러 번 열리는 소스(국회 본회의 등)에 필요.
    day_level_identity: bool = False

    def make_dedupe_key(self) -> str:
        """같은 이벤트로 볼 기준.

        기본은 '연-월' 단위로 묶는다. 그래야 발표일이 8/27 -> 8/28 로 밀렸을 때
        '신규 + 취소' 가 아니라 '일정변경(RESCHEDULED)' 으로 잡힌다.
        띄어쓰기·괄호 같은 표기 흔들림은 흡수하되, 회차를 구분하는
        '8월' 같은 표기는 남겨둔다.
        """
        norm = re.sub(r"[\s()\[\]<>·,.\-–—'\"]", "", self.title)
        scope = self.date if self.day_level_identity else self.date[:7]
        return f"{self.source_id}|{self.category}|{norm}|{scope}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# diff 대상에서 제외할 필드 (매 실행마다 바뀌는 메타데이터)
VOLATILE_FIELDS = {"first_seen_at", "last_seen_at", "updated_at", "id", "dedupe_key"}


class SourceAdapter:
    """모든 소스 어댑터의 부모 클래스.

    새 기관을 추가하려면 이 클래스를 상속한 파일을 sources/에 만들고
    registry.py 에 등록하면 된다. 파이프라인은 건드릴 필요 없다.
    """

    id: str = ""
    name: str = ""
    agency: str = ""
    homepage: str = ""
    # 실패해도 전체 실행을 실패로 만들지 않을 소스인지
    optional: bool = False

    def fetch(self) -> Any:
        """원본 데이터를 가져온다. 네트워크 접근은 여기서만."""
        raise NotImplementedError

    def parse(self, raw: Any) -> Iterable[Event]:
        """원본을 Event 목록으로 변환한다."""
        raise NotImplementedError

    def collect(self) -> list[Event]:
        raw = self.fetch()
        events = list(self.parse(raw))
        return [e for e in events if self.in_range(e)]

    @staticmethod
    def in_range(e: Event) -> bool:
        """과거 2년 ~ 미래 2년 밖의 날짜는 파싱 오류로 간주하고 버린다."""
        y = int(e.date[:4])
        this_year = date.today().year
        return this_year - 2 <= y <= this_year + 2
