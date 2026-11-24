"""Ticker -> 10-digit CIK lookup, cached from SEC's company_tickers.json."""

import json
from pathlib import Path

from thesis_drift.config import EDGAR_CACHE_DIR
from thesis_drift.edgar.http import get_json

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE_PATH = Path(EDGAR_CACHE_DIR) / "company_tickers.json"


def _download_mapping() -> dict[str, str]:
    payload = get_json(TICKERS_URL)
    return {
        str(entry["ticker"]).upper(): str(entry["cik_str"]).zfill(10)
        for entry in payload.values()
    }


def refresh_cache() -> dict[str, str]:
    """Force a fresh download of the SEC ticker/CIK mapping."""
    mapping = _download_mapping()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(mapping), encoding="utf-8")
    return mapping


def _load_mapping() -> dict[str, str]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return refresh_cache()


def get_cik(ticker: str) -> str:
    """Return the 10-digit zero-padded CIK for a ticker (case-insensitive)."""
    symbol = ticker.strip().upper()
    mapping = _load_mapping()
    if symbol not in mapping:
        raise ValueError(
            f"Unknown SEC ticker {ticker!r}; refresh the ticker cache with "
            "thesis_drift.edgar.ticker_cik.refresh_cache() if it is newly listed"
        )
    return mapping[symbol]
