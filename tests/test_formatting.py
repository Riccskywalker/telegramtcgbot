import pytest
from tcgbot.core.api import Item
from tcgbot.core import formatting as f


@pytest.mark.parametrize('amount,currency,expected', [
    (23.99, 'EUR', '€23.99'), (1234.56, 'EUR', '€1,234.56'),
    (23.22, 'USD', '$23.22'), (1234.56, 'USD', '$1,234.56'),
    (53771, 'JPY', '¥53,771'), (None, 'EUR', None)])
def test_money(amount, currency, expected):
    assert f.format_money(amount, currency) == expected


@pytest.mark.parametrize('value,expected', [(-4.03022, '7d −4.0%'), (11.4, '7d +11.4%'),
                                           (0, '7d 0.0%'), (None, '')])
def test_delta(value, expected):
    assert f.format_delta(value) == expected


def card():
    return Item(kind='card', id='obf-125', name='Charizard ex', number='125',
                price=3.81, currency='EUR', delta_pct=-4.03, as_of='2026-09-21',
                rarity='Double Rare', set_name='Obsidian Flames')


def test_render_price():
    msg = f.render_message(card())
    assert '<b>Charizard ex</b>' in msg
    assert 'Current value <b>€3.81</b> (as of 2026-09-21) · 7d −4.0%' in msg
    assert 'http' not in msg and '<a ' not in msg


def test_no_price():
    item = card()
    item.price = None
    assert 'Current value unavailable' in f.render_message(item)
    assert 'Current value' not in f.render_message(card(), with_price=False)
    assert '7d' not in f.inline_description(card())


def test_quotes(fixture):
    item = card()
    item.quotes = fixture('card-prices-lor-125')['data']['quotes']
    msg = f.render_message(item)
    assert 'Cardmarket 7d avg: €0.04' in msg
    assert 'TCGplayer Market: $0.11' in msg


def test_subtitles_and_escaping():
    item = card()
    item.name = 'Farfetch\'d <test> & co'
    assert '&lt;test&gt; &amp;' in f.render_message(item)
    assert f.subtitle(item) == 'Obsidian Flames · #125 · Double Rare'
    assert f.subtitle(Item(kind='box', id='x', name='x', product_kind='ETB', set_name='151')) == 'Sealed · Elite Trainer Box · 151'
    assert f.product_kind_label('BOOSTER_BOX') == 'Booster Box'
    assert f.product_kind_label(None) is None


def test_quota_shape():
    result = f.render_quota({'plan': {'name': 'Trial'}, 'quota': {
        'credits_limit': 800, 'credits_used': 8, 'credits_remaining': 792,
        'daily_cap': 400, 'daily_used': 8, 'period_seq': 1,
        'period_start': '2026-09-01T00:00:00.000Z', 'resets_at': '2026-10-01T00:00:00.000Z',
        'renews': False, 'trial_expires_at': '2026-10-20T16:17:55.246Z',
        'trial_expired': False, 'overage_enabled': False, 'stale': False}})
    assert result == ('Plan: Trial\nCredits: 8 / 800 (792 remaining)\nDaily cap: 8 / 400 today\n'
                      'Trial expiry: 2026-10-20T16:17:55.246Z\n'
                      'Current period ends: 2026-10-01T00:00:00.000Z (trial credits do not renew)')
    assert 'Daily cap: none' in f.render_quota({'quota': {'daily_cap': None}})


@pytest.mark.parametrize('quota,expected', [
    ({'renews': False, 'trial_expires_at': '2026-10-20T16:17:55.246Z', 'trial_expired': True},
     'Trial expiry: 2026-10-20T16:17:55.246Z (expired)'),
    ({'renews': True}, 'Trial expiry: not applicable'),
    ({'renews': False}, 'Trial expiry: not provided'),
    ({}, 'Trial expiry: not provided'),
])
def test_quota_trial_expiry(quota, expected):
    assert expected in f.render_quota({'quota': quota}).splitlines()


def test_quota_zero_usage_and_remaining():
    result = f.render_quota({'quota': {'credits_used': 80, 'credits_limit': 80,
        'credits_remaining': 0, 'daily_used': 0, 'daily_cap': 40}})
    assert 'Credits: 80 / 80 (0 remaining)' in result
    assert 'Daily cap: 0 / 40 today' in result
