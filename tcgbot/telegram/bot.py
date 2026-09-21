"""Bootstrap dell'applicazione Telegram: setup, registrazione handler, polling."""

from __future__ import annotations

import logging

from telegram import BotCommand
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    InlineQueryHandler,
)

from . import handlers, texts
from ..core.api import PTCGAPI
from .config import Config, load_config
from ..core.fx import FxRates
from .groups import GroupStore

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        level=getattr(logging, level, logging.INFO),
    )
    # httpx è chiacchierone a INFO
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in texts.BOT_COMMANDS])
    # Catalogue setup is a separate ~3-credit startup cost, shared by all searches.
    try:
        await app.bot_data['api'].set_index()
    except Exception as exc:
        logger.warning('Set index warmup failed (%s); lookups will retry', type(exc).__name__)
    me = await app.bot.get_me()
    logger.info("Bot started as @%s (%s)", me.username, me.id)


async def _post_shutdown(app: Application) -> None:
    api: PTCGAPI = app.bot_data.get("api")
    if api is not None:
        await api.aclose()
    fx: FxRates = app.bot_data.get("fx")
    if fx is not None:
        await fx.aclose()


def build_application(cfg: Config) -> Application:
    app = (
        ApplicationBuilder()
        .token(cfg.bot_token)
        .rate_limiter(AIORateLimiter())
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    app.bot_data["cfg"] = cfg
    app.bot_data["api"] = PTCGAPI(
        base_url=cfg.core.api_base,
        timeout=cfg.core.http_timeout,
        api_key=cfg.core.api_key,
    )
    app.bot_data["fx"] = FxRates(timeout=cfg.core.http_timeout)
    app.bot_data["groups"] = GroupStore(cfg.groups_store_path)

    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("price", handlers.cmd_price))
    app.add_handler(CommandHandler("box", handlers.cmd_box))
    app.add_handler(CommandHandler("quota", handlers.cmd_quota))
    app.add_handler(CallbackQueryHandler(handlers.on_callback))
    app.add_handler(InlineQueryHandler(handlers.on_inline))
    app.add_handler(
        ChatMemberHandler(handlers.on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    app.add_error_handler(handlers.on_error)
    return app


def main() -> None:
    try:
        cfg = load_config()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    _setup_logging('INFO')
    app = build_application(cfg)
    logger.info("Starting polling...")
    app.run_polling(
        allowed_updates=["message", "callback_query", "inline_query", "my_chat_member"]
    )


if __name__ == "__main__":
    main()
