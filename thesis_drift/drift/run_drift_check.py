"""Deterministic drift pipeline with one LLM call for evidence interpretation."""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thesis_drift import llm_client
from thesis_drift.config import db_path
from thesis_drift.db.setup_db import connect, setup_database
from thesis_drift.edgar import extract, fetch_filing

DRIFT_SYSTEM_PROMPT = """You evaluate whether an ORIGINAL INVESTMENT THESIS still holds.
This is NOT a request to summarize what changed at the company. Evaluate ONLY the
specific assumptions and target metrics of THIS thesis using ONLY the retrieved
filing evidence. Your output must help a committee decide whether to keep or
re-evaluate the position. Ignore evidence you were not given.

Use this fixed score/status band mapping:
7-10 CONFIRMED: thesis holds, no action needed.
4-6.99 WEAKENED: a monitored assumption is softening, watch it.
2-4 CHALLENGED: a key assumption or metric has reversed, flag for review.
1-2 INVALIDATED: the original reason to hold has broken, recommend re-evaluating.

Return EXACTLY this format and no other text:
DRIFT_SCORE: <number from 1.0 to 10.0, decimals allowed>
STATUS: <CONFIRMED|WEAKENED|CHALLENGED|INVALIDATED>
DRIFT_SUMMARY: <reference the specific assumptions/metrics that changed and why;
end with an explicit keep-or-re-evaluate recommendation for UCIMCO>"""

DRIFT_USER_PROMPT_TEMPLATE = """Ticker: {ticker}
Original thesis summary: {thesis_summary}
Original key assumptions:
{key_assumptions}
Original target metrics:
{target_metrics}
Original conviction level: {conviction_level} / 5

New SEC filing: {form} filed {filing_date}, accession {accession_number}

Retrieved evidence from that filing (labeled by the thesis item it was retrieved for):
---
{evidence}
---

Assess whether each specific assumption and target metric still holds, using only
the evidence above, and apply the fixed score/status bands from the system prompt."""

MOCK_DRIFT_RESPONSE = """DRIFT_SCORE: 6.5
STATUS: WEAKENED
DRIFT_SUMMARY: MOCK DRY-RUN placeholder (not a real filing assessment): the retrieved evidence was not interpreted by an LLM. Assumption 1 and metric 1 need human review; UCIMCO should keep watching the position until a real check is run."""

ALLOWED_STATUSES = {"CONFIRMED", "WEAKENED", "CHALLENGED", "INVALIDATED"}


def parse_drift_response(text: str) -> dict:
    """Parse and validate the fixed LLM response format."""
    score_match = re.search(r"^\s*DRIFT_SCORE:\s*([0-9]+(?:\.[0-9]+)?)\s*$", text, re.M)
    status_match = re.search(r"^\s*STATUS:\s*([A-Z]+)\s*$", text, re.M)
    summary_match = re.search(r"^\s*DRIFT_SUMMARY:\s*(.+?)\s*$", text, re.M)
    if not (score_match and status_match and summary_match):
        raise ValueError("LLM drift response missing DRIFT_SCORE, STATUS, or DRIFT_SUMMARY")
    score = float(score_match.group(1))
    status = status_match.group(1)
    if not 1.0 <= score <= 10.0:
        raise ValueError(f"Drift score out of range: {score}")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid drift status: {status}")
    return {"drift_score": score, "status": status, "drift_summary": summary_match.group(1)}


def _thesis_items(thesis) -> list[tuple[str, str]]:
    items = []
    for field, label in (("key_assumptions", "Assumption"), ("target_metrics", "Metric")):
        number = 0
        for line in (thesis[field] or "").splitlines():
            item = line.strip().lstrip("-* ").strip()
            if item:
                number += 1
                items.append((f"{label} {number}: {item}", item))
    return items


