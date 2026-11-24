"""SEC EDGAR HTTP helpers with a declared User-Agent and 10 req/sec throttle."""

import threading
import time

import requests

from thesis_drift.config import (
    MIN_REQUEST_INTERVAL,
    USER_AGENT,
)

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    }
)
_lock = threading.Lock()
_last_request = 0.0


def _throttle() -> None:
    global _last_request
    with _lock:
        wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _get(url: str) -> requests.Response:
    """GET with fair-access throttling and limited retries on SEC HTTP errors."""
    for attempt in range(3):
        _throttle()
        response = _SESSION.get(url, timeout=30)
        if response.status_code not in (429, 500, 502, 503, 504):
            response.raise_for_status()
            return response
        if attempt == 2:
            response.raise_for_status()
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def get_json(url: str):
    return _get(url).json()


def get_text(url: str) -> str:
    return _get(url).text
