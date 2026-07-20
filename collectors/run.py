"""수집 실행 진입점.

사용:
  python -m collectors.run                    # 전체 소스 수집
  python -m collectors.run --only bok         # 특정 소스만
  python -m collectors.run --only bok --dry-run  # 저장하지 않고 결과만 출력
  python -m collectors.run --list             # 등록된 소스 목록
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

from .base import Event
from .dates import now_kst_iso
from .pipeline import EVENTS_FILE, load_json, merge, write_outputs
from .registry import ADAPTERS, BY_ID

RETRIES = 3
BACKOFF_SECONDS = 4


def collect_with_retry(adapter) -> list[Event]:
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            return adapter.collect()
        except Exception as exc:  # noqa: BLE001 - 소스별로 격리해야 한다
            last_error = exc
            if attempt < RETRIES:
                time.sleep(BACKOFF_SECONDS * attempt)
    raise last_error  # type: ignore[misc]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="정책·경제 이벤트 수집기")
    parser.add_argument("--only", nargs="*", help="수집할 소스 ID (기본: 전체)")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    parser.add_argument("--list", action="store_true", help="등록된 소스 목록 출력")
    args = parser.parse_args(argv)

    if args.list:
        for a in ADAPTERS:
            flag = "선택" if a.optional else "필수"
            print(f"  {a.id:<10} {a.name:<20} {a.agency:<12} [{flag}]")
        return 0

    targets = ADAPTERS
    if args.only:
        unknown = [s for s in args.only if s not in BY_ID]
        if unknown:
            print(f"알 수 없는 소스: {', '.join(unknown)}", file=sys.stderr)
            return 2
        targets = [BY_ID[s] for s in args.only]

    started = now_kst_iso()
    collected: list[Event] = []
    results: list[dict] = []
    touched: set[str] = set()
    hard_failures = 0

    for adapter in targets:
        t0 = time.monotonic()
        try:
            events = collect_with_retry(adapter)
            collected.extend(events)
            touched.add(adapter.id)
            results.append({
                "source": adapter.id, "status": "OK",
                "fetched": len(events), "seconds": round(time.monotonic() - t0, 1),
            })
            print(f"[OK]   {adapter.id:<10} {len(events)}건")
        except Exception as exc:  # noqa: BLE001
            level = "SKIP" if adapter.optional else "FAIL"
            if not adapter.optional:
                hard_failures += 1
            results.append({
                "source": adapter.id, "status": level,
                "fetched": 0, "error": str(exc)[:300],
                "seconds": round(time.monotonic() - t0, 1),
            })
            print(f"[{level}] {adapter.id:<10} {exc}", file=sys.stderr)
            if level == "FAIL":
                traceback.print_exc()

    if args.dry_run:
        print(json.dumps([e.to_dict() for e in collected], ensure_ascii=False, indent=2))
        return 0

    existing = load_json(EVENTS_FILE, {"events": []})["events"]
    merged, changes = merge(existing, collected, touched)

    counts = {"NEW": 0, "RESCHEDULED": 0, "UPDATED": 0, "CANCELLED": 0}
    for c in changes:
        counts[c["type"]] = counts.get(c["type"], 0) + 1

    write_outputs(merged, changes, {
        "started_at": started,
        "finished_at": now_kst_iso(),
        "sources": results,
        "total_events": len(merged),
        "changes": counts,
    })

    print(
        f"\n총 {len(merged)}건 저장 · "
        f"신규 {counts['NEW']} / 일정변경 {counts['RESCHEDULED']} / "
        f"수정 {counts['UPDATED']} / 취소 {counts['CANCELLED']}"
    )
    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
