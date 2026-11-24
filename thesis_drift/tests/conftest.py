import sys
from pathlib import Path
from uuid import uuid4

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from thesis_drift.db.setup_db import setup_database


@pytest.fixture
def scratch_dir():
    root = REPO_ROOT / ".scratch" / "pytest"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"test_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield path
    for child in path.iterdir():
        child.unlink(missing_ok=True)
    path.rmdir()


@pytest.fixture
def db_path(scratch_dir, monkeypatch):
    target = scratch_dir / "ucimco.db"
    setup_database(target)
    monkeypatch.setenv("UCIMCO_DB_PATH", str(target))
    return target
