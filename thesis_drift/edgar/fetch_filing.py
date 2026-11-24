"""Fetch recent 10-K/10-Q metadata and documents from SEC EDGAR."""

import re

from thesis_drift.edgar.http import get_text, get_json
from thesis_drift.edgar.ticker_cik import get_cik

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")


def _submissions(cik: str) -> dict:
    return get_json(SUBMISSIONS_URL.format(cik=cik))


def _document_url(cik: str, accession: str, document: str) -> str:
    return ARCHIVE_URL.format(
        cik=int(cik), accession=accession.replace("-", ""), document=document
    )


def _filing_info(cik: str, recent: dict, index: int) -> dict:
    accession = recent["accessionNumber"][index]
    document = recent["primaryDocument"][index]
    return {
        "cik": cik,
        "accession_number": accession,
        "form": recent["form"][index],
        "filing_date": recent["filingDate"][index],
        "report_date": recent.get("reportDate", [None] * len(recent["form"]))[index],
        "primary_document": document,
        "primary_document_url": _document_url(cik, accession, document),
    }


def _candidates(recent: dict, forms: tuple[str, ...]) -> list[int]:
    forms = tuple(form.upper() for form in forms)
    return [
        i
        for i, form in enumerate(recent["form"])
        if form.upper() in forms
    ]


def get_latest_filing(ticker: str, forms=("10-K", "10-Q")) -> dict:
    """Return metadata for the most recently filed 10-K/10-Q for ``ticker``."""
    cik = get_cik(ticker)
    recent = _submissions(cik)["filings"]["recent"]
    indexes = _candidates(recent, forms)
    if not indexes:
        raise LookupError(f"No filing with form {forms} found for {ticker} ({cik})")
    best = max(indexes, key=lambda i: (recent["filingDate"][i], recent["accessionNumber"][i]))
    return _filing_info(cik, recent, best)


def get_filing_newer_than(ticker: str, after_accession_or_date: str) -> dict | None:
    """Return the newest 10-K/10-Q filed strictly after an accession or date."""
    cik = get_cik(ticker)
    recent = _submissions(cik)["filings"]["recent"]
    reference = str(after_accession_or_date).strip()

    if DATE_RE.match(reference):
        threshold = reference
        candidates = [
            i for i in _candidates(recent, ("10-K", "10-Q"))
            if recent["filingDate"][i] > threshold
        ]
    elif ACCESSION_RE.match(reference):
        threshold = None
        for i, accession in enumerate(recent["accessionNumber"]):
            if accession == reference:
                threshold = recent["filingDate"][i]
                break
        if threshold is None:
            year, month = reference[0:4], reference[5:7]
            threshold = f"{year}-{month}-01"
        candidates = [
            i for i in _candidates(recent, ("10-K", "10-Q"))
            if (recent["filingDate"][i], recent["accessionNumber"][i])
            > (threshold, reference)
        ]
    else:
        raise ValueError(
            "after_accession_or_date must be an accession number or an ISO date, "
            f"got {after_accession_or_date!r}"
        )

    if not candidates:
        return None
    best = max(candidates, key=lambda i: (recent["filingDate"][i], recent["accessionNumber"][i]))
    return _filing_info(cik, recent, best)


def download_filing_document(filing_info: dict) -> str:
    """Fetch and return the primary document text for a filing."""
    url = filing_info.get("primary_document_url")
    if not url:
        url = _document_url(
            filing_info["cik"],
            filing_info["accession_number"],
            filing_info["primary_document"],
        )
    return get_text(url)
