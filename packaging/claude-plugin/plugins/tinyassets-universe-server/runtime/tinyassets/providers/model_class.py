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

    ``class`` is the id with its version tokens REMOVED IN PLACE -- every remaining
    separator is exactly the one the id used. ``version`` is the version tokens in
    the order they appeared, flattened, so ``4-6`` and ``4.6`` describe the same
    version and compare equal.

    Removing in place rather than re-joining the surviving tokens matters twice.
    ``some_model`` and ``some-model`` stay two classes, where normalising both to
    ``some-model`` collapsed them and made ``newest_per_class`` discard one (Codex
    on #4028). And a mixed-separator id like ``vendor/thing-2.5-turbo`` keeps its
    own shape (``vendor/thing-turbo``) instead of being rewritten with whichever
    separator happened to come first.

    A blank or non-string id is refused rather than bucketed: an unnamed model is
    a caller bug, and silently giving it a class would let it win a "newest"
    comparison against real ids.
    """
    if type(model_id) is not str or not model_id.strip():
        raise ValueError("model id must be a non-empty string")
    text = model_id.strip()
    # Keep the separators: `parts` alternates token, separator, token, ...
    parts = _SPLIT.split(text)
    separators = _SPLIT.findall(text)
    version: list[int] = []
    kept: list[str] = []
    kept_separators: list[str] = []
    pending_separator = ""
    for index, token in enumerate(parts):
        if token and _VERSION_TOKEN.match(token):
            version.extend(_version_parts(token))
            # Remember the separator that led INTO this version so the next
            # surviving token inherits it instead of the one that followed.
            if not pending_separator and index:
                pending_separator = separators[index - 1]
            continue
        if kept:
            # The separator BEFORE the run of version tokens just dropped, not the
            # one after it. Codex round 2 on #4028: taking the following separator
            # made `vendor/2-model` and `vendor-2-model` both collapse to
            # `vendor-model`, so one of two distinct ids could disappear. Keeping
            # the leading separator preserves `vendor/model` and `vendor-model`.
            kept_separators.append(pending_separator if pending_separator else (
                separators[index - 1] if index else ""))
        kept.append(token)
        pending_separator = ""
    # Nothing but versions and separators: no class of its own to share, so it is
    # its own class -- the rule for anything unparseable, applied not excepted.
    if not any(kept):
        return text, tuple(version)
    klass = kept[0]
    for separator, token in zip(kept_separators, kept[1:], strict=True):
        klass += separator + token
    return klass, tuple(version)


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
    The winner of a class is decided by: higher version, then the EARLIER
    first-verified time (the id known to work longest), then the lower model id.

    That last tiebreak is not cosmetic. Equal version AND equal timestamp used to
    fall back to input order, so the same catalog could answer differently
    depending on how rows were read (Codex on #4028). Arbitrary but STABLE beats
    arbitrary.

    An id that cannot be given a class is returned as its own class, so it is
    never dropped for being unusual.
    """
    best: dict[str, tuple[tuple[int, ...], str, str, object]] = {}
    for row in rows:
        try:
            klass, version = model_class_and_version(row.model_id)
        except ValueError:
            continue  # a row with no usable id is not a model anyone can select
        stamp = str(getattr(row, "first_verified_at", "") or "")
        # Higher version wins, so the version is compared as-is; among equals the
        # smaller (stamp, id) wins, so it is negated by comparing the incumbent.
        candidate = (version, stamp, str(row.model_id), row)
        seen = best.get(klass)
        if (seen is None
                or candidate[0] > seen[0]
                or (candidate[0] == seen[0] and candidate[1:3] < seen[1:3])):
            best[klass] = candidate
    return [best[klass][3] for klass in sorted(best)]


def superseded_by(model_id: str, known) -> str | None:
    """The newest KNOWN sibling of ``model_id``'s class, if one is newer than it.

    ``known`` is any iterable of objects with ``model_id`` and ``first_verified_at``.
    Returns that sibling's id, or ``None`` when nothing known is newer.

    This is the vendor-free reading of "a smart recent big model": not a list of
    names, and not "is a member of the published newest set" -- which cannot work,
    because an EMPTY catalog has no newest set, so no confirmer could ever qualify
    and the catalog could never fill (the bootstrap deadlock).

    "Not superseded" inverts that and is monotone. With nothing known, nothing is
    newer, so a first confirmer qualifies; as the catalog fills, the bar rises on
    its own. It cannot be gamed downward either: publishing more of your own OLDER
    ids never makes yours the newest of its class, and the id in question is the one
    a turn actually RAN on, so it cannot be invented.

    An unparseable id is its own class, so it is never superseded by anything --
    which is right: nothing known is comparable to it.
    """
    klass, version = model_class_and_version(model_id)
    for row in newest_per_class(known):
        other_class, other_version = model_class_and_version(row.model_id)
        if other_class == klass and newer(other_version, version):
            return row.model_id
    return None
