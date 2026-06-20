"""Store dei gruppi/canali dove il bot è stato aggiunto.

Serve al digest giornaliero (top movers): per postare "in uno dei tuoi gruppi"
il bot deve sapere dove si trova. Telegram lo notifica con un update
`my_chat_member` ogni volta che entra o esce da una chat; qui lo persistiamo
su un file JSON.

La logica di decisione (è presente? è una chat dove ha senso postare?) è pura e
testabile; l'I/O è isolato in `GroupStore`.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# tipi di chat in cui ha senso postare un digest (private/no)
TRACKABLE_CHAT_TYPES = ("group", "supergroup", "channel")

# stati ChatMember che contano come "il bot è dentro la chat"
_PRESENT_STATUSES = ("member", "administrator", "creator")


def is_trackable_chat(chat_type: Optional[str]) -> bool:
    """True per gruppi/supergruppi/canali (dove un digest ha senso)."""
    return chat_type in TRACKABLE_CHAT_TYPES


def membership_is_present(status: Optional[str], is_member: Optional[bool]) -> bool:
    """True se, con questo stato, il bot risulta effettivamente nella chat.

    `restricted` conta solo se `is_member` è vero (un bot può essere ristretto
    ma ancora membro). `left`/`kicked` = fuori.
    """
    if status in _PRESENT_STATUSES:
        return True
    if status == "restricted":
        return bool(is_member)
    return False


@dataclass
class Group:
    chat_id: int
    type: str
    title: Optional[str] = None
    added_by: Optional[int] = None  # user id di chi ha aggiunto il bot
    is_admin: bool = False          # il bot è admin? (serve per postare nei canali)


class GroupStore:
    """Persistenza JSON dei gruppi/canali noti.

    Single-writer: il polling di PTB processa gli update in serie, quindi non
    servono lock. Ogni mutazione riscrive il file in modo atomico.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._groups: Dict[int, Group] = {}
        self._load()

    # --- I/O ---------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            logger.warning("Store gruppi illeggibile (%s), riparto vuoto", self._path)
            return
        for rec in raw.get("groups", []):
            try:
                g = Group(
                    chat_id=int(rec["chat_id"]),
                    type=rec.get("type", "group"),
                    title=rec.get("title"),
                    added_by=rec.get("added_by"),
                    is_admin=bool(rec.get("is_admin", False)),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._groups[g.chat_id] = g

    def _save(self) -> None:
        payload = {"groups": [asdict(g) for g in self._groups.values()]}
        target_dir = os.path.dirname(os.path.abspath(self._path))
        os.makedirs(target_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except OSError:
            logger.exception("Salvataggio store gruppi fallito")
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # --- API ---------------------------------------------------------------
    def upsert(self, group: Group) -> None:
        self._groups[group.chat_id] = group
        self._save()

    def remove(self, chat_id: int) -> None:
        if chat_id in self._groups:
            del self._groups[chat_id]
            self._save()

    def all(self) -> List[Group]:
        return list(self._groups.values())

    def for_owner(self, owner_id: int) -> List[Group]:
        """I gruppi/canali aggiunti da uno specifico utente (i 'tuoi gruppi')."""
        return [g for g in self._groups.values() if g.added_by == owner_id]

    def __len__(self) -> int:
        return len(self._groups)
