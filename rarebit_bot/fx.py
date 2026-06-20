"""Conversione valute via tassi BCE (stessa fonte che usa RareBit).

I prezzi dell'API arrivano nella valuta della fonte (EUR per WEST, spesso USD
per il Giappone via TCGplayer). Qui li portiamo alla valuta di display
(default EUR). I tassi BCE sono EUR-based e si aggiornano una volta al giorno.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple
from xml.etree import ElementTree

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


def convert_amount(
    value: Optional[float],
    currency: Optional[str],
    target: str,
    rates: Optional[Dict[str, float]],
) -> Tuple[Optional[float], Optional[str]]:
    """Pura: converte `value` da `currency` a `target` usando tassi EUR-based.

    `rates` mappa CUR -> quante unità di CUR per 1 EUR (EUR stesso = 1.0).
    Se non si può convertire, ritorna l'importo originale invariato (onesto).
    """
    if value is None:
        return value, currency
    src = (currency or "").upper()
    tgt = (target or "").upper()
    if not src:
        return value, currency
    if src == tgt:
        return value, src
    if not rates or src not in rates or tgt not in rates:
        return value, currency
    eur = value / rates[src]
    return eur * rates[tgt], tgt


class FxRates:
    """Recupera e cachea i tassi BCE; espone una conversione async."""

    def __init__(self, timeout: float = 8.0, ttl: int = 21600) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": "rarebit-tg-bot/0.1"}
        )
        self._cache: TTLCache = TTLCache(maxsize=1, ttl=ttl)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def rates(self) -> Optional[Dict[str, float]]:
        cached = self._cache.get("r")
        if cached is not None:
            return cached
        try:
            resp = await self._client.get(ECB_URL)
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.text)
        except Exception as exc:  # rete/parse: degradiamo, niente conversione
            logger.warning("FX BCE non disponibile: %s", exc)
            return None
        out: Dict[str, float] = {"EUR": 1.0}
        for el in root.iter():
            cur = el.get("currency")
            rate = el.get("rate")
            if cur and rate:
                try:
                    out[cur.upper()] = float(rate)
                except ValueError:
                    pass
        if len(out) <= 1:
            return None
        self._cache["r"] = out
        return out

    async def convert(
        self, value: Optional[float], currency: Optional[str], target: str = "EUR"
    ) -> Tuple[Optional[float], Optional[str]]:
        if value is None:
            return value, currency
        src = (currency or "").upper()
        if not src or src == target.upper():
            return value, src or target.upper()
        return convert_amount(value, currency, target, await self.rates())
