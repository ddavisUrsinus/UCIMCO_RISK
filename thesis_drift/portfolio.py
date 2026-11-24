"""Single source of truth for UCIMCO holdings.

Edit HOLDINGS below, then run `python thesis_drift/portfolio.py`. The script
upserts each ticker into Stocks and adds any BUY lot that is not already there,
so it is safe to run repeatedly.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thesis_drift.config import db_path
from thesis_drift.db.setup_db import connect, setup_database


@dataclass(frozen=True)
class Holding:
    ticker: str
    shares: float
    cost_basis: float
    buy_date: str


VALUATION_DATE = "2026-05-07"

# Extracted from _project2_source/UCIMCO_port.py's pf.add(...) calls.
# MSFT and NVDA had no explicit cost_basis there (yfinance resolved the
# 2026-05-07 close at runtime); 0.0 marks those unknown fills for the user to
# replace with real execution prices before relying on cost-basis analytics.
HOLDINGS: list[Holding] = [
    Holding("AAPL", 10.0000, 185.20, VALUATION_DATE),
    Holding("MSFT", 5.0000, 0.0, VALUATION_DATE),
    Holding("NVDA", 8.0000, 0.0, VALUATION_DATE),
    Holding("GOOGL", 13.1050, 397.99, VALUATION_DATE),
    Holding("DIS", 10.0000, 108.66, VALUATION_DATE),
    Holding("META", 8.0139, 616.81, VALUATION_DATE),
    Holding("NXST", 9.8496, 194.52, VALUATION_DATE),
    Holding("OMC", 11.2308, 76.92, VALUATION_DATE),
    Holding("ABNB", 11.0000, 140.46, VALUATION_DATE),
    Holding("MCD", 7.2726, 283.70, VALUATION_DATE),
    Holding("TNL", 20.9988, 65.91, VALUATION_DATE),
    Holding("COST", 2.0026, 1012.06, VALUATION_DATE),
    Holding("HSY", 12.5596, 187.06, VALUATION_DATE),
    Holding("PG", 10.5128, 146.06, VALUATION_DATE),
    Holding("COP", 11.0497, 114.88, VALUATION_DATE),
    Holding("SHEL", 16.9221, 84.24, VALUATION_DATE),
    Holding("TS", 28.0000, 58.96, VALUATION_DATE),
    Holding("CINF", 15.8254, 162.05, VALUATION_DATE),
    Holding("C", 5.0269, 129.09, VALUATION_DATE),
]

UNKNOWN_COST_BASIS = {
    "MSFT": "cost_basis absent in source pf.add(); replace with actual fill price",
    "NVDA": "cost_basis absent in source pf.add(); replace with actual fill price",
}


def sync_portfolio(path: Path | str | None = None) -> dict:
    """Upsert holdings and insert only BUY lots that do not exist yet."""
    target = Path(path or db_path())
    setup_database(target)
    conn = connect(target)
    inserted = 0
    existing = 0
    try:
        with conn:
            for holding in HOLDINGS:
                ticker = holding.ticker.upper()
                conn.execute(
                    "INSERT INTO Stocks (ticker, company_name) VALUES (?, ?) "
                    "ON CONFLICT(ticker) DO NOTHING",
                    (ticker, ticker),
                )
                stock_id = conn.execute(
                    "SELECT stock_id FROM Stocks WHERE ticker = ?", (ticker,)
                ).fetchone()["stock_id"]
                row = conn.execute(
                    "SELECT transaction_id FROM Transactions "
                    "WHERE stock_id = ? AND transaction_type = 'BUY' "
                    "AND transaction_date = ? AND shares = ? AND price_per_share = ?",
                    (stock_id, holding.buy_date, holding.shares, holding.cost_basis),
                ).fetchone()
                if row is not None:
                    existing += 1
                    continue
                conn.execute(
                    "INSERT INTO Transactions (stock_id, transaction_type, "
                    "transaction_date, shares, price_per_share, fees, notes) "
                    "VALUES (?, 'BUY', ?, ?, ?, 0, ?)",
                    (
                        stock_id,
                        holding.buy_date,
                        holding.shares,
                        holding.cost_basis,
                        UNKNOWN_COST_BASIS.get(ticker),
                    ),
                )
                inserted += 1
    finally:
        conn.close()
    return {
        "holdings": len(HOLDINGS),
        "lots_inserted": inserted,
        "lots_already_present": existing,
        "db": str(target),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync the holdings list to the DB")
    parser.add_argument("--db", help="database path (overrides UCIMCO_DB_PATH)")
    args = parser.parse_args()
    result = sync_portfolio(args.db or db_path())
    print(
        f"Portfolio sync: {result['holdings']} holdings, "
        f"{result['lots_inserted']} new BUY lots, "
        f"{result['lots_already_present']} already present. ({result['db']})"
    )


if __name__ == "__main__":
    main()
