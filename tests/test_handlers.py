import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import httpx
import pytest

from tcgbot.core.api import PTCGAPI, APIError, Item
from tcgbot.core.config import CoreConfig
from tcgbot.telegram import handlers, texts
from tcgbot.telegram.config import Config


def context(api=None, args=None, admin=None):
    return NS(args=args or [], bot=NS(username='telegramtcgbot'), bot_data={
        'api': api or NS(search_cards=AsyncMock(), search_boxes=AsyncMock(),
                         priced_item=AsyncMock(), resolve=AsyncMock(), me=AsyncMock()),
        'fx': NS(convert=AsyncMock(return_value=(1.2, 'EUR'))),
        'cfg': Config(core=CoreConfig('test'), bot_token='test', admin_chat_id=admin)})


def update(user=123, chat=123, chat_type='private'):
    return NS(message=NS(reply_text=AsyncMock()), effective_chat=NS(id=chat, type=chat_type),
              effective_user=NS(id=user))


def test_inline_search_no_price_stats_or_fx():
    ctx = context()
    item = Item(kind='card', id='obf-125', name='Charizard ex', number='125', image_url='https://images.example/125.webp')
    ctx.bot_data['api'].search_cards.return_value = [item]
    inline = NS(query='charizard 125', from_user=NS(id=123), answer=AsyncMock())
    asyncio.run(handlers.on_inline(NS(inline_query=inline), ctx))
    ctx.bot_data['api'].priced_item.assert_not_called()
    ctx.bot_data['fx'].convert.assert_not_called()
    result = inline.answer.call_args.args[0][0]
    assert 'Current value' not in result.input_message_content.message_text
    assert result.thumbnail_url == item.image_url
    assert result.reply_markup.inline_keyboard[0][0].callback_data == 'card:123:_:obf-125'
    assert inline.answer.call_args.kwargs['is_personal'] is True


@pytest.mark.parametrize('admin,user,chat,kind,allowed', [
    (None, 123, 123, 'private', False), (123, 456, 456, 'private', False),
    (123, 123, -100, 'supergroup', False), (123, 456, 123, 'private', False),
    (123, 123, 123, 'private', True)])
def test_quota_authorization(admin, user, chat, kind, allowed):
    ctx, upd = context(admin=admin), update(user, chat, kind)
    ctx.bot_data['api'].me.return_value = {'plan': {'name': 'Trial'}, 'quota': {'credits_used': 0, 'credits_limit': 800}}
    asyncio.run(handlers.cmd_quota(upd, ctx))
    assert ctx.bot_data['api'].me.await_count == int(allowed)
    assert ('Credits: 0 / 800' in upd.message.reply_text.call_args.args[0]) == allowed


@pytest.mark.parametrize('failure_stage', ['search_cards', 'priced_item'])
def test_error_mapped_during_search_or_pricing(failure_stage):
    ctx, upd = context(args=['charizard']), update()
    api = ctx.bot_data['api']
    api.search_cards.return_value = [Item(kind='card', id='x', name='Charizard')]
    getattr(api, failure_stage).side_effect = APIError(429, 'QUOTA_EXCEEDED', details={'next_step': {'handoff': 'Ask the owner to verify email.'}})
    asyncio.run(handlers.cmd_price(upd, ctx))
    assert upd.message.reply_text.call_args.args[0] == 'Ask the owner to verify email.'


def test_inline_errors_visible():
    ctx = context()
    ctx.bot_data['api'].search_cards.side_effect = APIError(401, 'UNAUTHORIZED')
    inline = NS(query='charizard', from_user=NS(id=123), answer=AsyncMock())
    asyncio.run(handlers.on_inline(NS(inline_query=inline), ctx))
    result = inline.answer.call_args.args[0][0]
    assert 'misconfigured (API key)' in result.input_message_content.message_text
    assert inline.answer.call_args.kwargs['cache_time'] == 0


def test_command_only_prices_top_result():
    ctx, upd = context(args=['charizard', 'IT']), update()
    top = Item(kind='card', id='x', name='Charizard', price=1.2, currency='EUR')
    alt = Item(kind='card', id='y', name='Charizard V')
    api = ctx.bot_data['api']
    api.search_cards.return_value = [top, alt]
    api.priced_item.return_value = top
    asyncio.run(handlers.cmd_price(upd, ctx))
    api.priced_item.assert_awaited_once_with(top, 'it', with_stats=True)
    args = upd.message.reply_text.call_args.kwargs
    assert all(button.url is None for row in args['reply_markup'].inline_keyboard for button in row)
    assert len(args['reply_markup'].inline_keyboard) == 1


def test_inline_selection_does_not_request_stats():
    ctx = context()
    item = Item(kind='card', id='obf-125', name='Charizard')
    ctx.bot_data['api'].resolve.return_value = item
    ctx.bot_data['api'].priced_item.return_value = item
    cb = NS(data='card:123:_:obf-125', from_user=NS(id=123), answer=AsyncMock(), edit_message_text=AsyncMock())
    asyncio.run(handlers.on_callback(NS(callback_query=cb), ctx))
    ctx.bot_data['api'].priced_item.assert_awaited_once_with(item, None, with_stats=False)


def test_callback_owner_check():
    ctx = context()
    cb = NS(data='card:123:_:obf-125', from_user=NS(id=456), answer=AsyncMock())
    asyncio.run(handlers.on_callback(NS(callback_query=cb), ctx))
    ctx.bot_data['api'].resolve.assert_not_called()


def test_help_attribution_only_at_end():
    for message in (texts.start('bot'), texts.help_text('bot')):
        assert message.endswith('Card data and prices by pokemontcgapi.com')
        assert message.count('pokemontcgapi.com') == 1
