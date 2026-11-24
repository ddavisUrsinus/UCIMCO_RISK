"""Shared paths and SEC fair-access settings for thesis_drift."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "db" / "ucimco.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
EDGAR_CACHE_DIR = BASE_DIR / "edgar" / ".cache"

# PLACEHOLDER: replace contact@ucimco-placeholder.edu with a real contact
# address before using EDGAR in production (SEC fair-access policy).
USER_AGENT = "UCIMCO Fund Research Bot contact@ucimco-placeholder.edu"

MAX_REQUESTS_PER_SECOND = 10
MIN_REQUEST_INTERVAL = 1.0 / MAX_REQUESTS_PER_SECOND


def db_path() -> Path:
    """Return the active database path (overridable for tests via env var)."""
    return Path(os.environ.get("UCIMCO_DB_PATH") or str(DEFAULT_DB_PATH))
