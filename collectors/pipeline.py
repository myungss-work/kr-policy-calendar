"""수집한 이벤트를 기존 저장분과 병합하고 변경 이력을 남긴다."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Event, VOLATILE_FIELDS
from .dates import now_kst_iso

DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"
EVENTS_FILE = DATA_DIR / "events.json"
CHANGES_FILE = DATA_DIR / "changes.json"
RUNS_FILE = DATA_DIR / "runs.json"

MAX_CHANGES = 500
MAX_RUNS = 60


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def merge(
    existing: list[dict],
    incoming: list[Event],
    touched_sources: set[str],
) -> tuple[list[dict], list[dict]]:
    """기존 이벤트 목록에 새 수집분을 반영하고 (병합결과, 변경목록)을 반환.

    규칙:
      - locked=True 인 이벤트는 절대 덮어쓰지 않는다 (수동 확정 보호).
      - 이번 실행에서 건드린 소스의 이벤트만 '취소' 판정 대상으로 본다.
        (한국은행만 갱신했는데 통계청 일정이 사라지면 안 되므로)
      - 취소 판정은 삭제가 아니라 status=CANCELLED 로 남긴다.
    """
    now = now_kst_iso()
    by_key = {e["dedupe_key"]: e for e in existing}
    changes: list[dict] = []
    seen_keys: set[str] = set()

    for ev in incoming:
        rec = ev.to_dict()
        key = rec["dedupe_key"]
        seen_keys.add(key)
        old = by_key.get(key)

        if old is None:
            rec["first_seen_at"] = now
            rec["last_seen_at"] = now
            rec["updated_at"] = now
            by_key[key] = rec
            changes.append({
                "type": "NEW", "id": rec["id"], "title": rec["title"],
                "date": rec["date"], "agency": rec["agency"],
                "field": None, "before": None, "after": None, "detected_at": now,
            })
            continue

        if old.get("locked"):
            old["last_seen_at"] = now
            continue

        diffs = {
            k: (old.get(k), v)
            for k, v in rec.items()
            if k not in VOLATILE_FIELDS and k != "locked" and old.get(k) != v
        }
        old["last_seen_at"] = now
        if not diffs:
            continue

        for field_name, (before, after) in diffs.items():
            old[field_name] = after
            changes.append({
                "type": "RESCHEDULED" if field_name in ("date", "end_date", "time") else "UPDATED",
                "id": old["id"], "title": rec["title"], "date": rec["date"],
                "agency": rec["agency"], "field": field_name,
                "before": before, "after": after, "detected_at": now,
            })
        old["updated_at"] = now

    # 이번에 수집한 소스에 있었는데 사라진 이벤트 -> 취소 처리
    for key, rec in by_key.items():
        if key in seen_keys or rec.get("locked"):
            continue
        if rec.get("source_id") not in touched_sources:
            continue
        if rec.get("status") == "CANCELLED":
            continue
        rec["status"] = "CANCELLED"
        rec["updated_at"] = now
        changes.append({
            "type": "CANCELLED", "id": rec["id"], "title": rec["title"],
            "date": rec["date"], "agency": rec["agency"], "field": "status",
            "before": "CONFIRMED", "after": "CANCELLED", "detected_at": now,
        })

    merged = sorted(by_key.values(), key=lambda e: (e["date"], -e["importance"], e["title"]))
    return merged, changes


def write_outputs(merged: list[dict], changes: list[dict], run: dict) -> None:
    save_json(EVENTS_FILE, {
        "generated_at": now_kst_iso(),
        "count": len(merged),
        "events": merged,
    })

    history = load_json(CHANGES_FILE, {"changes": []})["changes"]
    save_json(CHANGES_FILE, {"changes": (changes + history)[:MAX_CHANGES]})

    runs = load_json(RUNS_FILE, {"runs": []})["runs"]
    save_json(RUNS_FILE, {"runs": ([run] + runs)[:MAX_RUNS]})
