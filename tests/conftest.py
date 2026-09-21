import json
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def fixture():
    def load(name):
        return json.loads((Path(__file__).parent / 'fixtures' / (name + '.json')).read_text())
    return load


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def blocked(*args, **kwargs):
        raise AssertionError('Tests must not use the network')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', blocked)
