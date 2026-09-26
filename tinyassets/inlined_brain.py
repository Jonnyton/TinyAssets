"""What this turn's prompt already quoted, so a re-read can say "nothing new".

Live 2026-09-26 on production ``ef63af30``, free account, a free model: the founder
asked "what's my favorite color again?" and the turn still ran ``rounds=3`` with
``tools=['read_brain']`` — it re-read ``founder.md`` although the persona prompt
quotes that file verbatim and (since #3998) says so. Telling a model the quoted text
is current does not make re-reading it expensive to prefer; making the re-read CHEAP
does, and it works whether the model obeys or not.

The engine ``read_brain`` handler serves a DIFFERENT request from the ``converse``
turn whose prompt it is talking about, so it cannot read the turn's context. Both run
in the one daemon process though, so this is an in-process registry: ``converse``
records the digest of each body it inlined, and ``read_brain`` compares that against
the file's CURRENT digest.

That comparison is what keeps it correct rather than merely cheap. It says nothing
about "did a write happen" — it asks the only question that matters, "is the text in
the prompt still the text on disk". A same-turn ``write_brain`` changes the digest, so
the read returns the fresh body with no coupling between the two handlers at all.
"""

from __future__ import annotations

import hashlib
import threading

#: (actor_id, graph_id) -> {filename: sha256 of the body the prompt quoted}. One
#: entry per pair, overwritten by each turn, so this cannot grow with traffic. Capped
#: anyway: a registry that can only grow is a leak waiting for a busy day.
_INLINED: dict[tuple[str, str], dict[str, str]] = {}
_LOCK = threading.Lock()

#: Distinct (actor, graph) pairs retained. Small: one per universe being served, and
#: a dropped entry only costs a full-body read, never a wrong answer.
MAX_TRACKED = 256


def digest(text: str) -> str:
    """The digest this module compares. One definition, used by both sides."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def record(actor_id: str, graph_id: str, bodies: dict[str, str]) -> None:
    """Record what THIS turn's prompt quoted verbatim. Replaces the prior turn's."""
    if not actor_id or not graph_id:
        return
    entry = {name: digest(body) for name, body in (bodies or {}).items() if body}
    with _LOCK:
        if len(_INLINED) >= MAX_TRACKED and (actor_id, graph_id) not in _INLINED:
            _INLINED.clear()
        _INLINED[(actor_id, graph_id)] = entry


def quoted(actor_id: str, graph_id: str) -> dict[str, str]:
    """Digests this turn's prompt quoted, or {} when nothing is known.

    Empty is the safe answer: every file then reads as changed and comes back in
    full, which is exactly the behaviour before this existed.
    """
    if not actor_id or not graph_id:
        return {}
    with _LOCK:
        return dict(_INLINED.get((actor_id, graph_id), {}))


def is_already_quoted(actor_id: str, graph_id: str, filename: str, body: str) -> bool:
    """Whether the prompt's copy of ``filename`` is still byte-identical to ``body``."""
    if not filename:
        return False
    known = quoted(actor_id, graph_id).get(filename)
    return bool(known) and known == digest(body)


def forget(actor_id: str, graph_id: str) -> None:
    """Drop what is known, so every file reads in full again (tests, teardown)."""
    with _LOCK:
        _INLINED.pop((actor_id, graph_id), None)
