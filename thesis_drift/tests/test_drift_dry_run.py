"""Offline end-to-end dry run: canned EDGAR filing text, mock LLM, real DB/vectors."""

import pytest

from thesis_drift.db.setup_db import connect
from thesis_drift.drift.run_drift_check import ALLOWED_STATUSES, check_drift
from thesis_drift.edgar import fetch_filing
from thesis_drift.thesis.draft_theses import draft_theses

CANNED_HTML = "<html><body><p>" + " ".join(
    ["revenue growth remains strong and operating margin is stable"] * 90
) + "</p></body></html>"


def _filing(accession: str, filing_date: str) -> dict:
    return {
        "accession_number": accession,
        "form": "10-Q",
        "filing_date": filing_date,
        "report_date": "2026-01-31",
        "primary_document": "aapl-20260131.htm",
        "primary_document_url": "https://www.sec.gov/Archives/edgar/data/320193/example.htm",
        "cik": "0000320193",
    }


@pytest.fixture
def one_holding(db_path, monkeypatch):
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO Stocks (ticker, company_name) VALUES ('AAPL', 'Apple Inc.')"
            )
            stock_id = conn.execute(
                "SELECT stock_id FROM Stocks WHERE ticker = 'AAPL'"
            ).fetchone()["stock_id"]
            conn.execute(
                "INSERT INTO Transactions (stock_id, transaction_type, transaction_date, "
                "shares, price_per_share) VALUES (?, 'BUY', '2026-05-07', 10, 185.20)",
                (stock_id,),
            )
    finally:
        conn.close()
    monkeypatch.setattr(fetch_filing, "get_latest_filing", lambda ticker: _filing(
        "0000320193-26-000001", "2026-02-01"
    ))
    monkeypatch.setattr(fetch_filing, "download_filing_document", lambda filing: CANNED_HTML)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    return db_path


def test_draft_and_drift_dry_run_end_to_end(one_holding, monkeypatch):
    drafted = draft_theses(one_holding, dry_run=True)
    assert len(drafted) == 1
    assert drafted[0]["ticker"] == "AAPL"
    assert drafted[0]["key_assumptions"]

    monkeypatch.setattr(fetch_filing, "get_filing_newer_than", lambda ticker, after: _filing(
        "0000320193-26-000002", "2026-06-01"
    ))
    result = check_drift("AAPL", one_holding, dry_run=True)
    assert result["drift_event_id"] is not None
    assert 1.0 <= result["drift_score"] <= 10.0
    assert result["status"] in ALLOWED_STATUSES
    assert "MOCK" in result["drift_summary"]

    monkeypatch.setattr(fetch_filing, "get_filing_newer_than", lambda ticker, after: None)
    no_new = check_drift("AAPL", one_holding, dry_run=True)
    assert no_new["result"] == "NO_NEW_FILING"
    assert "No new filing" in no_new["message"]

    conn = connect(one_holding)
    try:
        assert conn.execute("SELECT COUNT(*) FROM Drift_Events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM Document_Chunks").fetchone()[0] >= 2
    finally:
        conn.close()
