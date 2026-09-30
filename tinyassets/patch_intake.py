"""The one connection the platform offers a new universe: a way to report gaps.

Founder, 2026-09-30:

    "for new users the request that enables connection to the tinyassets universe
    for patch requests should be already there when they first login just like
    the connect another llm one is already there from the start."

A *patch request* is how a user's universe tells TinyAssets about a gap -- a bug,
a missing capability, an idea. It files one itself, mid-turn, without
interrupting its user. The receiving side is an ordinary user's intake: the
founder's universe built it through the app like anybody else, and its owner's
own gate decides each request. The founder's universe is *one* intake owner, not
a privileged one, which is exactly why the platform must be told WHICH intake to
offer rather than knowing one by name -- see :func:`configured_intake`.

Why a seeded consent request rather than an automatic connection
----------------------------------------------------------------
Sending a patch request means sending the user's words to ANOTHER USER. That is
the cross-user floor, so it is the user's yes to give, not the platform's to
assume. The ask is seeded into the same "Waiting on you" rail the model-connect
entry uses, with nothing to paste: approving it records ONE grant naming exactly
the configured intake.

What went wrong without it (live, 2026-09-30, free account
``u-01ky3zh1arr8qth8jee7zx63pq``): with no connection and nothing telling it one
existed, the universe invented its own pending request asking its user for a
bearer token -- a credential field for an address that needs no credential, and a
help link that 404ed. A universe cannot ask for a connection nobody told it
about, so the platform seeds this one, exactly as it synthesizes the
model-connect entry.

The grant is the authority, and it is narrow
--------------------------------------------
The grant is an ordinary effector consent: sink ``patch_intake``, destination
the intake's ``receiver_id``. ``effector_consents`` matches destinations exactly
and has no wildcards, so one grant can only ever name one intake -- "send-only
access to that one intake, nothing else" is structural rather than promised.
:func:`require_send_consent` is where it bites: a delivery to the configured
intake without an active grant is refused, so approving the ask is what actually
creates the connection.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Effector-consent sink for "this universe may send patch requests to <intake>".
#: Its destination is the intake's ``receiver_id`` verbatim, so the grant cannot
#: describe a wider reach than one receiver.
PATCH_INTAKE_SINK = "patch_intake"

#: The pending-request action type whose answer records the grant above.
ACTION_TYPE = "grant_patch_intake"

#: Tab header for the seeded ask. Bounded by ``_MAX_KIND_CHARS`` (24).
REQUEST_KIND = "TinyAssets"

#: Which intake new universes are offered. NOT a universe id and NOT a code
#: constant: the platform names the intake, and any user could own it.
RECEIVER_ID_VAR = "TINYASSETS_PATCH_INTAKE_RECEIVER_ID"

#: What the platform calls that intake on screen. Display text only; it confers
#: nothing and names no universe.
LABEL_VAR = "TINYASSETS_PATCH_INTAKE_LABEL"

DEFAULT_LABEL = "TinyAssets"

#: A receiver id is an address: bounded, no whitespace, and never ``*`` (which
#: ``storage/receiver_links._name`` refuses everywhere for the same reason -- a
#: sentinel that means "any" must not be spellable as a name).
_RECEIVER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

#: Bounded, single-line, printable. The label lands in prose a person reads.
_MAX_LABEL_CHARS = 48


class PatchIntakeMisconfigured(ValueError):
    """The intake is configured, but not to something that can be offered.

    Distinct from "unset" on purpose: unset means the platform offers no intake
    and says nothing, which is a legitimate deployment. A present-but-invalid
    value is an operator error, and silently treating it as unset is the mock
    fallback Hard Rule 8 forbids.
    """


class PatchIntakeConsentMissing(ValueError):
    """A delivery to the configured intake with no grant behind it."""


def configured_intake() -> dict[str, str] | None:
    """``{"receiver_id", "label"}`` for the offered intake, or ``None`` if unset.

    Raises :class:`PatchIntakeMisconfigured` when a value is present but cannot
    be an address or a label. Callers on a user-facing read path catch that and
    log it rather than breaking the rail; callers deciding authority let it
    propagate.
    """
    raw = os.environ.get(RECEIVER_ID_VAR)
    if raw is None or not raw.strip():
        return None
    receiver_id = raw.strip()
    if not _RECEIVER_ID_RE.match(receiver_id):
        raise PatchIntakeMisconfigured(
            f"{RECEIVER_ID_VAR} must be 8-128 characters of [A-Za-z0-9._:-] "
            f"naming one receiver; got {receiver_id!r}"
        )
    label = (os.environ.get(LABEL_VAR) or DEFAULT_LABEL).strip()
    if not label or len(label) > _MAX_LABEL_CHARS or not label.isprintable():
        raise PatchIntakeMisconfigured(
            f"{LABEL_VAR} must be 1-{_MAX_LABEL_CHARS} printable characters on "
            f"one line; got {label!r}"
        )
    return {"receiver_id": receiver_id, "label": label}


def _intake_or_none(where: str) -> dict[str, str] | None:
    """Read the configuration on a path that must never raise into a user's face."""
    try:
        return configured_intake()
    except PatchIntakeMisconfigured as exc:
        # LOUD, and not once-per-process quiet: an operator reading logs is the
        # only person who can fix this, and nothing else in the product will
        # complain. Nothing is seeded and nothing is granted, so no surface
        # pretends the connection exists.
        logger.error("patch intake is misconfigured (%s): %s", where, exc)
        return None


