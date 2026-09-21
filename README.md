# telegramtcgbot

Pokémon TCG card and sealed prices in your Telegram group, using your own pokemontcgapi.com key.

## Install in 10 minutes

1. Get a free server API key at https://pokemontcgapi.com/free-api-key and **verify your email** to unlock 800 trial credits with a 400 credits/day cap. Without verification you have only 80 credits with a 40 credits/day cap: a busy bot can stop in an afternoon. Check `/quota` for your account’s effective cap. Trial credits are granted once; they do not renew.
2. Get a Telegram token from **@BotFather** with `/newbot`. Enable inline searches with `/setinline` (for example, placeholder `Search card name, set or number`). Add the bot to your group; Telegram privacy mode can stay enabled.
3. In the cloned repository, create `.env` with these three lines:

   ```dotenv
   TELEGRAM_BOT_TOKEN=your_botfather_token
   PTCG_API_KEY=your_server_api_key
   BOT_LANG=en
   ```

4. Start with Docker:

   ```sh
   docker compose up -d
   ```

   Or use Python 3.9+:

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   . .venv/bin/activate
   python -m tcgbot
   ```

Only run one polling instance per Telegram token. The process exits before any network request if either required credential is missing.

Optional `.env` settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `PTCG_API_BASE` | `https://api.pokemontcgapi.com/v1` | API root |
| `BOT_LANG` | `en` | Interface language; this release supports English only |
| `ADMIN_CHAT_ID` | unset | Owner's positive Telegram user/private chat ID, enabling private `/quota` |

`groups.json` tracks group membership locally. In Docker it survives a container restart, but not container replacement. There are no scheduled group broadcasts.

For systemd, create a `telegramtcgbot` service account, place the checkout, `.env` and virtual environment in `/opt/telegramtcgbot`, make that directory writable by the account for `groups.json`, then install `deploy/telegramtcgbot.service` in `/etc/systemd/system/` and enable it. Choose systemd or Docker, not both for the same token.

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

## Commands

| Command | Example / purpose |
| --- | --- |
| `/start`, `/help` | Instructions |
| `/price` | `/price charizard 125`, `/price charizard obsidian flames`, `/price mew sv2a` |
| `/price` with language | `/price charizard 125 EN` (also IT, DE, FR, ES) |
| `/box` | `/box lost origin booster box` |
| `/quota` | Plan, credits used/limit and remaining, daily usage/cap and trial expiry; owner only in private chat |
| Inline | `@your_bot charizard 125` |

`/v1/me` exposes the trial expiry in `data.quota.trial_expires_at` and its status in `data.quota.trial_expired`. `/quota` shows the expiry with `(expired)` when applicable, `not applicable` for renewing plans, and `not provided` only when the field is missing. It also shows the quota period end separately; trial credits do not renew.

Use English names. Queries become field syntax such as `name:charizard set.code:obf number:125`; multiword names are quoted. Set names and PTCGO codes are recognized. Typos are passed through, without additional paid searches or a guarantee of correction. `mew` stays a Pokémon name to avoid its collision with a set code.

Price messages have no promotional links. Attribution appears only at the end of `/start` and `/help`.

## Development

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests
.venv/bin/python -m compileall tcgbot
```

Tests use recorded JSON fixtures and mock HTTP; they make no network calls. Fixture image URLs are preserved exactly as returned by the provider. The bot sends image URLs to Telegram and never downloads image bytes.

For a **manual live audit**, export `PTCG_API_KEY` and run `.venv/bin/python scripts/smoke.py`. It performs one field search, one prices request, one stats request with `window=7d`, and one `/v1/me` request, then prints credits reported by the response headers (normally 5). It does not read `.env`.

`tcgbot/core/` owns configuration, API, caching, query parsing, prices, formatting and FX; it imports no Telegram modules. `tcgbot/telegram/` owns polling, handlers, copy and group tracking. API quota headers are logged at DEBUG; fewer than 50 remaining credits trigger at most one warning per hour.

## Roadmap

Discord entry point next (`discordtcgbot`), reusing the same core.

## License

MIT — see [LICENSE](LICENSE).
