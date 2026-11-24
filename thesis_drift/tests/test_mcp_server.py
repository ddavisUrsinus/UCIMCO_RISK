from thesis_drift.db.setup_db import connect
from thesis_drift.mcp_server import server


def test_four_mcp_tools_are_registered_and_callable(db_path, monkeypatch):
    tools = {tool.name: tool.fn for tool in server.mcp._tool_manager.list_tools()}
    assert set(tools) == {
        "list_holdings",
        "get_thesis",
        "check_drift",
        "get_drift_history",
    }

    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO Stocks (ticker, company_name) VALUES ('AAPL', 'Apple Inc.')"
            )
            conn.execute(
                "INSERT INTO Transactions (stock_id, transaction_type, transaction_date, "
                "shares, price_per_share) VALUES (1, 'BUY', '2026-05-07', 10, 185.20)"
            )
    finally:
        conn.close()

    holdings = tools["list_holdings"]()
    assert holdings[0]["ticker"] == "AAPL"
    assert holdings[0]["shares_held"] == 10
    assert tools["get_thesis"]("AAPL") is None
    assert tools["get_drift_history"]("AAPL") == []

    monkeypatch.setattr(
        server,
        "run_check_drift",
        lambda ticker: {"ticker": ticker, "result": "NO_NEW_FILING"},
    )
    assert tools["check_drift"]("AAPL")["ticker"] == "AAPL"
