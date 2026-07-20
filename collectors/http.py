"""HTTP 공통 유틸.

원칙:
  - 공식 OpenAPI 가 있으면 무조건 그쪽을 쓴다. HTML 파싱은 최후 수단.
  - User-Agent 에 프로젝트 정체와 연락처를 밝힌다.
  - 요청 사이에 간격을 둔다. 하루 두 번 도는 수집기에 속도는 중요하지 않다.
  - robots.txt 를 확인하고, 막힌 경로는 긁지 않는다.
"""
from __future__ import annotations

import os
import time
import urllib.robotparser
from functools import lru_cache
from urllib.parse import urlsplit

import requests

CONTACT = os.environ.get("COLLECTOR_CONTACT", "https://github.com/<owner>/<repo>")
USER_AGENT = f"kr-policy-calendar/0.1 (personal schedule aggregator; {CONTACT})"

TIMEOUT = 15
DELAY_SECONDS = 1.5

_session: requests.Session | None = None
_last_request_at = 0.0


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
    return _session


@lru_cache(maxsize=32)
def _robots(origin: str) -> urllib.robotparser.RobotFileParser:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{origin}/robots.txt")
    try:
        rp.read()
    except Exception:
        rp.allow_all = True
    return rp


def allowed(url: str) -> bool:
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    try:
        return _robots(origin).can_fetch(USER_AGENT, url)
    except Exception:
        return True


def get(url: str, **kwargs) -> requests.Response:
    global _last_request_at
    if not allowed(url):
        raise PermissionError(f"robots.txt 가 이 경로 수집을 막고 있습니다: {url}")

    elapsed = time.monotonic() - _last_request_at
    if elapsed < DELAY_SECONDS:
        time.sleep(DELAY_SECONDS - elapsed)

    kwargs.setdefault("timeout", TIMEOUT)
    resp = session().get(url, **kwargs)
    _last_request_at = time.monotonic()
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    return resp
