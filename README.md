# RareBit Telegram bot

Bot Telegram che dà il **prezzo di carte e sigillati Pokémon** dentro le chat e
i gruppi, appoggiandosi all'**API pubblica di RareBit** (`api.rarebit.app`).

Side project: legge solo gli endpoint catalogo, **non tocca nulla della prod
RareBit**.

## Cosa fa (v1 — solo lookup)

- **Ricerca inline** `@nomebot charizard lost origin` — funziona in qualsiasi
  chat/gruppo **senza aggiungere il bot e senza leggere i messaggi**. È il modo
  con cui ti insedi nei gruppi senza fare spam.
- `/price <carta>` — prezzo (current value) + variazione 7 giorni, con bottone
  verso la scheda su RareBit. Più risultati → menù di scelta.
- `/box <sigillato>` — idem per box / ETB / tin / blister.
- `/start`, `/help` — istruzioni + bottone "aggiungimi a un gruppo".

Refusi tollerati (`charzard` → Charizard), multi-lingua/valuta come li dà l'API.
Ogni link verso rarebit.app porta i parametri UTM per misurare le conversioni.

Non fa (per scelta, v1): scan da foto, prezzi venduti eBay, deal finder,
portfolio, digest schedulati. Vedi la sezione "Roadmap".

## Setup

```bash
cd /Users/ricc/rarebit-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # poi metti RAREBIT_BOT_TOKEN
```

Crea il bot con [@BotFather](https://t.me/BotFather), prendi il token e mettilo
in `.env`. **Importante per i gruppi:**

- `/setprivacy` → **Enable** (privacy mode ON: il bot vede solo i comandi, non
  legge la chat — è anche ciò che convince gli admin a tenerlo).
- `/setinline` → abilita la modalità inline (placeholder es. `cerca una carta…`).
- `/setinlinefeedback` → opzionale.

## Avvio

```bash
python -m rarebit_bot
```

Gira in **polling** (nessun server/webhook richiesto). Una sola istanza per
token alla volta.

## Test

```bash
# funzioni pure (offline)
pip install -r requirements-dev.txt
pytest -q

# smoke end-to-end contro l'API live (rete, nessun token)
python scripts/smoke.py
```

## Deploy su VPS (come gli altri bot)

```bash
# sul VPS
git clone <repo> /opt/rarebit-bot && cd /opt/rarebit-bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # compila il token
sudo cp deploy/rarebit-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rarebit-bot
journalctl -u rarebit-bot -f
```

## Configurazione (env)

Tutte le variabili sono in `.env.example`. Le principali:

| Variabile             | Default                        | Note |
|-----------------------|--------------------------------|------|
| `RAREBIT_BOT_TOKEN`   | —                              | obbligatorio |
| `RAREBIT_LOCALE`      | `it`                           | lingua dei link al sito |
| `RAREBIT_IMAGE_MODE`  | `preview`                      | `preview`/`photo`/`none` |
| `RAREBIT_UTM`         | `utm_source=telegram…`         | vuoto per disattivare |
| `RAREBIT_CACHE_TTL`   | `120`                          | cache risposte API (s) |

> `IMAGE_MODE=preview` mostra la card art come anteprima-link sopra il testo.
> Le immagini sono `.webp`: se l'anteprima non rende su qualche client, prova
> `photo` (manda la foto) o `none`. Da rivalutare col token in mano.

## Struttura

```
rarebit_bot/
  config.py      env → Config
  api.py         client async API RareBit + cache + Item normalizzato
  formatting.py  URL, prezzi (stile IT), delta, rendering messaggi (puro)
  texts.py       tutta la copy italiana
  handlers.py    comandi, inline, callback, errori
  bot.py         bootstrap Application + polling
scripts/smoke.py smoke test live
tests/           test funzioni pure
deploy/          unit systemd
```

## Roadmap (fase 2, non in v1)

- Digest movers giornaliero/settimanale per gruppo (opt-in admin) — l'indice #29.
- Alert prezzo e valore portfolio (in DM, richiede collegare l'account).
- Box EV (concentrazione valore del set) nel comando `/box`.
- Conversione valuta unica (oggi mostra la valuta della fonte).
