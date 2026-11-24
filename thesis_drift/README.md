# UCIMCO thesis-drift tracker

Answers one question for each current holding: **should UCIMCO re-evaluate this
position?** It re-pulls each company's newest 10-K/10-Q and checks whether the
*specific assumptions and target metrics of that holding's original thesis*
still hold. It is not a generic "what changed at this company" summarizer.

## Setup

Run from the repository root:

1. `python -m venv .venv && source .venv/bin/activate` (optional but recommended)
2. `pip install -r thesis_drift/requirements.txt`
   - If PyTorch needs a CPU-only build: `pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1` before step 2.
3. `python thesis_drift/db/setup_db.py` (or `python scripts/setup_db.py`) — creates `thesis_drift/db/ucimco.db`, loads sqlite-vec, creates `vec_chunks`.
4. Edit the `HOLDINGS` list at the top of `thesis_drift/portfolio.py`, then run `python thesis_drift/portfolio.py`. This is the only seed mechanism: it upserts stocks and inserts missing BUY lots. Re-running is idempotent.
5. `python thesis_drift/thesis/draft_theses.py` — drafts original theses for holdings that lack one.
6. **Review and correct every drafted thesis in the `Thesis` table.** Drafts are placeholders/LLM output, not authoritative UCIMCO reasoning.
7. `python thesis_drift/drift/run_drift_check.py AAPL` (or no argument to check all holdings).
8. Register the MCP server with Hermes:
   `hermes mcp add ucimco-thesis-drift python thesis_drift/mcp_server/server.py`

Tests: `pytest thesis_drift/tests/ -v`. They use scratch databases under
`./.scratch/`; `test_edgar.py` hits real SEC EDGAR (no HTTP mocking).

## LLM configuration (real credentials later)

Set environment variables (a `.env` file in the repo root also works via
`python-dotenv`):

- `LLM_PROVIDER` — `anthropic` or `openai`
- `LLM_API_KEY` — your API key for that provider
- `LLM_MODEL` — optional; defaults to `claude-3-5-haiku-latest` or `gpt-4o-mini`

Nothing else needs changing. With **no key configured**, `draft_theses.py` and
`run_drift_check.py` print a loud warning and use explicit MOCK responses so the
full pipeline (EDGAR fetch → ingest → chunk/embed → sqlite-vec retrieval →
prompt assembly → DB write) can be smoke-tested without a paid API. Mock theses
and mock drift results are labeled and must be reviewed/replaced.

## Drift score bands

The fixed prompt hardcodes the interpretation:

| Score | Status | Meaning |
| --- | --- | --- |
| 7–10 | `CONFIRMED` | Original thesis holds. |
| 4–6.99 | `WEAKENED` | A monitored assumption is softening; watch it. |
| 2–4 | `CHALLENGED` | A key assumption/metric reversed; flag for review. |
| 1–2 | `INVALIDATED` | Original reason to hold is broken; re-evaluate the position. |

Drift checks are skipped entirely (no LLM call) when no newer 10-K/10-Q exists
since the last analyzed accession.

## SEC EDGAR fair access

All EDGAR requests send `User-Agent: UCIMCO Fund Research Bot contact@ucimco-placeholder.edu`
and are throttled to 10 requests/second. **Replace the placeholder email with a
real UCIMCO contact address before real use**, as required by the SEC's
fair-access policy. Ticker→CIK data is cached in `thesis_drift/edgar/.cache/`.

## MCP tools

Exactly four fixed tools are exposed (no free-form SQL or arbitrary query tool):

- `list_holdings()` — `Current_Holdings` view
- `get_thesis(ticker)` — original thesis row
- `check_drift(ticker)` — runs the drift check
- `get_drift_history(ticker)` — drift events, newest first

## Data notes

The original portfolio source resolved MSFT and NVDA cost bases dynamically
via yfinance and did not contain literal fill prices; `0.0` plus a transaction
note marks them as unknown. Replace those values in `HOLDINGS` with real fills
if cost-basis reporting matters.
