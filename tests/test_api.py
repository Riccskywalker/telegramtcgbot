import asyncio
import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from tcgbot.core.api import PTCGAPI, APIError, Item, retry_delay
from tcgbot.core.cache import HTTPCache, PRICE_TTL, SET_TTL, DETAIL_TTL
from tcgbot.core.config import USER_AGENT
from tcgbot.telegram.texts import api_error, QUOTA_EXHAUSTED


def run(coro):
    return asyncio.run(coro)


def test_budget_and_repeated_search(fixture):
    calls = []
    def handler(req):
        calls.append(req)
        assert req.headers['X-Api-Key'] == 'test-key'
        assert req.headers['User-Agent'] == USER_AGENT
        if req.url.path == '/v1/sets':
            return httpx.Response(200, json={'data': [], 'links': {}}, headers={'X-Credits-Cost': '1'})
        if req.url.path == '/v1/cards':
            assert dict(req.url.params) == {'q': 'name:charizard number:125', 'limit': '25', 'include': 'set,images'}
            data, cost = fixture('cards-search-charizard-125'), 1
        elif req.url.path.endswith('/prices/stats'):
            assert req.url.params['window'] == '7d'
            data, cost = fixture('card-prices-stats-obf-125'), 2
        elif req.url.path.endswith('/prices'):
            data, cost = fixture('card-prices-lor-125'), 2
        else:
            pytest.fail(str(req.url))
        return httpx.Response(200, json=data, headers={'X-Credits-Cost': str(cost), 'ETag': '"v1"'})
    async def scenario():
        api = PTCGAPI('test-key', transport=httpx.MockTransport(handler))
        await api.set_index()  # One-time catalogue setup is outside per-lookup cost.
        before = api.credits_spent
        items = await api.search_cards('charizard 125')
        assert api.credits_spent - before == 1
        assert items[0].image_url == fixture('cards-search-charizard-125')['data'][0]['images'][0]['url']
        assert items[0].price is None
        item = await api.priced_item(items[0])
        assert item.delta_pct == fixture('card-prices-stats-obf-125')['data']['change_pct']
        assert api.credits_spent - before == 5
        count = len(calls)
        again = await api.search_cards('charizard 125')
        assert await api.priced_item(again[0]) == item
        assert len(calls) == count
        await api.aclose()
    run(scenario())


def test_sealed_never_requests_stats(fixture):
    calls = []
    def handler(req):
        calls.append(req)
        if req.url.path == '/v1/sealed':
            assert dict(req.url.params) == {'q': 'lost origin', 'limit': '25'}
            data, cost = fixture('sealed-search'), 1
        elif req.url.path == '/v1/sealed/lost-origin-booster-box/prices':
            data, cost = fixture('sealed-prices'), 2
        else:
            pytest.fail(str(req.url))
        return httpx.Response(200, json=data, headers={'X-Credits-Cost': str(cost)})
    async def scenario():
        api = PTCGAPI('test', transport=httpx.MockTransport(handler))
        items = await api.search_boxes('lost origin')
        item = await api.priced_item(items[0])
        assert item.price == 595
        assert item.delta_pct == pytest.approx((595 / 427.83 - 1) * 100)
        assert api.credits_spent == 3
        assert len(calls) == 2
        await api.aclose()
    run(scenario())


def test_etag_304_zero_credits_and_internal_ttl():
    now, calls = [0], []
    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            assert 'If-None-Match' not in req.headers
            return httpx.Response(200, json={'data': {'value': 12}}, headers={'ETag': '"one"', 'X-Credits-Cost': '2'})
        assert req.headers['If-None-Match'] == '"one"'
        return httpx.Response(304, headers={'X-Credits-Cost': '0', 'ETag': '"one"'})
    async def scenario():
        api = PTCGAPI('test', transport=httpx.MockTransport(handler), cache=HTTPCache(clock=lambda: now[0]))
        body = await api._get_json('cards/x/prices', ttl=PRICE_TTL)
        now[0] = PRICE_TTL - 1
        assert await api._get_json('cards/x/prices') == body
        assert len(calls) == 1
        now[0] += 1
        assert await api._get_json('cards/x/prices') == body
        assert api.credits_spent == 2 and len(calls) == 2
        assert await api._get_json('cards/x/prices') == body
        assert len(calls) == 2
        await api.aclose()
    run(scenario())


def test_paginated_sets_refresh_after_24h(fixture):
    now, calls = [0], []
    first = fixture('sets-page')
    second_url = first['links']['next']
    def handler(req):
        calls.append(req)
        if 'If-None-Match' in req.headers:
            return httpx.Response(304, headers={'X-Credits-Cost': '0'})
        data = first if req.url.params.get('limit') == '250' else {'data': [{'code': 'lor', 'name': 'Lost Origin'}]}
        return httpx.Response(200, json=data, headers={'ETag': '"sets"', 'X-Credits-Cost': '1'})
    async def scenario():
        api = PTCGAPI('test', transport=httpx.MockTransport(handler), cache=HTTPCache(clock=lambda: now[0]))
        idx = await api.set_index()
        assert idx.by_code['lor'].name == 'Lost Origin'
        assert str(calls[1].url) == second_url
        assert idx.by_code['30c'].region == 'WEST'
        assert await api.set_index() is idx
        assert len(calls) == 2
        now[0] = SET_TTL
        assert (await api.set_index()).by_code['lor'].name == 'Lost Origin'
        assert len(calls) == 4 and api.credits_spent == 2
        await api.aclose()
    run(scenario())


