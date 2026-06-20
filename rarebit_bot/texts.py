"""Tutta la copy rivolta agli utenti, in italiano. Un solo posto da tradurre."""

from __future__ import annotations

# Comandi mostrati nel menu di Telegram (setMyCommands)
BOT_COMMANDS = [
    ("price", "Prezzo di una carta — /price charizard"),
    ("help", "Come si usa il bot"),
]

LINK_LABEL = "Vedi su RareBit ↗"
ADD_TO_GROUP = "Aggiungimi a un gruppo"
INLINE_SEARCH_LABEL = "Cerca una carta"
INLINE_PICK_LABEL = "Cerca in una chat"
PRICE_UNAVAILABLE = "<i>Prezzo non ancora disponibile</i>"
ALT_HINT = "Non è questa? Scegli qui sotto."
NOT_YOUR_SEARCH = "Questa ricerca è di un altro utente. Fai /price per cercare tu."


def lang_note(lang: str) -> str:
    return "Prezzo Cardmarket {}".format(lang.upper())


def start(bot_username: str) -> str:
    return (
        "<b>RareBit</b> — prezzi delle carte Pokémon, al volo.\n\n"
        "<b>Usami in QUALSIASI chat</b> (anche dove non sono presente):\n"
        "nel campo messaggio scrivi <code>@{u} moonbreon</code>, si apre un menù "
        "coi risultati, tocchi la carta e viene inviata come tuo messaggio.\n"
        "Più semplice: tocca <b>Cerca in una chat</b> qui sotto, scegli la chat e "
        "digita solo il nome — il <code>@</code> lo mette Telegram.\n\n"
        "<b>Comandi</b>\n"
        "• <code>/price &lt;carta&gt;</code> — es. <code>/price charizard sv2a</code>\n"
        "• <code>/help</code> — questa schermata\n\n"
        "Dati da rarebit.app, prezzi in euro. Non leggo i messaggi del gruppo: "
        "rispondo solo ai comandi e alle ricerche inline."
    ).format(u=bot_username)


def help_text(bot_username: str) -> str:
    return (
        "<b>Come usare RareBit nel gruppo</b>\n\n"
        "<b>1. Ricerca inline (consigliata)</b>\n"
        "In un messaggio scrivi <code>@{u} </code> seguito dal nome:\n"
        "<code>@{u} charizard lost origin</code>\n"
        "Scegli dal menù e la card prezzo finisce nel messaggio. Nessun "
        "permesso da admin, niente spam.\n\n"
        "<b>2. Comando</b>\n"
        "• <code>/price &lt;carta&gt;</code> — prezzo singola carta\n\n"
        "<b>Affinare la ricerca</b>\n"
        "• per numero: <code>/price charizard 04</code>\n"
        "• per nome set: <code>/price charizard lost origin</code>\n"
        "• per sigla set: <code>/price mew sv2a</code>\n"
        "• per lingua: <code>/price charizard lost origin EN</code> "
        "(EN/ENG, IT/ITA, DE, FR, ES)\n"
        "• i refusi sono tollerati: <code>charzard</code> trova Charizard.\n\n"
        "I prezzi sono mostrati in euro."
    ).format(u=bot_username)


def usage_price() -> str:
    return (
        "Scrivi cosa cercare: <code>/price charizard</code>\n"
        "Affina con numero, set o lingua:\n"
        "<code>/price charizard 04</code> · "
        "<code>/price mew sv2a</code> · "
        "<code>/price charizard lost origin EN</code>"
    )


def usage_box() -> str:
    return (
        "Scrivi quale sigillato: <code>/box 151 booster box</code>\n"
        "Funziona anche con ETB, tin, blister."
    )


def no_results_card(query: str) -> str:
    return (
        "Nessuna carta trovata per «{q}».\n"
        "Prova col nome inglese o aggiungi il set."
    ).format(q=query)


def no_results_box(query: str) -> str:
    return (
        "Nessun sigillato trovato per «{q}».\n"
        "Prova col nome del prodotto (es. «151 booster box»)."
    ).format(q=query)


def multi_header_card(query: str, n: int) -> str:
    return "{n} carte per «{q}». Quale?".format(n=n, q=query)


def multi_header_box(query: str, n: int) -> str:
    return "{n} sigillati per «{q}». Quale?".format(n=n, q=query)


ERROR_GENERIC = (
    "Ops, problema temporaneo nel recuperare i dati. Riprova tra poco."
)

INLINE_HINT_TITLE = "Scrivi il nome di una carta…"
INLINE_HINT_DESC = "es. charizard lost origin — poi scegli dal menù"
EXPIRED = "Risultato scaduto, rifai la ricerca."
