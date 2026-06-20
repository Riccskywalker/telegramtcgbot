"""Handler Telegram: comando /price, ricerca inline, selezione alternative.

Solo carte (il /box è stato rimosso per ora). Supporta tag lingua (EN/IT/…):
il prezzo mostrato è quello Cardmarket di quella lingua, preso dal dettaglio.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import List, Optional, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    LinkPreviewOptions,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from . import texts
from .api import Item, RarebitAPI, card_headline
from .config import Config
from .fx import FxRates
from .groups import Group, GroupStore, is_trackable_chat, membership_is_present
from .formatting import (
    format_money,
    inline_description,
    inline_title,
    item_url,
    render_message,
)
from .search import extract_language

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# stato condiviso
# --------------------------------------------------------------------------- #
def _api(context: ContextTypes.DEFAULT_TYPE) -> RarebitAPI:
    return context.bot_data["api"]


def _cfg(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.bot_data["cfg"]


def _fx(context: ContextTypes.DEFAULT_TYPE) -> FxRates:
    return context.bot_data["fx"]


def _groups(context: ContextTypes.DEFAULT_TYPE) -> GroupStore:
    return context.bot_data["groups"]


# --------------------------------------------------------------------------- #
# lingua + prezzo di display
# --------------------------------------------------------------------------- #
async def _priced_item(
    context: ContextTypes.DEFAULT_TYPE, item: Item, language: Optional[str]
) -> Tuple[Item, Optional[str]]:
    """Sostituisce il prezzo dell'item col current value calcolato dal dettaglio
    (come il sito: lingua CM → global-lowest → TCGplayer max → CardTrader).

    Ritorna (item, lingua_CM_applicata|None). Se il dettaglio non dà nulla di
    utile, tiene il price di lista."""
    detail = await _api(context).get_card_detail(item.id)
    value, currency, delta, applied = card_headline(detail, language)
    if value is None:
        return item, None
    new_delta = delta if delta is not None else item.delta_pct
    return replace(item, price=value, currency=currency, delta_pct=new_delta), applied


async def _disp_price(
    context: ContextTypes.DEFAULT_TYPE, item: Item
) -> Tuple[Optional[float], Optional[str]]:
    cfg, fx = _cfg(context), _fx(context)
    return await fx.convert(item.price, item.currency, cfg.display_currency)


def _preview(item: Item, cfg: Config) -> LinkPreviewOptions:
    if cfg.image_mode == "preview" and item.image_url:
        return LinkPreviewOptions(
            url=item.image_url, prefer_large_media=True, show_above_text=True
        )
    return LinkPreviewOptions(is_disabled=True)


def _url_button(item: Item, cfg: Config) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        texts.LINK_LABEL, url=item_url(item, cfg.site_base, cfg.locale, cfg.utm)
    )


def _inline_search_button() -> InlineKeyboardButton:
    """Pre-compila la ricerca inline nella chat corrente (niente da digitare)."""
    return InlineKeyboardButton(
        texts.INLINE_SEARCH_LABEL, switch_inline_query_current_chat=""
    )


def _inline_pick_button() -> InlineKeyboardButton:
    """Apre il selettore di chat: l'utente sceglie dove cercare (es. la chat di
    un amico) e Telegram pre-compila lì la ricerca inline."""
    return InlineKeyboardButton(texts.INLINE_PICK_LABEL, switch_inline_query="")


def _alt_label(item: Item, value: Optional[float], currency: Optional[str]) -> str:
    money = format_money(value, currency) or "prezzo n/d"
    set_name = item.set_name or item.set_code or ""
    label = item.name + (" · " + set_name if set_name else "") + " · " + money
    return label[:90]


def _effective_language(
    context: ContextTypes.DEFAULT_TYPE, explicit: Optional[str]
) -> Optional[str]:
    """Lingua da usare: il tag esplicito se c'è, altrimenti il default di config."""
    return explicit or _cfg(context).default_language


def _note_for(applied: Optional[str]) -> Optional[str]:
    # mostra "Cardmarket XX" solo se è stata applicata una lingua CM specifica;
    # su JP/global-lowest niente nota
    return texts.lang_note(applied) if applied else None


def _with_notes(text: str, notes: List[str]) -> str:
    clean = [n for n in notes if n]
    if not clean:
        return text
    return text + "\n\n" + "\n".join("<i>{}</i>".format(n) for n in clean)


