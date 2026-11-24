from thesis_drift import portfolio
from thesis_drift.db.setup_db import connect


def _buy_lots(path):
    conn = connect(path)
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM Transactions WHERE transaction_type = 'BUY'"
        ).fetchone()["n"]
    finally:
        conn.close()


def test_portfolio_sync_is_idempotent_and_accepts_new_holdings(db_path, monkeypatch):
    first = portfolio.sync_portfolio(db_path)
    assert first["holdings"] == 19
    assert first["lots_inserted"] == 19
    assert _buy_lots(db_path) == 19

    second = portfolio.sync_portfolio(db_path)
    assert second["lots_inserted"] == 0
    assert second["lots_already_present"] == 19
    assert _buy_lots(db_path) == 19

    monkeypatch.setattr(
        portfolio,
        "HOLDINGS",
        portfolio.HOLDINGS + [portfolio.Holding("NEWCO", 3.0, 12.5, "2026-05-07")],
    )
    third = portfolio.sync_portfolio(db_path)
    assert third["lots_inserted"] == 1
    assert _buy_lots(db_path) == 20
