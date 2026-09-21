"""API configuration shared by any chat entry point."""
from dataclasses import dataclass, field
import os

API_BASE = 'https://api.pokemontcgapi.com/v1'
USER_AGENT = 'telegramtcgbot/0.2 (+https://pokemontcgapi.com)'


@dataclass(frozen=True)
class CoreConfig:
    api_key: str = field(repr=False)
    api_base: str = API_BASE
    http_timeout: float = 8.0


def load_core_config() -> CoreConfig:
    key = os.getenv('PTCG_API_KEY', '').strip()
    if not key:
        raise RuntimeError('PTCG_API_KEY is required. Get a free key at '
                           'https://pokemontcgapi.com/free-api-key and verify your email.')
    return CoreConfig(api_key=key, api_base=os.getenv('PTCG_API_BASE', API_BASE).rstrip('/'))
