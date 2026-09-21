"""Authenticated catalogue and pricing client, independent of chat transports."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote

import httpx
from cachetools import TTLCache

from .cache import HTTPCache, SEARCH_TTL, PRICE_TTL, DETAIL_TTL, SET_TTL
from .config import API_BASE, USER_AGENT
from .search import SetIndex, parse_query, rank, tokens

logger = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(self, status: int, code: str, request_id: str = '', details=None):
        super().__init__(code)
        self.status, self.code, self.request_id = status, code, request_id
        self.details = details or {}


@dataclass
class Item:
    kind: str
    id: str
    name: str
    image_url: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    delta_pct: Optional[float] = None
    as_of: Optional[str] = None
    locale: Optional[str] = None
    number: Optional[str] = None
    rarity: Optional[str] = None
    set_code: Optional[str] = None
    set_name: Optional[str] = None
    product_kind: Optional[str] = None
    quotes: list = field(default_factory=list)


@dataclass(frozen=True)
class Headline:
    value: Optional[float] = None
    currency: Optional[str] = None
    as_of: Optional[str] = None
    locale: Optional[str] = None


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def select_quote(quotes, source, variant, locale=None, currency=None):
    candidates = [q for q in quotes if q.get('source') == source
                  and q.get('variant') == variant and _numeric(q.get('amount'))
                  and not q.get('grading')
                  and (not currency or q.get('currency') == currency)
                  and (not locale or q.get('locale') in (locale, None))]
    return min(candidates, key=lambda q: (q.get('locale') != locale if locale else False,
                                         0 if q.get('printing') == 'NORMAL' else
                                         1 if q.get('printing') is None else 2), default=None)


def card_headline(data: Optional[dict], language: Optional[str] = None) -> Headline:
    """Prefer the requested normal printing, then the EUR index, then USD market."""
    data = data or {}
    index = data.get('index') or {}
    if language:
        rows = [r for r in index.get('by_locale', [])
                if r.get('locale') == language and r.get('printing') in ('NORMAL', None)
                and _numeric(r.get('eur'))]
        if rows:
            row = min(rows, key=lambda r: r.get('printing') != 'NORMAL')
            return Headline(float(row['eur']), 'EUR', row.get('as_of'), language)
    if _numeric(index.get('eur')):
        return Headline(float(index['eur']), 'EUR', index.get('as_of'))
    q = select_quote(data.get('quotes') or [], 'TCGPLAYER', 'MARKET', currency='USD')
    if q:
        return Headline(float(q['amount']), 'USD', q.get('as_of'), q.get('locale'))
    return Headline()


def _item(raw: dict, kind: str) -> Item:
    s = raw.get('set') or {}
    images = raw.get('images') or []
    return Item(kind=kind, id=raw['id'], name=raw.get('name') or 'Unknown',
                image_url=images[0].get('url') if images else raw.get('image_url'),
                number=raw.get('number'), rarity=raw.get('rarity'),
                set_code=raw.get('set_code') or s.get('code'),
                set_name=raw.get('set_name') or s.get('name'), product_kind=raw.get('kind'))


def retry_delay(value: Optional[str]) -> float:
    try:
        return max(0.0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 1.0


class PTCGAPI:
    def __init__(self, api_key: str, base_url: str = API_BASE, timeout: float = 8.0,
                 *, transport=None, cache=None, sleep=asyncio.sleep):
        if not api_key.strip():
            raise ValueError('PTCG_API_KEY is required: https://pokemontcgapi.com/free-api-key')
        self._client = httpx.AsyncClient(base_url=base_url.rstrip('/') + '/', timeout=timeout,
            headers={'X-Api-Key': api_key, 'User-Agent': USER_AGENT, 'Accept': 'application/json'},
            transport=transport)
        self.cache = cache if cache is not None else HTTPCache()
        self._items = TTLCache(maxsize=2000, ttl=SEARCH_TTL)
        self._set_index = None
        self._set_expires = 0
        self._set_lock = asyncio.Lock()
        self._last_warning = float('-inf')
        self._sleep = sleep
        self.credits_spent = 0
        self.quota_headers = {}

    async def aclose(self):
        await self._client.aclose()

    def _meter(self, response):
        names = ('X-Credits-Cost', 'X-Quota-Remaining', 'X-Quota-Limit', 'RateLimit-Remaining')
        self.quota_headers = {n: response.headers.get(n) for n in names}
        logger.debug('API credits: %s', self.quota_headers)
        cost = response.headers.get('X-Credits-Cost')
        if cost and cost.isdigit() and response.is_success:
            self.credits_spent += int(cost)
        remaining = response.headers.get('X-Quota-Remaining')
        now = self.cache.clock()
        if remaining and remaining.isdigit() and int(remaining) < 50 and now - self._last_warning >= 3600:
            logger.warning('API quota is low: %s credits remaining', remaining)
            self._last_warning = now

    async def _get_json(self, path, params=None, ttl=SEARCH_TTL):
        url = self._client.build_request('GET', path, params=params).url
        # Pagination URLs must never send the key to a different host or API root.
        base = self._client.base_url
        if (url.scheme, url.host, url.port) != (base.scheme, base.host, base.port) or not url.path.startswith(base.path):
            raise APIError(0, 'INVALID_PAGINATION_URL')

        async def fetch(etag):
            for attempt in range(2):
                response = await self._client.get(url, headers={'If-None-Match': etag} if etag else {})
                self._meter(response)
                if response.is_success or response.status_code == 304:
                    return response
                try:
                    error = response.json().get('error') or {}
                except (ValueError, AttributeError):
                    error = {}
                code = error.get('code', 'UNKNOWN')
                request_id = error.get('request_id') or response.headers.get('X-Request-Id', '')
                logger.log(logging.ERROR if response.status_code == 401 else logging.WARNING,
                           'API HTTP %s code=%s request_id=%s', response.status_code, code, request_id)
                if response.status_code == 429 and code == 'RATE_LIMITED' and attempt == 0:
                    await self._sleep(retry_delay(response.headers.get('Retry-After')))
                    continue
                raise APIError(response.status_code, code, request_id, error.get('details'))

        if ttl == 0:
            return (await fetch(None)).json()
        return await self.cache.get(str(url), ttl, fetch)

    async def set_index(self):
        async with self._set_lock:
            if self._set_index is not None and self.cache.clock() < self._set_expires:
                return self._set_index
            raw, seen = [], set()
            path, params = 'sets', {'limit': 250}
            while path:
                if path in seen:
                    raise APIError(0, 'PAGINATION_LOOP')
                seen.add(path)
                body = await self._get_json(path, params, SET_TTL)
                raw.extend(body['data'])
                path, params = (body.get('links') or {}).get('next'), None
            self._set_index = SetIndex.build(raw)
            self._set_expires = self.cache.clock() + SET_TTL
            return self._set_index

    async def search_cards(self, query, limit=6):
        parsed = parse_query(query, await self.set_index())
        body = await self._get_json('cards', {'q': parsed.q, 'limit': 25, 'include': 'set,images'})
        items = [_item(raw, 'card') for raw in body['data']]
        for item in items:
            self._items[(item.kind, item.id)] = item
        return rank(items, parsed)[:limit]

    async def search_boxes(self, query, limit=6):
        body = await self._get_json('sealed', {'q': query, 'limit': 25})
        items = [_item(raw, 'box') for raw in body['data']]
        for item in items:
            self._items[(item.kind, item.id)] = item
        qt = tokens(query)
        return sorted(items, key=lambda it: -sum(t in tokens(it.name) for t in qt))[:limit]

    async def resolve(self, kind, item_id):
        cached = self._items.get((kind, item_id))
        if cached is not None:
            return cached
        resource = 'cards' if kind == 'card' else 'sealed'
        params = {'include': 'set,images'} if kind == 'card' else None
        body = await self._get_json(f'{resource}/{quote(item_id, safe="")}', params, DETAIL_TTL)
        item = _item(body['data'], kind)
        self._items[(kind, item.id)] = item
        return item

    async def prices(self, kind, item_id):
        resource = 'cards' if kind == 'card' else 'sealed'
        return (await self._get_json(f'{resource}/{quote(item_id, safe="")}/prices', ttl=PRICE_TTL))['data']

    async def stats(self, item_id, locale=None):
        params = {'window': '7d'}
        if locale:
            params['locale'] = locale
        return (await self._get_json(f'cards/{quote(item_id, safe="")}/prices/stats', params, PRICE_TTL))['data']

    async def priced_item(self, item, language=None, *, with_stats=True):
        data = await self.prices(item.kind, item.id)
        headline = card_headline(data, language)
        quotes = data.get('quotes') or []
        delta = None
        if item.kind == 'card' and with_stats:
            delta = (await self.stats(item.id, headline.locale)).get('change_pct')
        elif item.kind == 'box':
            avg = select_quote(quotes, 'CARDMARKET', 'AVG_7D', headline.locale, 'EUR')
            if avg and avg['amount'] > 0 and headline.value is not None and headline.currency == 'EUR':
                delta = (headline.value / avg['amount'] - 1) * 100
        return replace(item, price=headline.value, currency=headline.currency, as_of=headline.as_of,
                       locale=headline.locale, delta_pct=delta, quotes=quotes)

    async def me(self):
        return (await self._get_json('me', ttl=0))['data']