# --------------------------------------------------------------------------- #
# invio scheda (top) + bottoni alternativi
# --------------------------------------------------------------------------- #
async def _send_card(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    top: Item,
    alts: List[Item],
    owner_id: int,
    language: Optional[str],
) -> None:
    cfg = _cfg(context)
    top, applied = await _priced_item(context, top, language)
    dval, dcur = await _disp_price(context, top)
    text = render_message(top, dval, dcur)

    rows = [[_url_button(top, cfg), _inline_search_button()]]
    lang_seg = language or "_"

    async def _enrich(alt: Item):
        alt2, _ = await _priced_item(context, alt, language)
        av, ac = await _disp_price(context, alt2)
        return alt2, av, ac

    for alt2, av, ac in await asyncio.gather(*[_enrich(a) for a in alts]):
        cb = "c:{}:{}:{}".format(owner_id, lang_seg, alt2.id)
        rows.append([InlineKeyboardButton(_alt_label(alt2, av, ac), callback_data=cb)])

    notes = [_note_for(applied)]
    if alts:
        notes.append(texts.ALT_HINT)
    text = _with_notes(text, notes)
    markup = InlineKeyboardMarkup(rows)

    if cfg.image_mode == "photo" and top.image_url:
        try:
            await message.reply_photo(
                photo=top.image_url, caption=text,
                parse_mode=ParseMode.HTML, reply_markup=markup,
            )
            return
        except Exception:
            logger.debug("reply_photo fallita, fallback testo", exc_info=True)
    await message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=markup,
        link_preview_options=_preview(top, cfg),
    )


