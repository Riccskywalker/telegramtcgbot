"""Client async per l'API pubblica del catalogo RareBit.

Endpoint usati (no auth):
    GET /catalog/cards?q=&limit=     ricerca carte (typo-tolerant)
    GET /catalog/cards/{id}          dettaglio carta (price board multi-fonte)
    GET /catalog/boxes?q=&limit=     ricerca sigillati
    GET /catalog/boxes/{id}          dettaglio sigillato

Espone risultati normalizzati come `Item`, uguali per carte e box, così che
formatting/handlers non debbano conoscere la forma grezza del JSON.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
from cachetools import TTLCache

from .search import SetIndex, parse_query, rank, tokens

logger = logging.getLogger(__name__)


@dataclass
class Item:
    """Carta o sigillato, normalizzati per il rendering."""

    kind: str  # "card" | "box"
    id: str
    name: str
    image_url: Optional[str] = None
    # valore headline (current value, già risolto dal catalogo quando disponibile)
    price: Optional[float] = None
    currency: Optional[str] = None
    delta_pct: Optional[float] = None  # variazione 7 giorni, in %
    # campi carta
    number: Optional[str] = None
    rarity: Optional[str] = None
    # set (per costruire l'URL)
    set_code: Optional[str] = None
    set_slug: Optional[str] = None
    set_name: Optional[str] = None
    # campi box
    sku: Optional[str] = None
    product_kind: Optional[str] = None


def _card_item(raw: Dict[str, Any]) -> Item:
    return Item(
        kind="card",
        id=raw.get("id", ""),
        name=raw.get("name") or "—",
        image_url=raw.get("imageUrl"),
        price=raw.get("price"),
        currency=raw.get("priceCurrency"),
        delta_pct=raw.get("priceDeltaPct"),
        number=raw.get("number"),
        rarity=raw.get("rarity"),
        set_code=raw.get("setCode"),
        set_slug=raw.get("setSlug"),
        set_name=raw.get("setName"),
    )


def _box_item(raw: Dict[str, Any]) -> Item:
    return Item(
        kind="box",
        id=raw.get("id", ""),
        name=raw.get("name") or "—",
        image_url=raw.get("imageUrl"),
        price=raw.get("price"),
        currency=raw.get("priceCurrency"),
        delta_pct=raw.get("priceDeltaPct"),
        set_code=raw.get("setCode"),
        set_name=raw.get("setName"),
        sku=raw.get("sku"),
        product_kind=raw.get("productKind"),
    )


def headline_from_board(board: Optional[Dict[str, Any]]) -> Tuple[Optional[float], Optional[str]]:
    """Ricava un valore headline dal price board del dettaglio.

    Mirror leggero della logica del sito: per i sigillati/le carte WEST il
    riferimento è il global-lowest Cardmarket (min tra le lingue prezzate);
    se manca, si ripiega su TCGplayer. Serve solo come fallback quando il
    valore di catalogo (`price`) non è disponibile (es. alcuni box).
    """
    if not board:
        return None, None

    cm = board.get("cardmarket") or {}
    langs = cm.get("languages") or []
    prices = [
        (lang.get("price"), lang.get("currency"))
        for lang in langs
        if isinstance(lang.get("price"), (int, float))
    ]
    if prices:
        price, currency = min(prices, key=lambda p: p[0])
        return float(price), currency

    tcg = board.get("tcgplayer") or {}
    if isinstance(tcg.get("price"), (int, float)):
        return float(tcg["price"]), tcg.get("currency")

    return None, None


def card_headline(
    detail: Optional[Dict[str, Any]], language: Optional[str]
) -> Tuple[Optional[float], Optional[str], Optional[float], Optional[str]]:
    """Current value di una carta dal dettaglio, come lo calcola il sito.

    Ritorna (valore, valuta, delta7d, lingua_cardmarket_applicata|None). Cascata:
      1) lingua richiesta in Cardmarket → quel prezzo;
      2) WEST: global-lowest tra le lingue Cardmarket;
      3) JP/altro: TCGplayer **max(market, lowest listing)** (regola del sito #150);
      4) CardTrader global-lowest.
    `None` se nessuna fonte è prezzata (→ il chiamante usa il price di lista).
    """
    if not detail:
        return None, None, None, None
    pb = detail.get("priceBoard") or {}
    cm_langs = (pb.get("cardmarket") or {}).get("languages") or []

    if language:
        for lang in cm_langs:
            if lang.get("language") == language and isinstance(lang.get("price"), (int, float)):
                return float(lang["price"]), lang.get("currency"), lang.get("d7d"), language

    cm_priced = [l for l in cm_langs if isinstance(l.get("price"), (int, float))]
    if cm_priced:
        lo = min(cm_priced, key=lambda l: l["price"])
        return float(lo["price"]), lo.get("currency"), lo.get("d7d"), None

    tcg = pb.get("tcgplayer") or {}
    tcg_vals = [v for v in (tcg.get("price"), tcg.get("lowestListing")) if isinstance(v, (int, float))]
    if tcg_vals:
        return float(max(tcg_vals)), tcg.get("currency"), tcg.get("d7d"), None

    ct_langs = (pb.get("cardtrader") or {}).get("languages") or []
    ct_priced = [l for l in ct_langs if isinstance(l.get("price"), (int, float))]
    if ct_priced:
        lo = min(ct_priced, key=lambda l: l["price"])
        return float(lo["price"]), lo.get("currency"), None, None

    return None, None, None, None


class RarebitAPI:
    """Wrapper async con cache TTL su ricerche e dettagli."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 8.0,
        cache_ttl: int = 120,
        user_agent: str = "rarebit-tg-bot/0.1",
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )
        # cache delle risposte grezze JSON
        self._json_cache: TTLCache = TTLCache(maxsize=1024, ttl=cache_ttl)
        # cache degli Item per id, per servire i callback senza ri-cercare
        self._items: TTLCache = TTLCache(maxsize=4096, ttl=max(cache_ttl, 300))
        # indice dei set (codici/nomi), caricato pigramente una volta
        self._set_index: Optional[SetIndex] = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        key = (path, tuple(sorted((params or {}).items())))
        if key in self._json_cache:
            return self._json_cache[key]
        try:
            resp = await self._client.get(path, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("API %s -> HTTP %s", path, exc.response.status_code)
            return None
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("API %s fallita: %s", path, exc)
            return None
        self._json_cache[key] = data
        return data

    def _remember(self, item: Item) -> None:
        if item.id:
            self._items[(item.kind, item.id)] = item

    async def set_index(self) -> Optional[SetIndex]:
        """Carica (una volta) l'indice di tutti i set per il riconoscimento."""
        if self._set_index is not None:
            return self._set_index
        raw: List[dict] = []
        skip = 0
        for _ in range(6):  # 373 set / 200 a pagina → bastano 2 giri; 6 è margine
            data = await self._get_json("/catalog/sets", {"take": 200, "skip": skip})
            batch = (data or {}).get("items", [])
            if not batch:
                break
            raw.extend(batch)
            if len(batch) < 200:
                break
            skip += 200
        if raw:
            self._set_index = SetIndex.build(raw)
        return self._set_index

    async def search_cards(self, query: str, limit: int = 6) -> List[Item]:
        """Ricerca carte con riconoscimento set/numero + ranking lato bot."""
        index = await self.set_index()
        p = parse_query(query, index)
        params = {"q": p.q, "take": 50}
        if p.set_code:
            params["setCode"] = p.set_code
        data = await self._get_json("/catalog/cards", params)
        items = [_card_item(raw) for raw in (data or {}).get("items", [])]
        for it in items:
            self._remember(it)
        return rank(items, p)[:limit]

    async def search_boxes(self, query: str, limit: int = 6) -> List[Item]:
        data = await self._get_json("/catalog/boxes", {"q": query, "take": 50})
        items = [_box_item(raw) for raw in (data or {}).get("items", [])]
        for it in items:
            self._remember(it)
        # ranking leggero: copertura dei token del nome
        qt = tokens(query)
        scored = sorted(
            enumerate(items),
            key=lambda p: (-sum(1 for t in qt if t in set(tokens(p[1].name))), p[0]),
        )
        return [it for _, it in scored][:limit]

    async def get_card_detail(self, card_id: str) -> Optional[Dict[str, Any]]:
        return await self._get_json("/catalog/cards/{}".format(card_id))

    async def price_in_language(
        self, card_id: str, language: str
    ) -> Optional[Tuple[float, Optional[str], Optional[float]]]:
        """Prezzo Cardmarket di una carta nella lingua data (dal dettaglio).

        Ritorna (prezzo, valuta, delta7d) o None se quella lingua non è prezzata
        (es. carte JP via TCGplayer, o lingua mancante)."""
        detail = await self.get_card_detail(card_id)
        if not detail:
            return None
        cm = (detail.get("priceBoard") or {}).get("cardmarket") or {}
        for lang in cm.get("languages") or []:
            if lang.get("language") == language and isinstance(
                lang.get("price"), (int, float)
            ):
                return float(lang["price"]), lang.get("currency"), lang.get("d7d")
        return None

    async def get_box_detail(self, box_id: str) -> Optional[Dict[str, Any]]:
        return await self._get_json("/catalog/boxes/{}".format(box_id))

    async def resolve(self, kind: str, item_id: str) -> Optional[Item]:
        """Recupera un Item per id: prima dalla cache, poi dal dettaglio.

        Usato dai callback (l'utente tappa un risultato): di solito la cache
        è calda; in caso di miss ricostruiamo dal dettaglio così il bot non
        resta muto.
        """
        cached = self._items.get((kind, item_id))
        if cached is not None:
            return cached

        if kind == "card":
            detail = await self.get_card_detail(item_id)
            if not detail:
                return None
            set_obj = detail.get("set") or {}
            price, currency = headline_from_board(detail.get("priceBoard"))
            item = Item(
                kind="card",
                id=item_id,
                name=detail.get("name") or "—",
                image_url=detail.get("imageUrl"),
                price=price,
                currency=currency,
                number=detail.get("number"),
                rarity=detail.get("rarity"),
                set_code=detail.get("setCode") or set_obj.get("code"),
                set_slug=detail.get("setSlug") or set_obj.get("slug"),
                set_name=detail.get("setName") or set_obj.get("name"),
            )
            self._remember(item)
            return item

        if kind == "box":
            detail = await self.get_box_detail(item_id)
            if not detail:
                return None
            set_obj = detail.get("set") or {}
            price, currency = headline_from_board(detail.get("priceBoard"))
            item = Item(
                kind="box",
                id=item_id,
                name=detail.get("name") or "—",
                image_url=detail.get("imageUrl"),
                price=price,
                currency=currency,
                sku=detail.get("sku"),
                product_kind=detail.get("productKind"),
                set_code=set_obj.get("code"),
                set_name=set_obj.get("name"),
            )
            self._remember(item)
            return item

        return None

    async def enrich_box_value(self, item: Item) -> Item:
        """Per i box senza `price` di catalogo, calcola un headline dal board."""
        if item.kind != "box" or item.price is not None:
            return item
        detail = await self.get_box_detail(item.id)
        if not detail:
            return item
        price, currency = headline_from_board(detail.get("priceBoard"))
        if price is not None:
            item.price = price
            item.currency = currency
        if not item.sku:
            item.sku = detail.get("sku")
        self._remember(item)
        return item
