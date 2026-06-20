"""Smoke test live (rete, nessun token Telegram).

Esercita ricerca con ranking (set/numero), conversione FX in euro, box.

    python scripts/smoke.py
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rarebit_bot.api import RarebitAPI  # noqa: E402
from rarebit_bot.config import load_config  # noqa: E402
from rarebit_bot.fx import FxRates  # noqa: E402
from rarebit_bot.formatting import format_money, item_url  # noqa: E402
from rarebit_bot.search import extract_language  # noqa: E402


async def show(api, fx, cfg, it):
    val, cur = await fx.convert(it.price, it.currency, cfg.display_currency)
    money = format_money(val, cur) or "n/d"
    return "{} | {} ({}) #{} | {}".format(
        it.name, it.set_name, it.set_code, it.number, money
    )


async def main() -> int:
    cfg = load_config(require_token=False)
    api = RarebitAPI(cfg.api_base, cfg.http_timeout, cfg.cache_ttl)
    fx = FxRates(timeout=cfg.http_timeout)
    fails = 0
    try:
        rates = await fx.rates()
        print("FX BCE:", "ok (USD=%.4f)" % rates["USD"] if rates else "NON disponibile")

        checks = [
            ("charizard lost origin", lambda it: "lost origin" in (it.set_name or "").lower()),
            ("charizard 04", lambda it: (it.number or "").lstrip("0") in ("4", "")),
            ("mew sv2a", lambda it: (it.set_code or "") == "SV2a"),
            ("charzard", lambda it: "chari" in it.name.lower()),  # typo
        ]
        for q, ok in checks:
            items = await api.search_cards(q, 4)
            print("\n== /price %s ==" % q)
            if not items:
                print("  FAIL: nessun risultato"); fails += 1; continue
            for it in items[:3]:
                print("  •", await show(api, fx, cfg, it))
            if not ok(items[0]):
                print("  !! TOP non soddisfa l'atteso"); fails += 1
            else:
                print("  → top OK:", item_url(items[0], cfg.site_base, cfg.locale, ""))

        print("\n== lingua su Charizard Lost Origin (default config = %s) ==" % cfg.default_language)
        items = await api.search_cards("charizard lost origin", 1)
        if not items:
            print("  FAIL: nessun risultato"); fails += 1
        else:
            it = items[0]
            gv, gc = await fx.convert(it.price, it.currency, cfg.display_currency)
            print("  global-lowest (no default):", format_money(gv, gc))
            for label, lang in [("senza tag → default", cfg.default_language), ("tag IT", "it")]:
                if not lang:
                    continue
                lp = await api.price_in_language(it.id, lang)
                if lp:
                    ev, ec = await fx.convert(lp[0], lp[1], cfg.display_currency)
                    print("  %s (%s):" % (label, lang.upper()), format_money(ev, ec))
                else:
                    print("  %s: non disponibile" % label)
    finally:
        await api.aclose()
        await fx.aclose()

    print("\n== Esito:", "OK" if fails == 0 else "%d FALLIMENTI" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
