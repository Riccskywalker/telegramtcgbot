# telegramtcgbot: Pokémon TCG card price bot for Telegram

An open-source Python Pokémon TCG Telegram bot for card and sealed prices (Cardmarket, TCGplayer) in any chat or group, with inline search, Docker support, and a free API key from [pokemontcgapi.com](https://pokemontcgapi.com).

Powered by the Pokémon TCG API at [pokemontcgapi.com](https://pokemontcgapi.com).

## For AI agents

Follow this checklist from the checkout directory; ask the user for credentials instead of guessing them.

- [ ] Install Git and either Docker with Compose, or Python ≥3.9 (the minimum declared in [pyproject.toml](pyproject.toml)).
- [ ] Ask for `PTCG_API_KEY`: get a free server key at [free-api-key](https://pokemontcgapi.com/free-api-key). Verify the email for 800 trial credits and a 400/day cap; without verification, 80 credits and 40/day. Trial credits are granted once and do not renew.
- [ ] Ask for `TELEGRAM_BOT_TOKEN`: open [@BotFather](https://t.me/BotFather), run `/newbot`, then `/setinline` for that bot (placeholder: `Search card name, set or number`). Add it to the group; privacy mode can stay enabled.
- [ ] Clone the repository:

```sh
git clone https://github.com/Riccskywalker/telegramtcgbot.git && cd telegramtcgbot
```

- [ ] Write `.env` using the complete variable list and defaults from [.env.example](.env.example) below. Fill the required token and API key. Ask for the owner's positive Telegram user/private chat ID and set `ADMIN_CHAT_ID` to enable private `/quota`; leaving it blank disables that command. Keep `BOT_LANG=en` (English only).

```dotenv
TELEGRAM_BOT_TOKEN=
PTCG_API_KEY=
BOT_LANG=en
PTCG_API_BASE=https://api.pokemontcgapi.com/v1
ADMIN_CHAT_ID=
```

Do not commit `.env`; it is gitignored.

- [ ] Start with Docker:

```sh
docker compose up -d
docker compose logs -f telegramtcgbot
```

Or start with Python in the checkout directory (the bot loads `.env` there):

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m tcgbot
```

- [ ] Check the startup logs: `Starting polling...`, followed by `Bot started as @<username> (<id>)`. If `Set index warmup failed (<exception type>); lookups will retry` appears, resolve the API error below even if polling starts.
- [ ] Send `/start` in chat and confirm the instructions appear. From the configured admin's private chat, send `/quota` and check plan, credits, daily cap and trial expiry. Try `/price charizard 125` and `@your_bot charizard 125` to check prices and inline search against the credit budget below.

Run only one polling instance per Telegram token. Missing required credentials stop the process before network requests.

### Known errors

| Symptom / exact message | Action |
| --- | --- |
| Missing key: `PTCG_API_KEY is required. Get a free key at https://pokemontcgapi.com/free-api-key and verify your email.` | Fill `PTCG_API_KEY` in the checkout's `.env` and restart. Direct API client construction instead raises `PTCG_API_KEY is required: https://pokemontcgapi.com/free-api-key`. |
| Missing token: `TELEGRAM_BOT_TOKEN is required. Get a token from @BotFather.` | Fill `TELEGRAM_BOT_TOKEN` and restart. |
| HTTP 401: `The bot is misconfigured (API key). The owner has been notified in the log.` | Replace the incorrect key and restart; inspect `API HTTP %s code=%s request_id=%s` in logs for status, code and request ID. |
| `QUOTA_EXCEEDED`, `DAILY_CAP_EXCEEDED`, `TRIAL_EXHAUSTED`, `EMAIL_UNVERIFIED`: `This bot has used up its API credits for now. The owner can raise the limit at pokemontcgapi.com/pricing (or verify the account email).` | Verify the account email, inspect `/quota`, or review [pricing](https://pokemontcgapi.com/pricing). If the API supplies a nonempty `error.details.next_step.handoff`, the bot displays that text instead. |
| HTTP 429 / `RATE_LIMITED`: `Too many requests. Please try again in a moment.` | The client retries once after `Retry-After`; if it still fails, wait before trying again. |

After editing `.env`, re-run `docker compose up -d` to apply it, or restart the Python process/service.

## Commands

| Command | Example / purpose |
| --- | --- |
| `/start`, `/help` | Instructions and API attribution |
| `/price` | `/price charizard 125`, `/price charizard obsidian flames`, `/price mew sv2a` |
| `/price` with language | `/price charizard 125 EN` (also IT, DE, FR, ES) |
| `/box` | `/box lost origin booster box` (also ETBs, tins and packs) |
| `/quota` | Plan, credits used/limit and remaining, daily usage/cap and trial expiry; owner only in private chat |
| Inline | `@your_bot charizard 125`; select a result, then tap **Current value** |

`/quota` reads `data.quota.trial_expires_at` and `trial_expired`: expiry shows `(expired)` when applicable, `not applicable` for renewing plans, or `not provided` if missing. The quota period end is separate from trial expiry.

Price messages have no promotional links. Attribution appears only in `/start` and `/help`.

## What it costs in credits

| Action | Credits |
| --- | ---: |
| Inline result list (one search, up to 25 candidates) | 1 |
| `/price` | Up to 5: search 1 + prices 2 + 7d stats 2 |
| `/box` | Up to 3: search 1 + prices 2 |
| Repeated lookups within TTL, or unchanged ETag revalidation | 0 |
| Images | 0 |
| `/quota` | 0 |

Unverified accounts have 80 credits with a 40/day cap; verified trial accounts have 800 credits with a 400/day cap. 800 trial credits ≈ 160 price checks; a group doing 20 price checks a day (~100 credits) stays under the 400/day cap and runs ~8 days on the trial, then Developer at 29 €/month gives 50,000 credits.

These estimates exclude the set index: approximately 3 credits at startup (652 sets, 250 per page), shared across all lookups. It refreshes after 24 hours using ETags. The in-memory cache holds up to 2,000 URLs: searches and prices for 6 hours, sets and details for 24 hours. A restart clears it; eviction can also require a new request. An expired entry sends `If-None-Match`: a 304 is free, while changed data costs the normal endpoint credits.

Inline lists contain names, sets, collector numbers and images. Selecting a result posts its identity; tap **Current value** to load its price for 2 additional credits, with no stats request. A selection whose item has expired may also need a 1-credit detail lookup. Alternatives under `/price` and `/box` are only priced when tapped. Search lists never request `include=prices`.

Prices use the EUR index and its date. An explicit language tag selects that locale's normal printing when available (NORMAL before unspecified printing); otherwise the overall index is used. The trial can withhold non-English locales. If there is no index, the bot uses TCGplayer Market in USD and converts with cached ECB exchange rates; if FX is unavailable it shows USD. Source quotes retain their original currency. Sealed changes compare current value with Cardmarket's 7-day average, and are labelled accordingly.

Trial credit limits and daily caps were verified by the auditor against live `/v1/me` responses on 2026-09-21.

## How it talks to the API

The client sends `X-Api-Key` to `https://api.pokemontcgapi.com/v1`. Paths and query parameters below come from [core/api.py](tcgbot/core/api.py); normal request costs follow the verified credit budget above. TTLs are in-memory, per URL.

| Endpoint | Credits on cache miss / changed response | Cache TTL |
| --- | ---: | --- |
| `/v1/sets?limit=250` (follow pagination) | 1 per page; approximately 3 for the recorded catalogue | 24 hours |
| `/v1/cards?q=…&limit=25&include=set,images` | 1 | 6 hours |
| `/v1/cards/{id}?include=set,images` | 1 | 24 hours |
| `/v1/cards/{id}/prices` | 2 | 6 hours |
| `/v1/cards/{id}/prices/stats?window=7d` (optional `locale`) | 2 | 6 hours |
| `/v1/sealed?q=…&limit=25` | 1 | 6 hours |
| `/v1/sealed/{id}` | 1 | 24 hours |
| `/v1/sealed/{id}/prices` | 2 | 6 hours |
| `/v1/me` | 0 | Uncached |

Searches never use `include=prices`. Sealed comparisons use the prices response's Cardmarket average; there is no sealed stats request. Images are passed to Telegram as provider URLs; the bot does not download image bytes. API quota headers are logged at DEBUG; fewer than 50 remaining credits trigger at most one warning per hour.

## Query syntax the bot builds

Use English card names. Set names and PTCGO codes resolve through the cached set index; multiword names are quoted. Purely numeric collector numbers lose leading zeros. Language tags are removed before searching and select a price locale when the plan includes it.

| User query | API `q` / price selection |
| --- | --- |
| `charizard obsidian flames` | `name:charizard set.code:obf` |
| `charizard 0125` | `name:charizard number:125` |
| `charizard 125 EN` | `name:charizard number:125`; requested price locale `en` |
| `mew sv2a` | `name:mew set.code:sv2a` |

`mew` remains a Pokémon name to avoid a set-code collision. Typos pass through without extra paid searches or guaranteed correction. Sealed searches pass the query text through after removing any language tag.

## Run as a service

Compose uses `restart: unless-stopped`; run `docker compose up -d` from the checkout. `groups.json` survives container restarts, but not container replacement. There are no scheduled group broadcasts.

For systemd on Linux, first stop any foreground bot or run `docker compose down` if Docker uses the same token. Prepare the service account and checkout (requires sudo):

```sh
sudo useradd --system --user-group --home-dir /opt/telegramtcgbot telegramtcgbot
sudo git clone https://github.com/Riccskywalker/telegramtcgbot.git /opt/telegramtcgbot
sudo cp .env /opt/telegramtcgbot/.env
sudo chown -R telegramtcgbot:telegramtcgbot /opt/telegramtcgbot
sudo chmod 600 /opt/telegramtcgbot/.env
sudo -u telegramtcgbot python3 -m venv /opt/telegramtcgbot/.venv
sudo -u telegramtcgbot /opt/telegramtcgbot/.venv/bin/pip install -r /opt/telegramtcgbot/requirements.txt
sudo cp /opt/telegramtcgbot/deploy/telegramtcgbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegramtcgbot
sudo journalctl -u telegramtcgbot -f
```

Skip account/checkout creation if already prepared. The account needs write access to `/opt/telegramtcgbot` for `groups.json`. After changing the service's `.env`, use `sudo systemctl restart telegramtcgbot`.

## Development

From the checkout, with the virtual environment activated:

```sh
pip install -r requirements-dev.txt
python -m pytest -q tests
```

Tests use real recorded JSON in `tests/fixtures/` and mocked HTTP transport; they make no network calls. Preserve provider image URLs. Read [AGENTS.md](AGENTS.md) for architecture and credit rules.

For a manual live smoke check, export `PTCG_API_KEY`, then run `python scripts/smoke.py`. It does not read `.env`. It makes a field search, a prices request, a stats request with `window=7d`, and a `/v1/me` request, normally costing 5 credits; it prints the costs reported in response headers.

## Roadmap

Discord entry point next (`discordtcgbot`), reusing the same transport-independent core.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Pokémon is a trademark of its respective owners; this project is not affiliated with Nintendo, Creatures, GAME FREAK, or The Pokémon Company.
