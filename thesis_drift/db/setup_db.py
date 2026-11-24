"""Database setup and connection helpers (sqlite-vec enabled)."""

import sqlite3
import sys
from pathlib import Path

import sqlite_vec

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from thesis_drift.config import SCHEMA_PATH, db_path


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with foreign keys on and the sqlite-vec extension loaded."""
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    sqlite_vec.load(conn)
    return conn


def setup_database(path: Path | str | None = None) -> sqlite3.Connection:
    """Idempotently create every table, the vec0 table, and the holdings view."""
    target = Path(path or db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(target)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def main() -> None:
    target = db_path()
    conn = setup_database(target)
    conn.close()
    print(f"Database ready: {target}")


if __name__ == "__main__":
    main()