@pytest.mark.parametrize('status,code,details,expected', [
    (401, 'UNAUTHORIZED', {}, 'The bot is misconfigured (API key). The owner has been notified in the log.'),
    (401, 'INVALID_API_KEY', {}, 'The bot is misconfigured (API key). The owner has been notified in the log.'),
    (429, 'QUOTA_EXCEEDED', {'next_step': {'handoff': 'Please verify the owner email.'}}, 'Please verify the owner email.'),
    (402, 'TRIAL_EXHAUSTED', {}, QUOTA_EXHAUSTED),
    (429, 'DAILY_CAP_EXCEEDED', {}, QUOTA_EXHAUSTED),
    (403, 'EMAIL_UNVERIFIED', {}, QUOTA_EXHAUSTED),
    (404, 'CARD_NOT_FOUND', {}, 'Nothing found.'),
    (500, 'INTERNAL_ERROR', {}, 'There was a problem fetching the data.'),
])
def test_api_errors(status, code, details, expected, caplog):
    def handler(req):
        return httpx.Response(status, json={'error': {'code': code, 'request_id': 'request-123', 'details': details}})
    async def scenario():
        api = PTCGAPI('test', transport=httpx.MockTransport(handler))
        with pytest.raises(APIError) as exc:
            await api.prices('card', 'obf-125')
        assert api_error(exc.value).startswith(expected)
        assert 'request-123' in caplog.text
        assert api.credits_spent == 0
        if status == 401:
            assert any(r.levelno == logging.ERROR for r in caplog.records)
        await api.aclose()
    run(scenario())


@pytest.mark.parametrize('succeeds', [True, False])
def test_rate_limited_one_retry(succeeds):
    calls, sleep = [], AsyncMock()
    def handler(req):
        calls.append(req)
        if succeeds and len(calls) == 2:
            return httpx.Response(200, json={'data': {}}, headers={'X-Credits-Cost': '2'})
        return httpx.Response(429, json={'error': {'code': 'RATE_LIMITED'}}, headers={'Retry-After': '3'})
    async def scenario():
        api = PTCGAPI('test', transport=httpx.MockTransport(handler), sleep=sleep)
        if succeeds:
            await api.prices('card', 'obf-125')
        else:
            with pytest.raises(APIError) as exc:
                await api.prices('card', 'obf-125')
            assert 'try again in a moment' in api_error(exc.value)
        assert len(calls) == 2
        sleep.assert_awaited_once_with(3)
        await api.aclose()
    run(scenario())


def test_warning_throttled_and_headers(caplog):
    now = [0]
    headers = {'X-Credits-Cost': '0', 'X-Quota-Remaining': '49', 'X-Quota-Limit': '800', 'RateLimit-Remaining': '1'}
    async def scenario():
        api = PTCGAPI('test', cache=HTTPCache(clock=lambda: now[0]),
                      transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'data': {}}, headers=headers)))
        with caplog.at_level(logging.DEBUG):
            await api.me()
            await api.me()
            now[0] = 3600
            await api.me()
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2
        assert api.quota_headers == headers
        assert 'RateLimit-Remaining' in caplog.text
        await api.aclose()
    run(scenario())


def test_cross_host_pagination_does_not_leak_key():
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200, json={'data': [], 'links': {'next': 'https://elsewhere.example/v1/sets'}})
    async def scenario():
        api = PTCGAPI('test', transport=httpx.MockTransport(handler))
        with pytest.raises(APIError, match='INVALID_PAGINATION_URL'):
            await api.set_index()
        assert len(requests) == 1
        await api.aclose()
    run(scenario())


def test_detail_include_and_ttl(fixture):
    now, calls = [0], []
    def handler(req):
        calls.append(req)
        assert dict(req.url.params) == {'include': 'set,images'}
        return httpx.Response(200, json={'data': fixture('cards-search-charizard-125')['data'][0]})
    async def scenario():
        api = PTCGAPI('test', cache=HTTPCache(clock=lambda: now[0]), transport=httpx.MockTransport(handler))
        await api.resolve('card', 'obf-125')
        api._items.clear()
        now[0] = DETAIL_TTL - 1
        await api.resolve('card', 'obf-125')
        assert len(calls) == 1
        api._items.clear()
        now[0] += 1
        await api.resolve('card', 'obf-125')
        assert len(calls) == 2
        await api.aclose()
    run(scenario())


def test_lru_and_simultaneous_requests():
    calls = []
    async def fetch(etag):
        calls.append(etag)
        await asyncio.sleep(0)
        return httpx.Response(200, request=httpx.Request('GET', 'https://example.test'), json={'ok': True})
    async def scenario():
        cache = HTTPCache(maxsize=2)
        await asyncio.gather(cache.get('a', 10, fetch), cache.get('a', 10, fetch))
        assert len(calls) == 1
        await cache.get('b', 10, fetch)
        await cache.get('a', 10, fetch)
        await cache.get('c', 10, fetch)
        assert list(cache.entries) == ['a', 'c']
    run(scenario())
