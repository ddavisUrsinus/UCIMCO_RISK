-- Consolidated SQLite schema for UCIMCO thesis-drift tracking.
-- Adapted from the four draft schemas in _project2_source/Storage/.

CREATE TABLE IF NOT EXISTS Stocks (
    stock_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    sector       TEXT,
    industry     TEXT,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Transactions (
    transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id         INTEGER NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('BUY', 'SELL')),
    transaction_date TEXT NOT NULL,
    shares           REAL NOT NULL,
    price_per_share  REAL NOT NULL,
    fees             REAL NOT NULL DEFAULT 0,
    notes            TEXT,
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id)
);

CREATE TABLE IF NOT EXISTS Price_History (
    price_history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id         INTEGER NOT NULL,
    price_date       TEXT NOT NULL,
    closing_price    REAL NOT NULL,
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id),
    UNIQUE (stock_id, price_date)
);

CREATE TABLE IF NOT EXISTS Documents (
    document_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id         INTEGER NOT NULL,
    doc_type         TEXT NOT NULL CHECK (doc_type IN ('10-K', '10-Q')),
    fiscal_year      INTEGER,
    filing_date      TEXT,
    accession_number TEXT NOT NULL,
    source_url       TEXT,
    extracted_text   TEXT,
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id),
    UNIQUE (stock_id, accession_number)
);

CREATE TABLE IF NOT EXISTS Document_Chunks (
    chunk_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    stock_id    INTEGER NOT NULL,
    doc_type    TEXT NOT NULL CHECK (doc_type IN ('10-K', '10-Q')),
    chunk_index INTEGER NOT NULL,
    chunk_text  TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES Documents(document_id),
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id)
);

-- sqlite-vec vec0 table; rowid is aligned to Document_Chunks.chunk_id.
CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
    chunk_embedding FLOAT[384]
);

CREATE TABLE IF NOT EXISTS Thesis (
    thesis_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id              INTEGER NOT NULL,
    thesis_date           TEXT NOT NULL,
    is_original           INTEGER NOT NULL DEFAULT 0 CHECK (is_original IN (0, 1)),
    thesis_summary        TEXT NOT NULL,
    key_assumptions       TEXT,
    target_metrics        TEXT,
    conviction_level      INTEGER CHECK (conviction_level BETWEEN 1 AND 5),
    price_at_thesis       REAL,
    source_accession_number TEXT,
    created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id)
);

CREATE TABLE IF NOT EXISTS Drift_Events (
    drift_event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id              INTEGER NOT NULL,
    thesis_id             INTEGER NOT NULL,
    event_date            TEXT NOT NULL,
    source_accession_number TEXT NOT NULL,
    drift_score           REAL NOT NULL CHECK (drift_score BETWEEN 1.0 AND 10.0),
    drift_summary         TEXT,
    status                TEXT NOT NULL CHECK (status IN ('CONFIRMED', 'WEAKENED', 'CHALLENGED', 'INVALIDATED')),
    created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id),
    FOREIGN KEY (thesis_id) REFERENCES Thesis(thesis_id)
);

CREATE VIEW IF NOT EXISTS Current_Holdings AS
SELECT
    s.stock_id,
    s.ticker,
    s.company_name,
    SUM(CASE WHEN t.transaction_type = 'BUY' THEN t.shares ELSE -t.shares END) AS shares_held,
    SUM(CASE WHEN t.transaction_type = 'BUY' THEN t.shares * t.price_per_share
             ELSE -(t.shares * t.price_per_share) END)
        / NULLIF(SUM(CASE WHEN t.transaction_type = 'BUY' THEN t.shares
                          ELSE -t.shares END), 0) AS avg_cost_basis,
    ph.closing_price AS latest_price,
    ph.price_date AS latest_price_date,
    SUM(CASE WHEN t.transaction_type = 'BUY' THEN t.shares ELSE -t.shares END)
        * ph.closing_price AS current_market_value
FROM Transactions t
JOIN Stocks s ON s.stock_id = t.stock_id
LEFT JOIN (
    SELECT ph1.stock_id, ph1.closing_price, ph1.price_date
    FROM Price_History ph1
    JOIN (
        SELECT stock_id, MAX(price_date) AS max_date
        FROM Price_History
        GROUP BY stock_id
    ) latest ON ph1.stock_id = latest.stock_id AND ph1.price_date = latest.max_date
) ph ON ph.stock_id = s.stock_id
GROUP BY s.stock_id, s.ticker, s.company_name, ph.closing_price, ph.price_date;