# --------------------------------------------------------------------------- #
# comandi base
# --------------------------------------------------------------------------- #
def _add_to_group_kb(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_inline_search_button(), _inline_pick_button()],
            [InlineKeyboardButton(
                texts.ADD_TO_GROUP, url="https://t.me/{}?startgroup=true".format(username)
            )],
        ]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    username = context.bot.username
    await update.message.reply_text(
        texts.start(username), parse_mode=ParseMode.HTML,
        reply_markup=_add_to_group_kb(username),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    username = context.bot.username
    await update.message.reply_text(
        texts.help_text(username), parse_mode=ParseMode.HTML,
        reply_markup=_add_to_group_kb(username),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    raw = " ".join(context.args or []).strip()
    if not raw:
        await update.message.reply_text(texts.usage_price(), parse_mode=ParseMode.HTML)
        return

    query, explicit = extract_language(raw)
    language = _effective_language(context, explicit)
    api, cfg = _api(context), _cfg(context)
    try:
        items = await api.search_cards(query, cfg.command_results)
    except Exception:
        logger.exception("Ricerca carte fallita per «%s»", raw)
        await update.message.reply_text(texts.ERROR_GENERIC)
        return

    if not items:
        await update.message.reply_text(
            texts.no_results_card(raw), parse_mode=ParseMode.HTML
        )
        return

    top = items[0]
    alts = items[1 : 1 + cfg.max_alts]
    owner_id = update.effective_user.id if update.effective_user else 0
    await _send_card(update.message, context, top, alts, owner_id, language)


# --------------------------------------------------------------------------- #
# selezione di un'alternativa (callback)
# --------------------------------------------------------------------------- #
def _parse_callback(data: str):
    """Ritorna (owner|None, language|None, item_id) o None se non valido.

    Formati: 'c:owner:lang:id' (nuovo), 'c:owner:id' / 'c:id' (legacy)."""
    parts = data.split(":", 3)
    if not parts or parts[0] != "c":
        return None
    if len(parts) == 4:
        _, owner, lang, item_id = parts
    elif len(parts) == 3:
        _, owner, item_id = parts
        lang = None
    elif len(parts) == 2:
        owner, lang, item_id = None, None, parts[1]
    else:
        return None
    language = None if lang in (None, "_", "") else lang
    return owner, language, item_id


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    parsed = _parse_callback(query.data or "")
    if parsed is None:
        await query.answer()
        return
    owner, language, item_id = parsed

    if owner is not None and query.from_user and str(query.from_user.id) != owner:
        await query.answer(texts.NOT_YOUR_SEARCH, show_alert=False)
        return
    await query.answer()

    api, cfg = _api(context), _cfg(context)
    item = await api.resolve("card", item_id)
    if item is None:
        try:
            await query.edit_message_text(texts.EXPIRED)
        except Exception:
            logger.debug("edit EXPIRED fallita", exc_info=True)
        return

    item, applied = await _priced_item(context, item, language)
    dval, dcur = await _disp_price(context, item)
    text = _with_notes(render_message(item, dval, dcur), [_note_for(applied)])
    markup = InlineKeyboardMarkup([[_url_button(item, cfg), _inline_search_button()]])
    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=markup,
            link_preview_options=_preview(item, cfg),
        )
    except Exception:
        logger.debug("edit_message_text fallita, invio nuovo", exc_info=True)
        if query.message:
            await query.message.reply_text(
                text, parse_mode=ParseMode.HTML, reply_markup=markup,
                link_preview_options=_preview(item, cfg),
            )


# --------------------------------------------------------------------------- #
# ricerca inline (il wedge per i gruppi)
# --------------------------------------------------------------------------- #
async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    inline = update.inline_query
    if inline is None:
        return
    cfg, api = _cfg(context), _api(context)
    query, explicit = extract_language((inline.query or "").strip())
    language = _effective_language(context, explicit)

    if len(query) < 2:
        hint = InlineQueryResultArticle(
            id="hint",
            title=texts.INLINE_HINT_TITLE,
            description=texts.INLINE_HINT_DESC,
            input_message_content=InputTextMessageContent(
                "Cerca una carta con @{} seguito dal nome".format(context.bot.username)
            ),
        )
        await inline.answer([hint], cache_time=10, is_personal=False)
        return

    try:
        items = await api.search_cards(query, cfg.inline_limit)
    except Exception:
        logger.exception("Inline search fallita per «%s»", query)
        await inline.answer([], cache_time=5)
        return

    async def _result(it: Item):
        if not it.id:
            return None
        it2, applied = await _priced_item(context, it, language)
        dval, dcur = await _disp_price(context, it2)
        desc = inline_description(it2, dval, dcur)
        if applied:
            desc += " · " + applied.upper()
        content = _with_notes(render_message(it2, dval, dcur), [_note_for(applied)])
        return InlineQueryResultArticle(
            id=it2.id,
            title=inline_title(it2),
            description=desc,
            thumbnail_url=it2.image_url or None,
            input_message_content=InputTextMessageContent(
                content,
                parse_mode=ParseMode.HTML,
                link_preview_options=_preview(it2, cfg),
            ),
            reply_markup=InlineKeyboardMarkup([[_url_button(it2, cfg), _inline_search_button()]]),
        )

    results = [r for r in await asyncio.gather(*[_result(it) for it in items]) if r]
    await inline.answer(results, cache_time=30, is_personal=False)


# --------------------------------------------------------------------------- #
# tracciamento gruppi (per il digest top-movers)
# --------------------------------------------------------------------------- #
async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Aggiorna lo store quando il bot entra/esce da un gruppo o canale.

    Telegram manda un update `my_chat_member` a ogni cambio di stato del bot in
    una chat. Lo registriamo così il cron del digest sa dove poter postare.
    """
    cmu = update.my_chat_member
    if cmu is None:
        return
    new = cmu.new_chat_member
    # gli update MY_CHAT_MEMBER riguardano sempre il bot, ma verifichiamo
    if new is None or (new.user and context.bot and new.user.id != context.bot.id):
        return

    chat = cmu.chat
    if not is_trackable_chat(chat.type):
        return

    store = _groups(context)
    status = new.status
    is_member = getattr(new, "is_member", None)
    if membership_is_present(status, is_member):
        store.upsert(
            Group(
                chat_id=chat.id,
                type=chat.type,
                title=chat.title,
                added_by=cmu.from_user.id if cmu.from_user else None,
                is_admin=(status == "administrator"),
            )
        )
        logger.info("Bot presente in %s «%s» (%s)", chat.id, chat.title, status)
    else:
        store.remove(chat.id)
        logger.info("Bot fuori da %s «%s» (%s)", chat.id, chat.title, status)


# --------------------------------------------------------------------------- #
# errori
# --------------------------------------------------------------------------- #
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Eccezione non gestita", exc_info=context.error)
