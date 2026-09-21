"""Live audit: exactly one search, prices, 7d stats and account lookup (5 credits).

Run manually with PTCG_API_KEY exported. Does not load .env or a Telegram token.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tcgbot.core.api import PTCGAPI, card_headline
from tcgbot.core.config import load_core_config
from tcgbot.core.formatting import render_quota


async def main():
    cfg = load_core_config()
    api = PTCGAPI(cfg.api_key, cfg.api_base, cfg.http_timeout)
    try:
        # Explicit field query avoids the separate set-index warmup.
        response = await api._get_json('cards', {
            'q': 'name:charizard number:125', 'limit': 25, 'include': 'set,images'})
        cards = response['data']
        if not cards:
            raise RuntimeError('Smoke search returned no cards')
        card = cards[0]
        print('Card:', card['id'], card['name'])
        print('Current value:', card_headline(await api.prices('card', card['id'])))
        print('7d stats:', await api.stats(card['id']))
        print(render_quota(await api.me()))
    finally:
        print('Credits spent (X-Credits-Cost):', api.credits_spent)
        print('Last quota headers:', api.quota_headers)
        await api.aclose()


if __name__ == '__main__':
    asyncio.run(main())
