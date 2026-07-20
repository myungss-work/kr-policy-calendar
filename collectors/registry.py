"""소스 어댑터 등록소.

새 기관을 추가하려면:
  1. collectors/sources/<기관>.py 에 SourceAdapter 상속 클래스를 만든다
  2. 아래 ADAPTERS 에 추가한다
끝. 파이프라인·프론트엔드는 수정할 필요 없다.
"""
from __future__ import annotations

from .base import SourceAdapter
from .sources.assembly import AssemblyAdapter
from .sources.bok import BokAdapter
from .sources.holiday import HolidayAdapter
from .sources.manual import ManualAdapter
from .sources.rules import RuleAdapter

ADAPTERS: list[SourceAdapter] = [
    ManualAdapter(),   # 수동 입력이 항상 마지막 판정권을 갖도록 먼저 로드
    RuleAdapter(),
    BokAdapter(),
    AssemblyAdapter(),
    HolidayAdapter(),
]

BY_ID = {a.id: a for a in ADAPTERS}
