"""Bounded HTTP cache. Expired bodies survive for free ETag revalidation."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import httpx

SEARCH_TTL = PRICE_TTL = 6 * 3600
DETAIL_TTL = SET_TTL = 24 * 3600


@dataclass
class Entry:
    body: Any
    etag: Optional[str]
    expires: float


class HTTPCache:
    def __init__(self, maxsize: int = 2000, clock: Callable = time.monotonic):
        self.maxsize = maxsize
        self.clock = clock
        self.entries: OrderedDict[str, Entry] = OrderedDict()
        # Coalesce overlapping lookups, including the first request for a URL.
        self._lock = asyncio.Lock()

    async def get(self, url: str, ttl: float,
                  fetch: Callable[[Optional[str]], Awaitable[httpx.Response]]) -> Any:
        async with self._lock:
            entry = self.entries.get(url)
            if entry:
                self.entries.move_to_end(url)
                if entry.expires > self.clock():
                    return entry.body
            response = await fetch(entry.etag if entry else None)
            if response.status_code == 304 and entry:
                entry.expires = self.clock() + ttl
                entry.etag = response.headers.get('ETag', entry.etag)
                return entry.body
            response.raise_for_status()
            body = response.json()
            self.entries[url] = Entry(body, response.headers.get('ETag'), self.clock() + ttl)
            self.entries.move_to_end(url)
            while len(self.entries) > self.maxsize:
                self.entries.popitem(last=False)
            return body
