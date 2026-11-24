"""HTML/PDF text extraction, local embeddings, and filing ingestion."""

import re
from pathlib import Path

import fitz
import numpy as np
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

from thesis_drift.config import db_path
from thesis_drift.db.setup_db import connect

_MODEL = None
EMBEDDING_DIM = 384


def _model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def extract_text_from_html(html: str) -> str:
    """Return visible text from EDGAR HTML, with scripts/styles and spacing removed."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def extract_text_from_pdf(path: str) -> str:
    """Fallback extraction for literal PDF exhibits (PyMuPDF, fully local)."""
    with fitz.open(path) as doc:
        text = "\n".join(page.get_text() for page in doc)
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split into word-based chunks with overlap (same logic as the source project)."""
    if chunk_size <= overlap or overlap < 0:
        raise ValueError("chunk_size must be greater than overlap (>= 0)")
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + chunk_size]))
        start += chunk_size - overlap
    return chunks


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed chunks locally with all-MiniLM-L6-v2 (384 dimensions)."""
    if not chunks:
        return []
    vectors = _model().encode(chunks, convert_to_numpy=True, show_progress_bar=False)
    return np.asarray(vectors, dtype=np.float32).tolist()


def ingest_filing(
    stock_id: int,
    filing_info: dict,
    html_text: str,
    path: Path | str | None = None,
) -> int:
    """Insert a document, its chunks, and its vectors; return its document_id.

    Re-ingesting the same accession for the same stock returns the existing id.
    """
    target = Path(path or db_path())
    conn = connect(target)
    try:
        existing = conn.execute(
            "SELECT document_id FROM Documents WHERE stock_id = ? AND accession_number = ?",
            (stock_id, filing_info["accession_number"]),
        ).fetchone()
        if existing is not None:
            return existing["document_id"]

        if str(filing_info.get("primary_document", "")).lower().endswith(".pdf") or html_text.lstrip().startswith("%PDF"):
            scratch_dir = target.parent.parent / ".scratch"
            scratch_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = scratch_dir / f"{filing_info['accession_number']}.pdf"
            pdf_path.write_bytes(html_text.encode("latin-1", errors="replace"))
            text = extract_text_from_pdf(str(pdf_path))
        else:
            text = extract_text_from_html(html_text)

        report_date = filing_info.get("report_date") or ""
        fiscal_year = int(report_date[:4]) if re.match(r"^\d{4}", report_date) else None
        chunks = chunk_text(text)
        vectors = embed_chunks(chunks)

        with conn:
            cursor = conn.execute(
                "INSERT INTO Documents (stock_id, doc_type, fiscal_year, filing_date, "
                "accession_number, source_url, extracted_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    stock_id,
                    filing_info["form"],
                    fiscal_year,
                    filing_info["filing_date"],
                    filing_info["accession_number"],
                    filing_info.get("primary_document_url"),
                    text,
                ),
            )
            document_id = cursor.lastrowid
            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                cursor = conn.execute(
                    "INSERT INTO Document_Chunks (document_id, stock_id, doc_type, "
                    "chunk_index, chunk_text) VALUES (?, ?, ?, ?, ?)",
                    (document_id, stock_id, filing_info["form"], index, chunk),
                )
                chunk_id = cursor.lastrowid
                conn.execute(
                    "INSERT INTO vec_chunks (rowid, chunk_embedding) VALUES (?, ?)",
                    (chunk_id, np.asarray(vector, dtype=np.float32)),
                )
        return document_id
    finally:
        conn.close()


def retrieve_chunks(
    query: str,
    stock_id: int,
    document_id: int,
    k: int = 3,
    path: Path | str | None = None,
) -> list[str]:
    """Top-k most similar chunks of one document for an assumption/metric query."""
    conn = connect(path or db_path())
    try:
        chunk_ids = [
            row["chunk_id"]
            for row in conn.execute(
                "SELECT chunk_id FROM Document_Chunks WHERE document_id = ? AND stock_id = ? "
                "ORDER BY chunk_index",
                (document_id, stock_id),
            )
        ]
        if not chunk_ids:
            return []
        vector = np.asarray(embed_chunks([query])[0], dtype=np.float32)
        placeholders = ",".join("?" for _ in chunk_ids)
        sql = (
            "SELECT c.chunk_text FROM vec_chunks v "
            "JOIN Document_Chunks c ON c.chunk_id = v.rowid "
            "WHERE v.chunk_embedding MATCH ? AND v.k = ? "
            f"AND v.rowid IN ({placeholders}) ORDER BY v.distance"
        )
        return [
            row["chunk_text"]
            for row in conn.execute(sql, [vector, k, *chunk_ids])
        ]
    finally:
        conn.close()