def consent_is_active(universe_dir: str | Path, receiver_id: str) -> bool:
    """Whether this universe currently holds the grant for exactly this intake."""
    from tinyassets.storage.effector_consents import is_consent_active

    if not receiver_id:
        return False
    return is_consent_active(
        universe_dir, sink=PATCH_INTAKE_SINK, destination=receiver_id
    )


def grant_send_consent(
    universe_dir: str | Path, *, receiver_id: str, granted_by: str
) -> dict[str, Any]:
    """Record the one grant. Raises for an id that is not an address."""
    from tinyassets.storage.effector_consents import grant_consent

    if not _RECEIVER_ID_RE.match(str(receiver_id or "")):
        raise ValueError("a patch-intake grant names one receiver id")
    return grant_consent(
        universe_dir,
        sink=PATCH_INTAKE_SINK,
        destination=receiver_id,
        granted_by=granted_by,
    )


def require_send_consent(*, universe_dir: str | Path, receiver_id: str) -> None:
    """Fence the configured intake behind its grant. Other receivers untouched.

    Only the intake the PLATFORM offers is gated here, and deliberately: every
    other receiver is one this universe found itself, where the receiving owner's
    own exposure (``open_to_all`` / ``allowed_senders``) is the whole authority
    and the platform has no consent to hold. The offered intake is different --
    the platform put the address in front of the universe, so the platform holds
    the user's yes for it.

    A present-but-invalid configuration gates NOTHING here, and that is not a
    fail-open. An invalid value means no intake is being offered: nothing was
    ever granted under it and no universe was handed an address by the platform.
    Any receiver a universe reached on its own -- including, if it discovered it,
    the one an operator meant to name -- is governed by its owner's exposure,
    exactly as every other receiver is. Refusing every delivery instead would
    break unrelated cross-user work over a typo in one variable, on a surface
    nobody would connect to that variable.
    """
    intake = _intake_or_none("fencing a delivery")
    if intake is None or intake["receiver_id"] != str(receiver_id or ""):
        return
    if not consent_is_active(universe_dir, intake["receiver_id"]):
        raise PatchIntakeConsentMissing(
            "patch_intake_consent_required: sending to the "
            f"{intake['label']} patch intake needs the owner's approval of the "
            '"Report a problem" request in their rail; nothing has been sent'
        )


def _seeded_rows(universe_dir: Path) -> list[dict[str, Any]]:
    from tinyassets.storage.pending_requests import find_by_action_type

    return find_by_action_type(universe_dir, ACTION_TYPE)


def _already_answered(rows: list[dict[str, Any]], receiver_id: str) -> bool:
    """Whether this user already decided THIS intake, however they decided it.

    Keyed on the receiver id rather than on the request's dedupe key, because the
    dedupe key is a hash of the rendered text: reword the title and every past
    answer stops matching, so a user who declined would be asked again on the
    next deploy. The intake's address is what the decision was actually about.
    """
    return any(
        row["status"] != "pending"
        and str((row.get("action") or {}).get("receiver_id") or "") == receiver_id
        for row in rows
    )


def request_payload(intake: dict[str, str]) -> dict[str, Any]:
    """The seeded ask, in the user's words. No fields: there is nothing to paste."""
    label = intake["label"]
    return {
        "kind": REQUEST_KIND,
        "title": f"Let your universe report problems to {label}",
        "body": (
            f"When your universe hits a bug, a missing feature or an idea worth "
            f"building, it can tell {label} directly instead of stopping. "
            "Approving this lets it send those reports -- what it was trying to "
            "do and what was missing -- and nothing else: not your files, not "
            "your conversations, not your other work. Whoever runs the intake "
            "sees only what your universe sends them, and you can take this back "
            "at any time. There is nothing to paste."
        ),
        "fields": [],
        "action": {"type": ACTION_TYPE, "receiver_id": intake["receiver_id"],
                   "label": label},
    }


