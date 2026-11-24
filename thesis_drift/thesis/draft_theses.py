"""Draft ORIGINAL thesis rows for holdings that do not have one yet."""

import argparse
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thesis_drift import llm_client
from thesis_drift.config import db_path
from thesis_drift.db.setup_db import connect, setup_database
from thesis_drift.edgar import extract, fetch_filing

DRAFT_SYSTEM_PROMPT = """You are helping a student-led investment fund record the ORIGINAL
investment thesis for a stock it already owns. Use only the SEC filing evidence supplied.
Be specific and concise. Return EXACTLY this format and no other text:

THESIS_SUMMARY: <one paragraph explaining why the fund bought this holding>
KEY_ASSUMPTIONS:
- <assumption 1>
- <assumption 2>
- <assumption 3>
TARGET_METRICS:
- <metric/threshold 1>
- <metric/threshold 2>
CONVICTION_LEVEL: <integer from 1 to 5>

Provide 3-5 key assumptions and 2-3 target metrics. Do not claim certainty."""

DRAFT_USER_PROMPT_TEMPLATE = """Draft an original investment thesis for {ticker} ({company_name}).
Purchase price / cost basis: {price_at_thesis}
Source SEC filing: {form} filed {filing_date}, accession {accession_number}

Filing text excerpt:
---
{filing_excerpt}
---

Write the thesis in the required fixed output format. This is a DRAFT for a human
committee to review, not an authoritative statement of the fund's reasoning."""

MOCK_DRAFT_RESPONSE = """THESIS_SUMMARY: MOCK DRY-RUN DRAFT (not authoritative): the fund bought {ticker} based on expected durable growth and cash generation; a human must replace this with the real original thesis.
KEY_ASSUMPTIONS:
- MOCK: revenue and margins remain supportive over the holding period
- MOCK: competitive position does not materially deteriorate
- MOCK: management continues to execute on the stated capital allocation plan
TARGET_METRICS:
- MOCK: revenue growth stays positive
- MOCK: operating margin remains stable
CONVICTION_LEVEL: 3"""


def parse_draft_response(text: str) -> dict:
    """Parse the fixed output format into fields stored in the Thesis table."""
    summary = ""
    assumptions: list[str] = []
    metrics: list[str] = []
    conviction = 3
    section = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("THESIS_SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
            section = None
        elif line.startswith("KEY_ASSUMPTIONS:"):
            section = "assumptions"
        elif line.startswith("TARGET_METRICS:"):
            section = "metrics"
        elif line.startswith("CONVICTION_LEVEL:"):
            value = line.split(":", 1)[1].strip()
            try:
                conviction = int(value)
            except ValueError as exc:
                raise ValueError(f"Invalid CONVICTION_LEVEL in LLM output: {value!r}") from exc
            section = None
        elif line.startswith(("- ", "* ")) and section:
            item = line[2:].strip()
            (assumptions if section == "assumptions" else metrics).append(item)
    if not summary or not assumptions or not metrics:
        raise ValueError("LLM draft response missing summary, assumptions, or metrics")
    if not 1 <= conviction <= 5:
        raise ValueError(f"Conviction level out of range: {conviction}")
    return {
        "thesis_summary": summary,
        "key_assumptions": "\n".join(f"- {item}" for item in assumptions),
        "target_metrics": "\n".join(f"- {item}" for item in metrics),
        "conviction_level": conviction,
    }


def draft_theses(path: Path | str | None = None, dry_run: bool | None = None) -> list[dict]:
    """Draft one original thesis per holding with no Thesis row; human review required."""
    target = Path(path or db_path())
    setup_database(target)
    mock = llm_client.is_configured() is False if dry_run is None else dry_run
    if mock:
        print("WARNING: DRY RUN / MOCK LLM — drafted theses are placeholders, NOT authoritative.")

    conn = connect(target)
    drafted: list[dict] = []
    try:
        pending = conn.execute(
            "SELECT s.stock_id, s.ticker, s.company_name FROM Stocks s "
            "LEFT JOIN Thesis t ON t.stock_id = s.stock_id "
            "WHERE t.thesis_id IS NULL ORDER BY s.ticker"
        ).fetchall()
        for stock in pending:
            ticker = stock["ticker"]
            filing = fetch_filing.get_latest_filing(ticker)
            raw_document = fetch_filing.download_filing_document(filing)
            document_id = extract.ingest_filing(stock["stock_id"], filing, raw_document, path=target)
            row = conn.execute(
                "SELECT extracted_text FROM Documents WHERE document_id = ?", (document_id,)
            ).fetchone()
            excerpt = (row["extracted_text"] or "")[:12000]
            price_row = conn.execute(
                "SELECT AVG(price_per_share) AS price FROM Transactions "
                "WHERE stock_id = ? AND transaction_type = 'BUY'",
                (stock["stock_id"],),
            ).fetchone()
            price = price_row["price"]
            user_prompt = DRAFT_USER_PROMPT_TEMPLATE.format(
                ticker=ticker,
                company_name=stock["company_name"],
                price_at_thesis=price,
                form=filing["form"],
                filing_date=filing["filing_date"],
                accession_number=filing["accession_number"],
                filing_excerpt=excerpt,
            )
            response = MOCK_DRAFT_RESPONSE.format(ticker=ticker) if mock else llm_client.call_llm(
                DRAFT_SYSTEM_PROMPT, user_prompt
            )
            fields = parse_draft_response(response)
            thesis_date = filing["filing_date"] or date.today().isoformat()
            with conn:
                cursor = conn.execute(
                    "INSERT INTO Thesis (stock_id, thesis_date, is_original, thesis_summary, "
                    "key_assumptions, target_metrics, conviction_level, price_at_thesis, "
                    "source_accession_number) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)",
                    (
                        stock["stock_id"],
                        thesis_date,
                        fields["thesis_summary"],
                        fields["key_assumptions"],
                        fields["target_metrics"],
                        fields["conviction_level"],
                        price,
                        filing["accession_number"],
                    ),
                )
                thesis_id = cursor.lastrowid
            drafted.append({"thesis_id": thesis_id, "ticker": ticker, **fields})
    finally:
        conn.close()
    if drafted:
        print(f"DRAFT ONLY — REVIEW IN DATABASE BEFORE USE: {len(drafted)} thesis row(s).")
    else:
        print("No holdings were missing a thesis.")
    return drafted


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft original theses for review")
    parser.add_argument("--db", help="database path (overrides UCIMCO_DB_PATH)")
    parser.add_argument("--dry-run", action="store_true", help="force mock LLM responses")
    args = parser.parse_args()
    draft_theses(args.db or db_path(), dry_run=True if args.dry_run else None)


if __name__ == "__main__":
    main()
