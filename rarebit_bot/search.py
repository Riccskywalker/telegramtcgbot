"""Logica di ricerca: indice dei set + parsing query + ranking dei risultati.

L'API RareBit cerca per NOME (typo-tolerant) ma:
  - ignora il `take` come limite (param giusto = `take`, gestito in api.py);
  - non usa le parole del set nel ranking ("charizard lost origin" resta una
    lista di Charizard a caso);
  - non capisce le sigle dei set nel testo ("charizard sv2a").

Qui riconosciamo nella query un eventuale **set** (per nome es. "lost origin"
o per sigla es. "sv2a") e un eventuale **numero** di carta ("04", "TG03"), così
da filtrare per `setCode` quando possibile e ri-ordinare i candidati.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_WORD = re.compile(r"[a-z0-9]+")
# token che "sembra" un numero di carta: 1-4 cifre, con prefisso/suffisso lettera
# opzionale (4, 04, 187, TG03, H31, 025a). Deve contenere almeno una cifra.
_NUM = re.compile(r"^[a-z]{0,3}\d{1,4}[a-z]?$")


def tokens(s: Optional[str]) -> List[str]:
    return _WORD.findall((s or "").lower())


# tag lingua riconosciuti nella query → codice lingua Cardmarket
LANG_ALIASES = {
    "en": "en", "eng": "en", "english": "en", "inglese": "en",
    "it": "it", "ita": "it", "italian": "it", "italiano": "it",
    "de": "de", "ger": "de", "deu": "de", "german": "de", "tedesco": "de",
    "fr": "fr", "fra": "fr", "french": "fr", "francese": "fr",
    "es": "es", "spa": "es", "spanish": "es", "spagnolo": "es",
}


def extract_language(query: str) -> Tuple[str, Optional[str]]:
    """Estrae un eventuale tag lingua (EN/ENG/IT/ITA…) dalla query.

    Ritorna (query_senza_tag, codice_lingua|None). Il tag si riconosce solo se
    NON è l'unico token (così 'it' da solo non viene interpretato).
    """
    toks = query.split()
    if len(toks) < 2:
        return query.strip(), None
    lang: Optional[str] = None
    kept: List[str] = []
    for t in toks:
        key = re.sub(r"[^a-z]", "", t.lower())
        if lang is None and key in LANG_ALIASES:
            lang = LANG_ALIASES[key]
            continue
        kept.append(t)
    if lang is None:
        return query.strip(), None
    return " ".join(kept).strip(), lang


def norm_number(x: Optional[str]) -> Optional[str]:
    """Normalizza un numero carta per il confronto: '04'->'4', '010'->'10',
    'TG03'->'tg03'. I numeri puramente numerici perdono gli zeri iniziali."""
    if x is None:
        return None
    s = str(x).strip().lower()
    if not s:
        return None
    if s.isdigit():
        return str(int(s))
    return s


@dataclass
class SetInfo:
    code: str
    slug: Optional[str]
    name: str


@dataclass
class SetIndex:
    by_code: Dict[str, SetInfo]
    by_name: Dict[str, SetInfo]  # nome normalizzato univoco -> set

    @classmethod
    def build(cls, raw_sets: List[dict]) -> "SetIndex":
        by_code: Dict[str, SetInfo] = {}
        name_groups: Dict[str, List[SetInfo]] = {}
        for s in raw_sets:
            code = s.get("code")
            if not code:
                continue
            info = SetInfo(code=code, slug=s.get("slug"), name=s.get("name") or "")
            by_code[code.lower()] = info
            key = " ".join(tokens(info.name))
            if key:
                name_groups.setdefault(key, []).append(info)
        by_name = {k: v[0] for k, v in name_groups.items() if len(v) == 1}
        return cls(by_code=by_code, by_name=by_name)

    def code_hint(self, tok: str) -> Optional[SetInfo]:
        """Sigla set SOLO se il token combacia con un code E contiene una cifra
        (evita le collisioni con i nomi Pokémon: 'mew' è anche il code di 151)."""
        info = self.by_code.get(tok.lower())
        if info and any(ch.isdigit() for ch in tok):
            return info
        return None

    def name_run(self, toks: List[str]) -> Tuple[Optional[SetInfo], set]:
        """Cerca il run contiguo più lungo che combacia ESATTAMENTE con il nome
        (normalizzato) di un set univoco. Ritorna (set, indici usati)."""
        n = len(toks)
        for length in range(n, 0, -1):
            for i in range(0, n - length + 1):
                key = " ".join(toks[i : i + length])
                info = self.by_name.get(key)
                if info:
                    return info, set(range(i, i + length))
        return None, set()


@dataclass
class Parsed:
    q: str
    set_code: Optional[str] = None
    name_tokens: List[str] = field(default_factory=list)
    number: Optional[str] = None
    set_label: Optional[str] = None


def parse_query(query: str, index: Optional[SetIndex]) -> Parsed:
    toks = tokens(query)
    if not toks:
        return Parsed(q=query.strip())

    used: set = set()
    set_code: Optional[str] = None
    set_label: Optional[str] = None

    if index is not None:
        for i, t in enumerate(toks):
            info = index.code_hint(t)
            if info:
                set_code, set_label = info.code, info.name
                used.add(i)
                break
        if set_code is None:
            info, idxs = index.name_run(toks)
            if info:
                set_code, set_label = info.code, info.name
                used |= idxs

    number: Optional[str] = None
    name_tokens: List[str] = []
    for i, t in enumerate(toks):
        if i in used:
            continue
        if number is None and _NUM.match(t) and any(c.isdigit() for c in t):
            number = norm_number(t)
        else:
            name_tokens.append(t)

    q_parts = list(name_tokens)
    # senza filtro set, tenere il numero nella q aiuta il ranking dell'API
    if number is not None and set_code is None:
        q_parts.append(number)
    q = " ".join(q_parts).strip()
    if not q and set_code is None:
        q = query.strip()
    return Parsed(
        q=q, set_code=set_code, name_tokens=name_tokens,
        number=number, set_label=set_label,
    )


def rank(items: List, parsed: Parsed) -> List:
    """Ri-ordina i candidati: numero esatto > copertura nome; stabile sull'ordine
    API a parità. `items` sono oggetti con .name e .number."""
    scored = []
    joined = " ".join(parsed.name_tokens)
    for idx, it in enumerate(items):
        s = 0.0
        name_toks = set(tokens(getattr(it, "name", "")))
        if parsed.number and norm_number(getattr(it, "number", None)) == parsed.number:
            s += 100
        for t in parsed.name_tokens:
            if t in name_toks:
                s += 12
        if joined and " ".join(tokens(getattr(it, "name", ""))) == joined:
            s += 20
        s -= idx * 0.01  # tie-break: preserva l'ordine API
        scored.append((s, idx, it))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [it for _, _, it in scored]
