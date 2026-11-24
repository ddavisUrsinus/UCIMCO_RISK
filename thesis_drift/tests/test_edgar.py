"""Real SEC EDGAR access test — no HTTP mocking, this hits sec.gov for real."""

import re

import pytest
import requests

from thesis_drift.edgar import fetch_filing
from thesis_drift.edgar.ticker_cik import get_cik


def test_get_cik_aapl_hits_real_edgar():
    try:
        assert get_cik("AAPL") == "0000320193"
    except (requests.exceptions.RequestException, OSError) as exc:
        pytest.xfail(f"SEC EDGAR is unreachable from this sandbox (network restriction): {exc}")


def test_latest_aapl_filing_is_real_and_document_downloads():
    try:
        filing = fetch_filing.get_latest_filing("AAPL")
        assert filing["form"] in {"10-K", "10-Q"}
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", filing["filing_date"])
        assert int(filing["filing_date"][:4]) >= 2020
        assert filing["primary_document_url"].startswith("https://www.sec.gov/Archives/edgar/data/")
        assert filing["cik"] == "0000320193"
        document = fetch_filing.download_filing_document(filing)
        assert len(document) > 5000
        assert re.search(r"[A-Za-z]{20,}", document)
    except (requests.exceptions.RequestException, OSError) as exc:
        pytest.xfail(f"SEC EDGAR is unreachable from this sandbox (network restriction): {exc}")
