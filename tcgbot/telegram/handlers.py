"""Telegram commands and inline selection; API and pricing stay in the core."""
from __future__ import annotations

import logging
from html import escape

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle,
                      InputTextMessageContent, LinkPreviewOptions, Update)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from . import texts
from ..core.api import APIError
from ..core.formatting import inline_description, inline_title, render_message, render_quota
from ..core.search import extract_language
from .groups import Group, is_trackable_chat, membership_is_present

logger = logging.getLogger(__name__)


def _preview(item):
    if item.image_url:
        return LinkPreviewOptions(url=item.image_url, prefer_large_media=True, show_above_text=True)
    return LinkPreviewOptions(is_disabled=True)


def _button(item, owner, language, label=None):
    data = f'{item.kind}:{owner}:{language or "_"}:{item.id}'
    # Telegram callback_data is at most 64 UTF-8 bytes (sealed IDs can be long).
    if len(data.encode('utf-8')) > 64:
        return None
    return InlineKeyboardButton(label or 'Current value', callback_data=data)


async def _render(context, item, language, with_stats):
    priced = await context.bot_data['api'].priced_item(item, language, with_stats=with_stats)
    value, currency = await context.bot_data['fx'].convert(priced.price, priced.currency, 'EUR')
    return render_message(priced, value, currency)


def _error_text(exc):
    if isinstance(exc, APIError):
        return texts.api_error(exc)
    logger.exception('Lookup failed')
    return texts.ERROR_GENERIC


async def cmd_start(update, context):
    if update.message:
        await update.message.reply_text(texts.start(context.bot.username), parse_mode=ParseMode.HTML,
                                       link_preview_options=LinkPreviewOptions(is_disabled=True))


async def cmd_help(update, context):
    await cmd_start(update, context)


async def _lookup(update, context, kind):
    if not update.message:
        return
    raw = ' '.join(context.args or []).strip()
    if not raw:
        await update.message.reply_text(texts.usage_price() if kind == 'card' else texts.usage_box())
        return
    query, language = extract_language(raw)
    api, cfg = context.bot_data['api'], context.bot_data['cfg']
    try:
        search = api.search_cards if kind == 'card' else api.search_boxes
        items = await search(query, cfg.command_results)
        if not items:
            await update.message.reply_text(texts.NOT_FOUND)
            return
        text = await _render(context, items[0], language, with_stats=True)
        owner = update.effective_user.id if update.effective_user else 0
        buttons = [_button(it, owner, language, (inline_title(it) + (f' #{it.number}' if it.number else ''))[:90])
                   for it in items[1:]]
        rows = [[button] for button in buttons if button]
        await update.message.reply_text(text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(rows) if rows else None,
            link_preview_options=_preview(items[0]))
    except Exception as exc:
        await update.message.reply_text(_error_text(exc), link_preview_options=LinkPreviewOptions(is_disabled=True))


async def cmd_price(update, context):
    await _lookup(update, context, 'card')


async def cmd_box(update, context):
    await _lookup(update, context, 'box')


async def cmd_quota(update, context):
    if not update.message:
        return
    admin = context.bot_data['cfg'].admin_chat_id
    if (admin is None or not update.effective_chat or update.effective_chat.type != 'private'
            or update.effective_chat.id != admin or not update.effective_user
            or update.effective_user.id != admin):
        await update.message.reply_text('This command is only available to the bot owner in private chat.')
        return
    try:
        await update.message.reply_text(render_quota(await context.bot_data['api'].me()))
    except Exception as exc:
        await update.message.reply_text(_error_text(exc), link_preview_options=LinkPreviewOptions(is_disabled=True))


async def on_inline(update, context):
    inline = update.inline_query
    if not inline:
        return
    query, language = extract_language(inline.query.strip())
    if len(query) < 2:
        await inline.answer([InlineQueryResultArticle(id='hint', title='Type a card name',
            description='For example: charizard 125',
            input_message_content=InputTextMessageContent(texts.usage_price()))], cache_time=10)
        return
    try:
        items = await context.bot_data['api'].search_cards(query, context.bot_data['cfg'].inline_limit)
        results = []
        for item in items:
            button = _button(item, inline.from_user.id, language)
            results.append(InlineQueryResultArticle(id=item.id, title=inline_title(item),
                description=inline_description(item), thumbnail_url=item.image_url,
                input_message_content=InputTextMessageContent(render_message(item, with_price=False),
                    parse_mode=ParseMode.HTML, link_preview_options=_preview(item)),
                reply_markup=InlineKeyboardMarkup([[button]]) if button else None))
        if not results:
            results = [InlineQueryResultArticle(id='empty', title='Nothing found',
                        input_message_content=InputTextMessageContent(texts.NOT_FOUND))]
        # Personal: callback buttons belong to the user who searched.
        await inline.answer(results, cache_time=30, is_personal=True)
    except Exception as exc:
        message = _error_text(exc)
        await inline.answer([InlineQueryResultArticle(id='error', title=message[:100],
            input_message_content=InputTextMessageContent(message,
                link_preview_options=LinkPreviewOptions(is_disabled=True)))], cache_time=0, is_personal=True)


async def on_callback(update, context):
    query = update.callback_query
    if not query:
        return
    parts = (query.data or '').split(':', 3)
    if len(parts) != 4 or parts[0] not in ('card', 'box'):
        await query.answer()
        return
    kind, owner, lang, item_id = parts
    if str(query.from_user.id) != owner:
        await query.answer('This search belongs to another user. Use /price to start yours.')
        return
    await query.answer()
    try:
        item = await context.bot_data['api'].resolve(kind, item_id)
        text = await _render(context, item, None if lang == '_' else lang, with_stats=False)
    except Exception as exc:
        await query.edit_message_text(escape(_error_text(exc)), parse_mode=ParseMode.HTML,
                                     link_preview_options=LinkPreviewOptions(is_disabled=True))
        return
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, link_preview_options=_preview(item))


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.my_chat_member
    if cmu is None:
        return
    new = cmu.new_chat_member
    if new is None or (new.user and context.bot and new.user.id != context.bot.id):
        return
    chat = cmu.chat
    if not is_trackable_chat(chat.type):
        return
    store = context.bot_data['groups']
    if membership_is_present(new.status, getattr(new, 'is_member', None)):
        store.upsert(Group(chat_id=chat.id, type=chat.type, title=chat.title,
                           added_by=cmu.from_user.id if cmu.from_user else None,
                           is_admin=new.status == 'administrator'))
    else:
        store.remove(chat.id)


async def on_error(update, context):
    logger.error('Unhandled Telegram error', exc_info=context.error)
