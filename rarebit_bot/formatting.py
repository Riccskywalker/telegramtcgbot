"""Rendering degli `Item` in messaggi Telegram (HTML) + costruzione URL.

Funzioni pure e testabili: nessuna dipendenza da Telegram o dalla rete.
"""

from __future__ import annotations

from html import escape
from typing import Optional
from urllib.parse import quote

from .api import Item
from .texts import PRICE_UNAVAILABLE

# Etichette leggibili per i tipi di sigillato più comuni
PRODUCT_KIND_LABELS = {
    "ETB": "Elite Trainer Box",
    "BOOSTER_BOX": "Booster Box",
    "BOOSTER_BUNDLE": "Booster Bundle",
    "BOOSTER_PACK": "Bustina",
    "BLISTER": "Blister",
    "TIN": "Tin",
    "MINI_TIN": "Mini Tin",
    "EX_BOX": "ex Box",
    "COLLECTION_BOX": "Collection Box",
    "PREMIUM_COLLECTION": "Premium Collection",
    "BUILD_AND_BATTLE": "Build & Battle",
}


# --------------------------------------------------------------------------- #
# numeri / valute / delta
# --------------------------------------------------------------------------- #
def _fmt_number(value: float, dec_sep: str, th_sep: str, decimals: int = 2) -> str:
    """Formatta un numero con separatori arbitrari (parte da quelli di Python)."""
    base = "{:,.{d}f}".format(value, d=decimals)  # es. 1,234.56
    return base.replace(",", "\x00").replace(".", dec_sep).replace("\x00", th_sep)


def format_money(value: Optional[float], currency: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cur = (currency or "").upper()
    if cur == "EUR":
        return "{} €".format(_fmt_number(value, ",", "."))
    if cur == "USD":
        return "${}".format(_fmt_number(value, ".", ","))
    if cur == "GBP":
        return "£{}".format(_fmt_number(value, ".", ","))
    if cur == "JPY":
        return "¥{}".format(_fmt_number(value, ".", ",", decimals=0))
    return "{} {}".format(_fmt_number(value, ",", "."), cur).strip()


def format_delta(pct: Optional[float]) -> str:
    """'▲ +3,4% (7g)' / '▼ -12,6% (7g)' / '→ 0% (7g)'. Vuoto se assente."""
    if pct is None:
        return ""
    rounded = round(float(pct), 1)
    if rounded == 0:
        return "→ 0% (7g)"
    arrow = "▲" if rounded > 0 else "▼"
    sign = "+" if rounded > 0 else "-"
    num = _fmt_number(abs(rounded), ",", ".", decimals=1)
    return "{} {}{}% (7g)".format(arrow, sign, num)


def product_kind_label(kind: Optional[str]) -> Optional[str]:
    if not kind:
        return None
    return PRODUCT_KIND_LABELS.get(kind, kind.replace("_", " ").title())


# --------------------------------------------------------------------------- #
# URL
# --------------------------------------------------------------------------- #
def _with_utm(url: str, utm: str) -> str:
    if not utm:
        return url
    sep = "&" if "?" in url else "?"
    return "{}{}{}".format(url, sep, utm)


def card_url(item: Item, site_base: str, locale: str, utm: str = "") -> str:
    set_seg = item.set_slug or item.set_code
    if not (set_seg and item.set_code and item.number):
        return _with_utm("{}/{}/catalog".format(site_base, locale), utm)
    # segmento carta = setCode minuscolo + numero NON modificato (es. lor-TG03)
    card_seg = "{}-{}".format(item.set_code.lower(), item.number)
    url = "{}/{}/catalog/{}/{}".format(
        site_base, locale, quote(set_seg, safe=""), quote(card_seg, safe="")
    )
    return _with_utm(url, utm)


def box_url(item: Item, site_base: str, locale: str, utm: str = "") -> str:
    if not item.sku:
        return _with_utm("{}/{}/catalog".format(site_base, locale), utm)
    url = "{}/{}/catalog/sealed/{}".format(site_base, locale, quote(item.sku, safe=""))
    return _with_utm(url, utm)


def item_url(item: Item, site_base: str, locale: str, utm: str = "") -> str:
    return (card_url if item.kind == "card" else box_url)(item, site_base, locale, utm)


# --------------------------------------------------------------------------- #
# righe descrittive
# --------------------------------------------------------------------------- #
def subtitle(item: Item) -> str:
    """Riga sotto al nome: set/numero/rarità (carte) o tipo prodotto (box)."""
    parts = []
    if item.kind == "card":
        if item.set_name or item.set_code:
            parts.append(item.set_name or item.set_code)
        if item.number:
            parts.append("#{}".format(item.number))
        if item.rarity:
            parts.append(item.rarity)
    else:
        parts.append("Sigillato")
        kind = product_kind_label(item.product_kind)
        if kind:
            parts.append(kind)
        if item.set_name:
            parts.append(item.set_name)
    return " · ".join(p for p in parts if p)


def price_line(
    item: Item,
    value: Optional[float] = None,
    currency: Optional[str] = None,
) -> str:
    v = item.price if value is None else value
    c = item.currency if currency is None else currency
    money = format_money(v, c)
    if money is None:
        return PRICE_UNAVAILABLE
    delta = format_delta(item.delta_pct)
    return "<b>{}</b>{}".format(escape(money), "  " + delta if delta else "")


# --------------------------------------------------------------------------- #
# messaggio completo
# --------------------------------------------------------------------------- #
def render_message(
    item: Item,
    disp_value: Optional[float] = None,
    disp_currency: Optional[str] = None,
) -> str:
    """HTML del corpo messaggio per una carta/box (parse_mode=HTML).

    Solo contenuto (nome, sottotitolo, prezzo). Il link a RareBit è gestito
    come bottone URL dagli handler, l'immagine come anteprima. `disp_value`/
    `disp_currency` permettono di mostrare il prezzo già convertito in euro.
    """
    sub = subtitle(item)
    lines = ["<b>{}</b>".format(escape(item.name))]
    if sub:
        lines.append(escape(sub))
    lines.append("")
    lines.append(price_line(item, disp_value, disp_currency))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# testo per i risultati inline (no HTML)
# --------------------------------------------------------------------------- #
def inline_title(item: Item) -> str:
    if item.set_name or item.set_code:
        return "{} · {}".format(item.name, item.set_name or item.set_code)
    return item.name


def inline_description(
    item: Item,
    disp_value: Optional[float] = None,
    disp_currency: Optional[str] = None,
) -> str:
    bits = []
    v = item.price if disp_value is None else disp_value
    c = item.currency if disp_currency is None else disp_currency
    money = format_money(v, c)
    bits.append(money if money else "prezzo n/d")
    delta = format_delta(item.delta_pct)
    if delta:
        bits.append(delta)
    if item.kind == "card" and item.number:
        bits.append("#{}".format(item.number))
    kind = product_kind_label(item.product_kind) if item.kind == "box" else None
    if kind:
        bits.append(kind)
    return " · ".join(bits)
