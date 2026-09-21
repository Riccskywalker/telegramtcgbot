"""Pure HTML/text rendering; no chat SDK dependencies."""
from html import escape

from .api import Item, select_quote

PRODUCT_KIND_LABELS = {'ETB': 'Elite Trainer Box', 'EX_BOX': 'ex Box'}


def format_money(value, currency):
    if value is None:
        return None
    cur = (currency or '').upper()
    if cur == 'JPY':
        return f'¥{value:,.0f}'
    prefix = {'EUR': '€', 'USD': '$', 'GBP': '£'}.get(cur)
    return f'{prefix}{value:,.2f}' if prefix else f'{value:,.2f} {cur}'.strip()


def format_delta(pct):
    if pct is None:
        return ''
    rounded = round(pct, 1)
    sign = '−' if rounded < 0 else '+' if rounded > 0 else ''
    return f'7d {sign}{abs(rounded):.1f}%'


def product_kind_label(kind):
    return PRODUCT_KIND_LABELS.get(kind, kind.replace('_', ' ').title()) if kind else None


def subtitle(item):
    if item.kind == 'card':
        parts = [item.set_name or item.set_code, f'#{item.number}' if item.number else None, item.rarity]
    else:
        parts = ['Sealed', product_kind_label(item.product_kind), item.set_name]
    return ' · '.join(p for p in parts if p)


def price_line(item, value=None, currency=None):
    money = format_money(item.price if value is None else value, currency or item.currency)
    if money is None:
        return '<i>Current value unavailable</i>'
    line = f'Current value <b>{escape(money)}</b>'
    if item.as_of:
        line += f' (as of {escape(item.as_of)})'
    if item.locale:
        line += f' [{escape(item.locale.upper())}]'
    if item.delta_pct is not None:
        line += ' · ' + format_delta(item.delta_pct)
        if item.kind == 'box':
            line += ' vs Cardmarket 7d avg'
    return line


def render_message(item, disp_value=None, disp_currency=None, *, with_price=True):
    lines = [f'<b>{escape(item.name)}</b>', escape(subtitle(item))]
    if with_price:
        lines.extend(['', price_line(item, disp_value, disp_currency)])
        for source, variant, label in [('CARDMARKET', 'AVG_7D', 'Cardmarket 7d avg'),
                                       ('TCGPLAYER', 'MARKET', 'TCGplayer Market')]:
            q = select_quote(item.quotes, source, variant, item.locale)
            if not q and source == 'CARDMARKET':
                q = select_quote(item.quotes, source, 'LOW', item.locale)
                label = 'Cardmarket low'
            if q:
                line = f'{label}: {format_money(q["amount"], q.get("currency"))}'
                if q.get('as_of'):
                    line += f' (as of {q["as_of"]})'
                lines.append(escape(line))
    return '\n'.join(lines)


def inline_title(item):
    return ' · '.join(p for p in [item.name, item.set_name or item.set_code] if p)


def inline_description(item):
    return subtitle(item)


def render_quota(data):
    plan, quota = data.get('plan') or {}, data.get('quota') or {}
    limit = quota.get('credits_limit', 'unknown')
    cap = quota.get('daily_cap', 'unknown')
    trial = quota.get('renews') is False
    expires = quota.get('trial_expires_at', 'not provided')
    if quota.get('renews') is True:
        expires = 'not applicable'
    elif 'trial_expires_at' in quota and quota.get('trial_expired'):
        expires = f'{expires} (expired)'
    credits = f'{quota.get("credits_used", "unknown")} / {"unlimited" if limit is None else limit}'
    if 'credits_remaining' in quota:
        credits += f' ({quota["credits_remaining"]} remaining)'
    daily = 'none' if cap is None else str(cap)
    if 'daily_used' in quota:
        daily = f'{quota["daily_used"]} / {daily} today'
    lines = [f'Plan: {plan.get("name") or plan.get("code") or "unknown"}',
             f'Credits: {credits}', f'Daily cap: {daily}', f'Trial expiry: {expires}']
    if trial and quota.get('resets_at'):
        lines.append(f'Current period ends: {quota["resets_at"]} (trial credits do not renew)')
    if quota.get('stale'):
        lines.append('Usage may be delayed.')
    return '\n'.join(lines)
