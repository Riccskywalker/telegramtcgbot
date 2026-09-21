"""Telegram-only settings, loaded after the mandatory API configuration."""
from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv

from ..core.config import CoreConfig, load_core_config


@dataclass(frozen=True)
class Config:
    core: CoreConfig
    bot_token: str = field(repr=False)
    bot_lang: str = 'en'
    admin_chat_id: int = None
    inline_limit: int = 10
    command_results: int = 6
    groups_store_path: str = 'groups.json'


def load_config():
    # Only the working directory's .env; never search parent directories.
    load_dotenv(Path.cwd() / '.env')
    core = load_core_config()
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is required. Get a token from @BotFather.')
    lang = os.getenv('BOT_LANG', 'en').strip().lower() or 'en'
    if lang != 'en':
        raise RuntimeError('BOT_LANG currently supports en only.')
    admin = os.getenv('ADMIN_CHAT_ID', '').strip()
    try:
        admin_id = int(admin) if admin else None
    except ValueError as exc:
        raise RuntimeError('ADMIN_CHAT_ID must be an integer Telegram chat ID.') from exc
    if admin_id is not None and admin_id <= 0:
        raise RuntimeError('ADMIN_CHAT_ID must identify the admin private chat (positive ID).')
    return Config(core=core, bot_token=token, bot_lang=lang, admin_chat_id=admin_id)
