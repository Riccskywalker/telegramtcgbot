"""Test del parsing query + ranking + indice set (puro, niente rete)."""

from rarebit_bot.api import Item
from rarebit_bot.search import (
    SetIndex,
    extract_language,
    norm_number,
    parse_query,
    rank,
)

# set finti realistici (i due "151" NON normalizzano a "151" esatto → ambigui)
SETS = [
    {"code": "LOR", "slug": "lost-origin", "name": "Lost Origin"},
    {"code": "SV2a", "slug": "pokemon-card-151", "name": "Pokemon Card 151 (SV2a)"},
    {"code": "MEW", "slug": "151", "name": "151 (MEW)"},
    {"code": "BASE", "slug": "base", "name": "Base"},
]
INDEX = SetIndex.build(SETS)


def test_norm_number():
    assert norm_number("04") == "4"
    assert norm_number("010") == "10"
    assert norm_number("TG03") == "tg03"
    assert norm_number("6") == "6"
    assert norm_number(None) is None


def test_code_hint_requires_digit():
    assert INDEX.code_hint("sv2a").code == "SV2a"
    assert INDEX.code_hint("SV2A").code == "SV2a"
    assert INDEX.code_hint("mew") is None  # collisione col Pokémon → niente sigla
    assert INDEX.code_hint("lor") is None  # senza cifra → via nome, non sigla


def test_parse_setcode_token():
    p = parse_query("charizard sv2a", INDEX)
    assert p.set_code == "SV2a"
    assert p.name_tokens == ["charizard"]
    assert p.q == "charizard"
    assert p.number is None


def test_parse_setname_run():
    p = parse_query("charizard lost origin", INDEX)
    assert p.set_code == "LOR"
    assert p.name_tokens == ["charizard"]
    assert p.q == "charizard"


def test_parse_number():
    p = parse_query("charizard 04", INDEX)
    assert p.set_code is None
    assert p.number == "4"
    assert p.name_tokens == ["charizard"]
    assert p.q == "charizard 4"  # numero tenuto in q per il ranking API


def test_parse_mew_pokemon_not_setcode():
    # "mew" è Pokémon, "sv2a" è la sigla set
    p = parse_query("mew sv2a", INDEX)
    assert p.set_code == "SV2a"
    assert p.name_tokens == ["mew"]


def test_parse_ambiguous_151_stays_query():
    p = parse_query("pikachu 151", INDEX)
    assert p.set_code is None  # "151" non matcha un nome set unico
    assert p.number == "151"
    assert p.q == "pikachu 151"


def _it(name, number):
    return Item(kind="card", id=name + number, name=name, number=number)


def test_rank_number_match_wins():
    p = parse_query("charizard 04", INDEX)
    items = [_it("Charizard", "1"), _it("Charizard VMAX", "4"), _it("Charizard", "4")]
    out = rank(items, p)
    assert out[0].name == "Charizard" and out[0].number == "4"  # numero + nome esatto
    assert out[1].number == "4"  # l'altro #4 prima dei non-#4
    assert out[2].number == "1"


def test_rank_exact_name_bonus():
    p = parse_query("mew", INDEX)
    items = [_it("Mew ex", "151"), _it("Mew", "053")]
    out = rank(items, p)
    assert out[0].name == "Mew"  # match esatto del nome batte "Mew ex"


# --- tag lingua ------------------------------------------------------------ #
def test_extract_language_suffix():
    assert extract_language("charizard lost origin EN") == ("charizard lost origin", "en")


def test_extract_language_aliases():
    assert extract_language("moonbreon ITA") == ("moonbreon", "it")
    assert extract_language("pikachu eng") == ("pikachu", "en")
    assert extract_language("charizard tedesco") == ("charizard", "de")


def test_extract_language_prefix():
    assert extract_language("ita pikachu 151") == ("pikachu 151", "it")


def test_extract_language_none():
    assert extract_language("charizard") == ("charizard", None)
    assert extract_language("charizard ex") == ("charizard ex", None)


def test_extract_language_single_token_not_treated():
    assert extract_language("EN") == ("EN", None)


def test_extract_language_keeps_card_name_token_ex():
    assert extract_language("charizard ex en") == ("charizard ex", "en")
