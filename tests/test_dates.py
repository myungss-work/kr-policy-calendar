"""날짜 정규화 회귀 테스트. 새 표기를 만날 때마다 케이스를 추가할 것."""
from collectors.dates import parse_date, parse_date_range, parse_time


def test_various_formats():
    cases = {
        "2026-08-27": "2026-08-27",
        "2026.08.27": "2026-08-27",
        "2026. 8. 27.": "2026-08-27",
        "2026년 8월 27일": "2026-08-27",
        "2026.08.27(목)": "2026-08-27",
        "2026/08/27": "2026-08-27",
    }
    for raw, want in cases.items():
        assert parse_date(raw) == want, raw


def test_year_omitted_uses_base_year():
    assert parse_date("8월 27일", base_year=2027) == "2027-08-27"


def test_invalid_date_returns_none():
    assert parse_date("2026년 2월 30일") is None
    assert parse_date("일정 미정") is None


def test_range():
    assert parse_date_range("2026.10.05 ~ 2026.10.24") == ("2026-10-05", "2026-10-24")


def test_time():
    assert parse_time("08:00 공표") == "08:00"
    assert parse_time("오후 2시 30분") == "14:30"
    assert parse_time("시각 미정") is None
