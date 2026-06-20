"""Test della cascata current value (card_headline), come il sito."""

from rarebit_bot.api import card_headline


def _detail(cm=None, tcg=None, ct=None):
    pb = {}
    if cm is not None:
        pb["cardmarket"] = {"languages": cm}
    if tcg is not None:
        pb["tcgplayer"] = tcg
    if ct is not None:
        pb["cardtrader"] = {"languages": ct}
    return {"priceBoard": pb}


WEST = [
    {"language": "en", "price": 26, "currency": "EUR", "d7d": 4},
    {"language": "it", "price": 23.99, "currency": "EUR", "d7d": 9},
]


def test_jp_tcgplayer_max_listing_over_market():
    # caso reale Altaria ex SV4M 090: market 57.12, lowest 75 → headline 75
    d = _detail(cm=[], tcg={"price": 57.12, "lowestListing": 75, "currency": "USD", "d7d": None})
    assert card_headline(d, "en") == (75.0, "USD", None, None)


def test_jp_market_only_no_listing():
    d = _detail(tcg={"price": 57.12, "lowestListing": None, "currency": "USD", "d7d": 3.4})
    assert card_headline(d, "en") == (57.12, "USD", 3.4, None)


def test_west_requested_language():
    assert card_headline(_detail(cm=WEST), "en") == (26.0, "EUR", 4, "en")


def test_west_global_lowest_when_no_language():
    assert card_headline(_detail(cm=WEST), None) == (23.99, "EUR", 9, None)


def test_west_requested_language_missing_falls_to_lowest():
    assert card_headline(_detail(cm=WEST), "de") == (23.99, "EUR", 9, None)


def test_cardtrader_last_fallback():
    d = _detail(cm=[], tcg={}, ct=[{"language": "en", "price": 13.33, "currency": "EUR"}])
    assert card_headline(d, "en") == (13.33, "EUR", None, None)


def test_empty():
    assert card_headline(None, "en") == (None, None, None, None)
    assert card_headline({}, "en") == (None, None, None, None)
