"""Test della conversione valute pura (niente rete)."""

from tcgbot.core.fx import convert_amount

RATES = {"EUR": 1.0, "USD": 1.1467, "JPY": 184.88, "GBP": 0.86653}


def test_usd_to_eur():
    val, cur = convert_amount(135.09, "USD", "EUR", RATES)
    assert cur == "EUR"
    assert round(val, 2) == 117.81


def test_jpy_to_eur():
    val, cur = convert_amount(1848.8, "JPY", "EUR", RATES)
    assert cur == "EUR"
    assert round(val, 2) == 10.00


def test_same_currency_noop():
    assert convert_amount(50.0, "EUR", "EUR", RATES) == (50.0, "EUR")


def test_missing_rate_returns_original():
    assert convert_amount(10.0, "CHF", "EUR", RATES) == (10.0, "CHF")


def test_no_rates_returns_original():
    assert convert_amount(10.0, "USD", "EUR", None) == (10.0, "USD")


def test_none_value():
    assert convert_amount(None, "USD", "EUR", RATES) == (None, "USD")
