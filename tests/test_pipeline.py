from collectors.base import Event
from collectors.pipeline import merge


def ev(**kw):
    base = dict(title="금융통화위원회", category="MONETARY",
                agency="한국은행", date="2026-08-27", source_id="bok")
    base.update(kw)
    return Event(**base)


def test_new_then_idempotent():
    merged, changes = merge([], [ev()], {"bok"})
    assert [c["type"] for c in changes] == ["NEW"]
    merged, changes = merge(merged, [ev()], {"bok"})
    assert changes == []


def test_date_shift_is_reschedule_not_new():
    merged, _ = merge([], [ev()], {"bok"})
    merged, changes = merge(merged, [ev(date="2026-08-28")], {"bok"})
    assert len(merged) == 1
    assert changes[0]["type"] == "RESCHEDULED"


def test_locked_is_never_overwritten():
    merged, _ = merge([], [ev(locked=True, time="09:00")], {"bok"})
    merged, changes = merge(merged, [ev(locked=True, time="14:00")], {"bok"})
    assert changes == []
    assert merged[0]["time"] == "09:00"


def test_missing_event_is_cancelled_not_deleted():
    merged, _ = merge([], [ev()], {"bok"})
    merged, changes = merge(merged, [], {"bok"})
    assert len(merged) == 1
    assert merged[0]["status"] == "CANCELLED"


def test_other_source_untouched():
    merged, _ = merge([], [ev()], {"bok"})
    merged, changes = merge(merged, [], {"kostat"})
    assert changes == []
    assert merged[0]["status"] == "CONFIRMED"
