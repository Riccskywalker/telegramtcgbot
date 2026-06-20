"""Test delle funzioni pure: nessuna rete, nessun Telegram."""

from rarebit_bot.api import Item, headline_from_board
from rarebit_bot import formatting as f

NBSP = chr(0x00A0)  # spazio insecabile usato tra numero e simbolo valuta


def _norm(s):
    """Normalizza il nbsp a spazio per asserzioni leggibili."""
    return None if s is None else s.replace(NBSP, " ")


# --- valute ---------------------------------------------------------------- #
def test_money_eur_it_style():
    assert _norm(f.format_money(23.99, "EUR")) == "23,99 €"
    assert _norm(f.format_money(1234.56, "EUR")) == "1.234,56 €"


def test_money_usd():
    assert f.format_money(23.22, "USD") == "$23.22"
    assert f.format_money(1234.56, "USD") == "$1,234.56"


def test_money_jpy_no_decimals():
    assert f.format_money(53771, "JPY") == "¥53,771"


def test_money_none():
    assert f.format_money(None, "EUR") is None


# --- delta ----------------------------------------------------------------- #
def test_delta_negative():
    assert f.format_delta(-12.6047) == "▼ -12,6% (7g)"


def test_delta_positive():
    assert f.format_delta(11.4) == "▲ +11,4% (7g)"


def test_delta_zero_and_none():
    assert f.format_delta(0) == "→ 0% (7g)"
    assert f.format_delta(None) == ""


# --- url ------------------------------------------------------------------- #
def _card():
    return Item(
        kind="card", id="x", name="Charizard",
        set_code="LOR", set_slug="lost-origin", number="TG03",
        price=23.99, currency="EUR", delta_pct=-12.6,
        rarity="Trainer Gallery Rare Holo", set_name="Lost Origin",
    )


def test_card_url_lowercases_setcode_but_keeps_number_case():
    # canonico: setCode minuscolo, numero invariato → lor-TG03
    url = f.card_url(_card(), "https://rarebit.app", "it", utm="")
    assert url == "https://rarebit.app/it/catalog/lost-origin/lor-TG03"


def test_card_url_falls_back_to_setcode_when_no_slug():
    it = _card()
    it.set_slug = None
    url = f.card_url(it, "https://rarebit.app", "it", utm="")
    assert url == "https://rarebit.app/it/catalog/LOR/lor-TG03"


def test_card_url_utm_appended():
    url = f.card_url(_card(), "https://rarebit.app", "it", utm="utm_source=telegram")
    assert url.endswith("?utm_source=telegram")


def test_box_url():
    box = Item(kind="box", id="y", name="Charizard ex Box", sku="charizard-ex-box")
    url = f.box_url(box, "https://rarebit.app", "it", utm="")
    assert url == "https://rarebit.app/it/catalog/sealed/charizard-ex-box"


def test_url_without_enough_data_falls_back_to_catalog():
    bare = Item(kind="card", id="z", name="??")
    assert f.card_url(bare, "https://rarebit.app", "it") == "https://rarebit.app/it/catalog"


# --- testo ----------------------------------------------------------------- #
def test_subtitle_card():
    assert f.subtitle(_card()) == "Lost Origin · #TG03 · Trainer Gallery Rare Holo"


def test_subtitle_box():
    box = Item(kind="box", id="y", name="x", product_kind="ETB", set_name="151")
    assert f.subtitle(box) == "Sigillato · Elite Trainer Box · 151"


def test_render_message_has_bold_name_and_price():
    msg = _norm(f.render_message(_card()))
    assert "<b>Charizard</b>" in msg
    assert "<b>23,99 €</b>" in msg
    assert "▼ -12,6% (7g)" in msg


def test_render_message_price_unavailable():
    it = _card()
    it.price = None
    assert "non ancora disponibile" in f.render_message(it)


def test_escaping_in_name():
    it = _card()
    it.name = "Farfetch'd <test> & co"
    msg = f.render_message(it)
    assert "&lt;test&gt;" in msg and "&amp;" in msg


# --- product kind ---------------------------------------------------------- #
def test_product_kind_label_known_and_fallback():
    assert f.product_kind_label("BOOSTER_BOX") == "Booster Box"
    assert f.product_kind_label("WEIRD_KIND") == "Weird Kind"
    assert f.product_kind_label(None) is None


# --- headline dal board ---------------------------------------------------- #
def test_headline_global_lowest():
    board = {"cardmarket": {"languages": [
        {"price": 40, "currency": "EUR"},
        {"price": 12, "currency": "EUR"},
        {"price": 399.9, "currency": "EUR"},
    ]}}
    assert headline_from_board(board) == (12.0, "EUR")


def test_headline_tcgplayer_fallback():
    board = {"cardmarket": {"languages": []}, "tcgplayer": {"price": 23.22, "currency": "EUR"}}
    assert headline_from_board(board) == (23.22, "EUR")


def test_headline_empty():
    assert headline_from_board(None) == (None, None)
    assert headline_from_board({}) == (None, None)
