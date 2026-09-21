"""English user-facing copy and API error mapping."""
BOT_COMMANDS = [('price', 'Look up a card price'), ('box', 'Look up a sealed product'),
                ('help', 'How to use the bot'), ('quota', 'API allowance (owner only)')]
ERROR_GENERIC = 'There was a problem fetching the data. Please try again in a moment.'
NOT_FOUND = 'Nothing found. Try the English name, set code or collector number.'
QUOTA_EXHAUSTED = ('This bot has used up its API credits for now. The owner can raise the limit '
                   'at pokemontcgapi.com/pricing (or verify the account email).')


def api_error(error):
    if error.status == 401:
        return 'The bot is misconfigured (API key). The owner has been notified in the log.'
    if error.code in {'QUOTA_EXCEEDED', 'DAILY_CAP_EXCEEDED', 'TRIAL_EXHAUSTED', 'EMAIL_UNVERIFIED'}:
        handoff = (error.details.get('next_step') or {}).get('handoff')
        return handoff if isinstance(handoff, str) and handoff.strip() else QUOTA_EXHAUSTED
    if error.status == 429 and error.code == 'RATE_LIMITED':
        return 'Too many requests. Please try again in a moment.'
    if error.status == 404 and error.code in {'CARD_NOT_FOUND', 'SEALED_NOT_FOUND'}:
        return NOT_FOUND
    return ERROR_GENERIC


def usage_price():
    return ('Use /price charizard 125\n'
            'Add a set name or code: /price charizard obsidian flames\n'
            'Add a price language: /price charizard 125 EN (EN, IT, DE, FR, ES).')


def usage_box():
    return 'Use /box lost origin booster box (also ETBs, tins and packs).'


def help_text(username):
    return (f'<b>telegramtcgbot</b> — Pokémon TCG prices in your chat.\n\n'
            '/price charizard 125 — card price and 7-day change\n'
            '/box lost origin booster box — sealed price\n'
            '/quota — API allowance, owner only in private chat\n'
            '/help — this message\n\n'
            f'Type @{username} charizard to browse cards, choose one and tap Current value.\n'
            'Refine searches with a set name, set code or collector number. '
            'Use English card names; spelling mistakes may return no matches. '
            'Add EN, IT, DE, FR or ES for a price language when your API plan includes it.\n'
            'Prices are shown in EUR when a conversion is available.\n\n'
            'Card data and prices by pokemontcgapi.com')


def start(username):
    return help_text(username)
