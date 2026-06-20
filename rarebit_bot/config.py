"""Configurazione del bot, letta da variabili d'ambiente (.env opzionale)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv è comodo ma non indispensabile
    pass


VALID_IMAGE_MODES = ("preview", "photo", "none")


@dataclass(frozen=True)
class Config:
    bot_token: str
    api_base: str = "https://api.rarebit.app/api"
    site_base: str = "https://rarebit.app"
    locale: str = "it"
    image_mode: str = "preview"
    display_currency: str = "EUR"
    default_language: Optional[str] = "en"  # lingua prezzo senza tag (None = global-lowest)
    utm: str = "utm_source=telegram&utm_medium=bot&utm_campaign=lookup"
    cache_ttl: int = 120
    http_timeout: float = 8.0
    inline_limit: int = 10
    command_results: int = 6
    max_alts: int = 5
    log_level: str = "INFO"
    groups_store_path: str = "groups.json"  # file JSON dei gruppi/canali dove il bot è stato aggiunto


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_config(require_token: bool = True) -> Config:
    """Costruisce la Config dall'ambiente.

    `require_token=False` permette di importare/testare senza token impostato.
    """
    token = (os.getenv("RAREBIT_BOT_TOKEN") or "").strip()
    if require_token and not token:
        raise RuntimeError(
            "RAREBIT_BOT_TOKEN non impostato. Mettilo in .env o esportalo "
            "(vedi .env.example)."
        )

    image_mode = (os.getenv("RAREBIT_IMAGE_MODE") or "preview").strip().lower()
    if image_mode not in VALID_IMAGE_MODES:
        image_mode = "preview"

    raw_lang = os.getenv("RAREBIT_DEFAULT_LANGUAGE")
    if raw_lang is None:
        default_language: Optional[str] = "en"  # default: prezzo EN
    else:
        default_language = raw_lang.strip().lower() or None  # vuoto = global-lowest

    return Config(
        bot_token=token,
        api_base=(os.getenv("RAREBIT_API_BASE") or "https://api.rarebit.app/api").rstrip("/"),
        site_base=(os.getenv("RAREBIT_SITE_BASE") or "https://rarebit.app").rstrip("/"),
        locale=(os.getenv("RAREBIT_LOCALE") or "it").strip().lower(),
        image_mode=image_mode,
        display_currency=(os.getenv("RAREBIT_DISPLAY_CURRENCY") or "EUR").strip().upper(),
        default_language=default_language,
        utm=(os.getenv("RAREBIT_UTM") if os.getenv("RAREBIT_UTM") is not None
             else "utm_source=telegram&utm_medium=bot&utm_campaign=lookup"),
        cache_ttl=_int("RAREBIT_CACHE_TTL", 120),
        http_timeout=_float("RAREBIT_HTTP_TIMEOUT", 8.0),
        inline_limit=_int("RAREBIT_INLINE_LIMIT", 10),
        command_results=_int("RAREBIT_COMMAND_RESULTS", 6),
        max_alts=_int("RAREBIT_MAX_ALTS", 5),
        log_level=(os.getenv("RAREBIT_LOG_LEVEL") or "INFO").strip().upper(),
        groups_store_path=(os.getenv("RAREBIT_GROUPS_STORE") or "groups.json").strip(),
    )