def check_drift(ticker: str, path: Path | str | None = None, dry_run: bool | None = None) -> dict:
    """Check one holding for a newer filing and write a Drift_Events row if needed."""
    target = Path(path or db_path())
    setup_database(target)
    mock = llm_client.is_configured() is False if dry_run is None else dry_run
    if mock:
        print("WARNING: DRY RUN / MOCK LLM — drift result is a placeholder, NOT a real assessment.")

    conn = connect(target)
    try:
        stock = conn.execute(
            "SELECT stock_id, ticker FROM Stocks WHERE ticker = ?", (ticker.strip().upper(),)
        ).fetchone()
        if stock is None:
            raise LookupError(f"No holding for ticker {ticker!r} in the portfolio")
        thesis = conn.execute(
            "SELECT * FROM Thesis WHERE stock_id = ? AND is_original = 1 "
            "ORDER BY thesis_id DESC LIMIT 1",
            (stock["stock_id"],),
        ).fetchone()
        if thesis is None:
            raise LookupError(
                f"No original thesis for {ticker}; run thesis_drift/thesis/draft_theses.py first"
            )

        previous = conn.execute(
            "SELECT source_accession_number FROM Drift_Events WHERE stock_id = ? "
            "ORDER BY event_date DESC, drift_event_id DESC LIMIT 1",
            (stock["stock_id"],),
        ).fetchone()
        reference = (
            previous["source_accession_number"]
            if previous is not None
            else thesis["source_accession_number"]
        )
        if not reference:
            raise LookupError(f"No source accession recorded for {ticker}'s thesis")

        newer = fetch_filing.get_filing_newer_than(stock["ticker"], reference)
        if newer is None:
            return {
                "ticker": stock["ticker"],
                "stock_id": stock["stock_id"],
                "thesis_id": thesis["thesis_id"],
                "drift_event_id": None,
                "reference_accession": reference,
                "result": "NO_NEW_FILING",
                "message": (
                    f"No new filing since last check for {stock['ticker']} "
                    f"(after {reference}); nothing to do."
                ),
            }

        raw_document = fetch_filing.download_filing_document(newer)
        document_id = extract.ingest_filing(stock["stock_id"], newer, raw_document, path=target)
        evidence_blocks = []
        for label, item in _thesis_items(thesis):
            chunks = extract.retrieve_chunks(
                item, stock["stock_id"], document_id, k=3, path=target
            )
            evidence_blocks.append(f"{label}\n" + "\n".join(chunks))
        evidence = "\n\n".join(evidence_blocks) or "No relevant evidence was retrieved."
        user_prompt = DRIFT_USER_PROMPT_TEMPLATE.format(
            ticker=stock["ticker"],
            thesis_summary=thesis["thesis_summary"],
            key_assumptions=thesis["key_assumptions"],
            target_metrics=thesis["target_metrics"],
            conviction_level=thesis["conviction_level"],
            form=newer["form"],
            filing_date=newer["filing_date"],
            accession_number=newer["accession_number"],
            evidence=evidence,
        )
        response = MOCK_DRIFT_RESPONSE if mock else llm_client.call_llm(
            DRIFT_SYSTEM_PROMPT, user_prompt
        )
        fields = parse_drift_response(response)
        with conn:
            cursor = conn.execute(
                "INSERT INTO Drift_Events (stock_id, thesis_id, event_date, "
                "source_accession_number, drift_score, drift_summary, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    stock["stock_id"],
                    thesis["thesis_id"],
                    date.today().isoformat(),
                    newer["accession_number"],
                    fields["drift_score"],
                    fields["drift_summary"],
                    fields["status"],
                ),
            )
            drift_event_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM Drift_Events WHERE drift_event_id = ?", (drift_event_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def check_drift_all(path: Path | str | None = None) -> list[dict]:
    """Run check_drift for every holding (intended for scheduled jobs)."""
    target = Path(path or db_path())
    setup_database(target)
    conn = connect(target)
    try:
        tickers = [row["ticker"] for row in conn.execute("SELECT ticker FROM Stocks ORDER BY ticker")]
    finally:
        conn.close()
    results = []
    for ticker in tickers:
        try:
            results.append(check_drift(ticker, path=target))
        except Exception as exc:
            results.append({"ticker": ticker, "result": "ERROR", "message": str(exc)})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Check thesis drift for holdings")
    parser.add_argument("ticker", nargs="*", help="ticker(s); default is all holdings")
    parser.add_argument("--db", help="database path (overrides UCIMCO_DB_PATH)")
    parser.add_argument("--dry-run", action="store_true", help="force mock LLM responses")
    args = parser.parse_args()
    dry_run = True if args.dry_run else None
    if args.ticker:
        for ticker in args.ticker:
            print(check_drift(ticker, args.db or db_path(), dry_run=dry_run))
    else:
        for result in check_drift_all(args.db or db_path()):
            print(result)


if __name__ == "__main__":
    main()
