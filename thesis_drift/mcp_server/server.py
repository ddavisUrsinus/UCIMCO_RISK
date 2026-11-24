"""MCP server exposing exactly four fixed, read/action tools (stdio transport)."""

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from thesis_drift.db.setup_db import connect
from thesis_drift.drift.run_drift_check import check_drift as run_check_drift

mcp = FastMCP("ucimco-thesis-drift")


@mcp.tool()
def list_holdings() -> list[dict]:
    """Rows of the Current_Holdings view."""
    conn = connect()
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM Current_Holdings ORDER BY ticker")]
    finally:
        conn.close()


@mcp.tool()
def get_thesis(ticker: str) -> dict | None:
    """The original thesis for one holding."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT t.* FROM Thesis t JOIN Stocks s ON s.stock_id = t.stock_id "
            "WHERE s.ticker = ? AND t.is_original = 1 ORDER BY t.thesis_id DESC LIMIT 1",
            (ticker.strip().upper(),),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


@mcp.tool()
def check_drift(ticker: str) -> dict:
    """Run the thesis-drift check for one holding and return the resulting event."""
    return run_check_drift(ticker)


@mcp.tool()
def get_drift_history(ticker: str) -> list[dict]:
    """All drift events for one holding, most recent first."""
    conn = connect()
    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT d.* FROM Drift_Events d JOIN Stocks s ON s.stock_id = d.stock_id "
                "WHERE s.ticker = ? ORDER BY d.event_date DESC, d.drift_event_id DESC",
                (ticker.strip().upper(),),
            )
        ]
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
