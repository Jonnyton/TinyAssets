"""Model class and version, derived from the id alone.

No vendor names, no model names, no registry. Founder, 2026-09-26: "we also
should not have to put out new patches for providers so make sure it is made
provider agnostic always updates for users once one user adds the newly available
model." Anything that had to be taught a vendor's naming scheme would be a patch
per provider, which is the thing being avoided.

The rule, applied to the id's own tokens:

* a run of digits, or a dotted run of digits, is a VERSION token;
* an 8-digit date stamp is a VERSION token (a date sorts as a number, which is
  all that is needed of it);
* every other token -- including a named suffix like ``sol`` -- is CLASS.

So ``claude-opus-4-6`` and ``claude-opus-4-7`` share the class ``claude-opus``
and only the higher one is the newest of that class, while ``gpt-5.6-sol`` and
``gpt-5.7-astra`` are different classes: a named suffix reads as a distinct line,
not as a newer version of its sibling. That distinction is the one a caller would
otherwise need vendor knowledge to make.

An id with no version token is its own class with an empty version. An id that
cannot be tokenised at all is its own class. Never a guess.
"""

from __future__ import annotations

import re

#: Separators an id may use between tokens. Both are common and neither is
#: privileged: `gpt-5.6-sol` mixes them in one id.
_SPLIT = re.compile(r"[-_/]")
#: A version token: digits, or digits separated by dots (``5``, ``4.6``,
#: ``20260115``). A date stamp needs no special case -- it is already a run of
#: digits, and comparing it as a number orders dates correctly.
_VERSION_TOKEN = re.compile(r"\A[0-9]+(?:\.[0-9]+)*\Z")


def _version_parts(token: str) -> tuple[int, ...]:
    return tuple(int(part) for part in token.split("."))


def model_class_and_version(model_id: str) -> tuple[str, tuple[int, ...]]:
    """Return ``(class, version)`` for one model id.

    ``class`` is the id with its version tokens removed, joined by ``-``.
    ``version`` is the version tokens in the order they appeared, flattened, so
    ``4-6`` and ``4.6`` describe the same version and compare equal.

    A blank or non-string id is refused rather than bucketed: an unnamed model is
    a caller bug, and silently giving it a class would let it win a "newest"
    comparison against real ids.
    """
    if type(model_id) is not str or not model_id.strip():
        raise ValueError("model id must be a non-empty string")
    tokens = [token for token in _SPLIT.split(model_id.strip()) if token]
    if not tokens:
        # Separators only. It cannot be tokenised, so it is its own class -- the
        # rule for anything unparseable, applied rather than excepted.
        return model_id.strip(), ()
    class_tokens: list[str] = []
    version: list[int] = []
    for token in tokens:
        if _VERSION_TOKEN.match(token):
            version.extend(_version_parts(token))
        else:
            class_tokens.append(token)
    # Every token was a version (an id that is only numbers). It has no class of
    # its own to share, so it is its own class and keeps its version.
    if not class_tokens:
        return model_id.strip(), tuple(version)
    return "-".join(class_tokens), tuple(version)


def newer(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    """Is version ``left`` newer than ``right``?

    Tuples of different lengths compare on their common prefix first; when one is
    a prefix of the other the longer one is newer, so ``(4, 6, 20260115)`` is
    newer than ``(4, 6)`` -- a dated build of a version is a later build of it.
    Python's tuple ordering already does exactly this.
    """
    return left > right


def newest_per_class(rows):
    """Reduce rows to the newest model of each class.

    ``rows`` is any iterable of objects with ``model_id`` and ``first_verified_at``.
    A tie on version is broken by the EARLIER first-verified time: the id that has
    been known to work longest wins, rather than whichever row was read first.

    An id that cannot be given a class is returned as its own class, so it is
    never dropped for being unusual.
    """
    best: dict[str, tuple[tuple[int, ...], str, object]] = {}
    for row in rows:
        try:
            klass, version = model_class_and_version(row.model_id)
        except ValueError:
            continue  # a row with no usable id is not a model anyone can select
        seen = best.get(klass)
        stamp = str(getattr(row, "first_verified_at", "") or "")
        if seen is None or newer(version, seen[0]) or (version == seen[0] and stamp < seen[1]):
            best[klass] = (version, stamp, row)
    return [entry[2] for entry in best.values()]