def seed_consent_request(
    universe_id: str, universe_dir: Path, *, view: dict[str, Any] | None = None
) -> None:
    """Put the ask in this universe's rail if it is owed one. Never raises.

    Runs on the rail read, which is the same code path every account and every
    surface already uses -- so it is there at a new user's first sign-in for the
    same reason the model-connect entry is, and an EXISTING user gets it on their
    next sign-in without a migration. Idempotent by four separate checks, in
    increasing cost order:

    1. no intake configured -> nothing to offer;
    2. the grant is already held -> the connection exists;
    3. an ask for this intake is already pending -> it is already in their face;
    4. this intake was already answered, denied or cleared -> they decided.

    ``create_request`` then adds its own two: a pending row with an identical
    dedupe key is returned rather than duplicated, and a standing "don't ask me
    this again" is honoured by not creating one at all.

    ``view`` lets the rail read hand over what :func:`rail_view` already worked
    out, so one poll opens the consent store once rather than twice. It is the
    same answer either way; passing nothing simply recomputes it.
    """
    if view is not None:
        intake = {"receiver_id": view["receiver_id"], "label": view["label"]}
        if view["granted"]:
            return
    else:
        intake = _intake_or_none("seeding the rail entry")
        if intake is None:
            return
    try:
        if view is None and consent_is_active(universe_dir, intake["receiver_id"]):
            return
        rows = _seeded_rows(universe_dir)
        if any(row["status"] == "pending" for row in rows):
            return
        if _already_answered(rows, intake["receiver_id"]):
            return
    except Exception:  # noqa: BLE001 - a rail that cannot seed must still render
        logger.warning("patch intake: could not decide whether to seed", exc_info=True)
        return

    import json

    from tinyassets.api.pending_requests import request_from_user

    result = request_from_user(
        universe_id=universe_id,
        origin="platform",
        payload=json.dumps(request_payload(intake)),
    )
    if isinstance(result, dict) and result.get("error"):
        # Reported, never silent: the rail still renders, but an operator can see
        # that the one connection the platform offers did not reach this user.
        logger.warning(
            "patch intake: seeding the consent request failed for %s: %s",
            universe_id,
            result.get("detail") or result.get("error"),
        )


def rail_view(universe_dir: Path) -> dict[str, Any] | None:
    """What the rail read tells the universe about the offered intake.

    Carried on the rail rather than in the resident tool description because the
    agent polls the rail anyway: it costs no per-round bytes and it is current.
    ``how`` is the short version of the ``delivering`` handbook chapter -- enough
    that a universe never has to guess, and specifically enough that it never
    invents a credential ask for an address that needs no credential.
    """
    intake = _intake_or_none("the rail view")
    if intake is None:
        return None
    granted = False
    try:
        granted = consent_is_active(universe_dir, intake["receiver_id"])
    except Exception:  # noqa: BLE001 - the rail must render either way
        logger.warning("patch intake: consent read failed", exc_info=True)
    return {
        "receiver_id": intake["receiver_id"],
        "label": intake["label"],
        "granted": granted,
        "how": (
            'Read its contract with read_graph target="receiver" query='
            f'"{intake["receiver_id"]}", connect one of your own step\'s outputs '
            'with write_graph target="output_link" operation="connect", then send '
            'with run_graph operation="deliver_output". No credential, no URL and '
            "no token is involved -- see the handbook chapter "
            'write_graph.delivering.'
            if granted else
            f"Your user has not approved sending to {intake['label']} yet. The "
            'request "Let your universe report problems to '
            f'{intake["label"]}" is already waiting in their rail -- point them '
            "at it. Do NOT raise a connection or credential request for this: "
            "there is no token, and approving that one request is the whole setup."
        ),
    }


__all__ = [
    "ACTION_TYPE",
    "DEFAULT_LABEL",
    "LABEL_VAR",
    "PATCH_INTAKE_SINK",
    "PatchIntakeConsentMissing",
    "PatchIntakeMisconfigured",
    "RECEIVER_ID_VAR",
    "REQUEST_KIND",
    "configured_intake",
    "consent_is_active",
    "grant_send_consent",
    "rail_view",
    "request_payload",
    "require_send_consent",
    "seed_consent_request",
]
