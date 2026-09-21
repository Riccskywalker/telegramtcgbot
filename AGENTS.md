# Working in telegramtcgbot

## Structure

- `tcgbot/core/`: configuration, API client, cache, queries, prices, formatting and FX.
- Keep the core independent of chat transports; never import Telegram there.
- `tcgbot/telegram/`: polling, handlers, user-facing copy and group tracking.
- `tcgbot/__main__.py`: Telegram entry point, invoked with `python -m tcgbot`.
- Runtime settings and defaults live in `.env.example`; never commit `.env` or keys.

## Local checks

From the repository root, use Python satisfying `pyproject.toml` and activate a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q tests
```

Tests mock the HTTP transport; `tests/conftest.py` blocks real HTTP requests.
Use real recorded JSON fixtures in `tests/fixtures/`; preserve provider image URLs.

## API and credit rules

- Never request `include=prices` in searches; card searches use `include=set,images`.
- Card stats always use `window=7d`; sealed comparisons use Cardmarket's average from prices.
- Preserve uncached command budgets: inline list 1 credit; `/price` up to 5 (1 + 2 + 2); `/box` up to 3 (1 + 2); `/quota` 0.
- Price buttons fetch prices only: 2 credits, plus 1 if a detail lookup is needed. Do not price all search alternatives.
- Account for the separate set-index warmup (approximately 3 credits); preserve TTL caching and free ETag revalidation.
- Keep promotional links out of price messages. Attribution belongs only in `/start` and `/help`.
- Source costs, limits and endpoints from code and the verified README; do not invent them.

## Adding an entry point

Add an adapter such as `tcgbot/discord/` with its own configuration, handlers and bootstrap.
Reuse the existing core API, query, formatting and FX interfaces without modifying the core for Discord.
Keep platform SDKs and message translation in the adapter; test it with mocked transports.

## Manual smoke check

Export `PTCG_API_KEY`, then run `python scripts/smoke.py`; it does not load `.env`.
This is a live check, normally costing 5 credits. Run deliberately, separately from offline tests.
