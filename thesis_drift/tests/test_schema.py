import numpy as np

from thesis_drift.db.setup_db import connect, setup_database


REQUIRED_TABLES = {
    "Stocks",
    "Transactions",
    "Price_History",
    "Documents",
    "Document_Chunks",
    "vec_chunks",
    "Thesis",
    "Drift_Events",
}
REQUIRED_VIEWS = {"Current_Holdings"}


def test_schema_builds_all_objects(db_path):
    conn = connect(db_path)
    try:
        objects = {
            row["name"]: row["type"]
            for row in conn.execute("SELECT name, type FROM sqlite_master")
        }
        assert REQUIRED_TABLES <= objects.keys()
        assert REQUIRED_VIEWS <= objects.keys()
        assert objects["vec_chunks"] == "table"
        assert conn.execute("SELECT vec_version()").fetchone()[0].startswith("v0")
    finally:
        conn.close()


def test_setup_database_is_idempotent(db_path):
    conn = setup_database(db_path)
    conn.close()
    conn = setup_database(db_path)
    conn.close()
    assert db_path.exists()


def test_vec0_round_trip(db_path):
    conn = connect(db_path)
    try:
        cursor = conn.execute("INSERT INTO Stocks (ticker, company_name) VALUES ('TEST', 'Test Co')")
        stock_id = cursor.lastrowid
        cursor = conn.execute(
            "INSERT INTO Documents (stock_id, doc_type, accession_number) "
            "VALUES (?, '10-Q', '0000000000-00-000001')",
            (stock_id,),
        )
        document_id = cursor.lastrowid
        cursor = conn.execute(
            "INSERT INTO Document_Chunks (document_id, stock_id, doc_type, chunk_index, chunk_text) "
            "VALUES (?, ?, '10-Q', 0, 'dummy')",
            (document_id, stock_id),
        )
        chunk_id = cursor.lastrowid
        vector = np.zeros(384, dtype=np.float32)
        vector[0] = 1.0
        conn.execute(
            "INSERT INTO vec_chunks (rowid, chunk_embedding) VALUES (?, ?)",
            (chunk_id, vector),
        )
        conn.commit()
        query = np.zeros(384, dtype=np.float32)
        query[0] = 1.0
        results = conn.execute(
            "SELECT rowid, distance FROM vec_chunks "
            "WHERE chunk_embedding MATCH ? AND k = 1 ORDER BY distance",
            (query,),
        ).fetchall()
        assert len(results) == 1
        assert results[0]["rowid"] == chunk_id
        assert results[0]["distance"] < 1e-6
    finally:
        conn.close()
