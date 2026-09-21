from tcgbot.core.api import card_headline, Headline


def test_index(fixture):
    assert card_headline(fixture('card-prices-lor-125')['data']) == Headline(.05, 'EUR', '2026-09-21')


def test_locale_normal_before_null_or_reverse(fixture):
    data = fixture('card-prices-lor-125')['data']
    data['index']['by_locale'].reverse()
    assert card_headline(data, 'en') == Headline(.05, 'EUR', '2026-09-21', 'en')


def test_locale_null_and_missing(fixture):
    data = fixture('card-prices-lor-125')['data']
    data['index']['by_locale'] = [{'locale': 'it', 'printing': None, 'eur': 1.2, 'as_of': '2026-09-20'}]
    assert card_headline(data, 'it') == Headline(1.2, 'EUR', '2026-09-20', 'it')
    assert card_headline(data, 'de') == Headline(.05, 'EUR', '2026-09-21')


def test_fallback_market_usd(fixture):
    data = fixture('card-prices-lor-125')['data']
    data['index'] = None
    assert card_headline(data) == Headline(.11, 'USD', '2026-09-20', 'en')


def test_empty_and_zero():
    assert card_headline(None) == Headline()
    assert card_headline({'index': None, 'quotes': []}) == Headline()
    assert card_headline({'index': {'eur': 0}}).value == 0


def test_expanded_search_not_a_price_response(fixture):
    # Never use index_eur or expanded list quotes as a cached /prices response.
    assert card_headline(fixture('cards-search-include-prices')['data'][0]) == Headline()


def test_usd_fallback_for_holo_only_card():
    data = {'quotes': [{'source': 'TCGPLAYER', 'variant': 'MARKET', 'printing': 'HOLO',
                         'amount': 5, 'currency': 'USD', 'as_of': '2026-09-20'}]}
    assert card_headline(data) == Headline(5, 'USD', '2026-09-20')
