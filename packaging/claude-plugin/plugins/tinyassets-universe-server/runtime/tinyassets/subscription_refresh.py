"""Refresh a deposited subscription document on the PLATFORM side, before launch.

A CLI provider is launched with a throwaway read-only copy of the vault's
``llm_subscription`` document (``credential_vault.snapshot_llm_subscription_credential``).
The CLI refreshes its own token when that document is near expiry -- and on the
sandboxed path it cannot even do that, because ``/codex-home`` is a tmpfs with
each credential file bound read-only, so the write fails. Either way the source
rotates the refresh token and the rotation never reaches the vault, so every
later launch replays a spent single-use refresh token and the source answers that
it was already used. That is the founder's subscription failing every turn since
2026-09-24.

So the platform refreshes first, through the ONE shared core
(:func:`tinyassets.credential_refresh.refresh_credential`): under the
per-credential thread and file locks, with the vault's exclusive admission held
BEFORE the refresh token is spent, and the rotated document written atomically
under that hold. The launch copy is then taken from a document that does not need
refreshing, so nothing inside the jail has to.

Two things this deliberately does NOT do:

- It does not refresh a document whose freshness cannot be read. A document with
  no expiry and no ``last_refresh`` may be a shape this code did not write, and
  spending its refresh token on a guess is the one irreversible move here.
- It does not refresh a record that stores its document as a PATH rather than
  inline. Writing the document inline would clear the record's path fields
  (``_merge_subscription_records`` drops the whole alias slot), silently
  migrating the owner's storage shape as a side effect of a refresh. Such a
  record launches exactly as it does today.

Nothing here logs, returns or formats the document or any token in it.
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tinyassets.credential_refresh import (
    RefreshError,
    RefreshRejected,
    RefreshUnavailable,
    refresh_credential,
)

#: Refresh when the access token is within this long of expiry. Matches the
#: ``oauth2`` connection skew so one owner's two credential kinds do not drift.
REFRESH_SKEW_SECONDS = 60.0

#: Refresh when the stored document's own ``last_refresh`` is older than this.
#: The CLI refreshes on its own schedule when it can; the platform must get
#: there first, so this is deliberately shorter than any CLI threshold observed
#: (the Codex CLI's is 28 days). A document refreshed within the window is left
#: alone, so an ordinary turn does no network work.
REFRESH_AGE_SECONDS = 12 * 3600.0

logger = logging.getLogger(__name__)

_MAX_DOCUMENT_BYTES = 128 * 1024
_TIMEOUT = 20.0

#: Token-endpoint error codes and phrases that mean the STORED refresh token is
#: finished: no retry of it helps and only the owner signing in again produces a
#: new one. Everything else is transient.
_TERMINAL_CODES = frozenset({"invalid_grant", "invalid_client", "unauthorized_client"})
_TERMINAL_PHRASES = (
    "already been used",
    "already used",
    "sign in again",
    "log in again",
    "reauthenticate",
    "re-authenticate",
)


@dataclass(frozen=True)
class _Document:
    """One stored subscription document, parsed. Never rendered anywhere."""

    text: str
    access_token: str
    refresh_token: str
    id_token: str
    last_refresh: str
    expires_at: float | None

    def encoded(self) -> str:
        return base64.b64encode(self.text.encode("utf-8")).decode("ascii")


def _claim_expiry(token: str) -> float | None:
    """``exp`` from an unverified JWT payload, or None for anything else.

    Unverified on purpose: this is a freshness HINT about our own stored token,
    never an authorization decision. A token that is not a JWT (an opaque
    string) simply has no readable expiry, which is a supported answer.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        value = claims.get("exp")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)
    except Exception:  # noqa: BLE001 - an unreadable token has no expiry, never raises
        return None


def _parse(encoded: str) -> _Document:
    """Parse the stored base64 document. Raises :class:`RefreshError` on any
    shape this module will not spend a refresh token against."""
    try:
        raw = base64.b64decode(encoded.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise RefreshError("the stored authorization is unreadable; reconnect") from None
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise RefreshError("the stored authorization is unreadable; reconnect")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        # `ValueError.doc` on a JSONDecodeError is the WHOLE document, i.e. every
        # token in it. Nothing from the exception is chained or interpolated.
        raise RefreshError("the stored authorization is unreadable; reconnect") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("tokens"), dict):
        raise RefreshError("the stored authorization is unreadable; reconnect")
    tokens = doc["tokens"]
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    if not isinstance(access, str) or not isinstance(refresh, str):
        raise RefreshError("the stored authorization is unreadable; reconnect")
    identity = tokens.get("id_token")
    stamp = doc.get("last_refresh")
    return _Document(
        text=raw.decode("utf-8"),
        access_token=access,
        refresh_token=refresh,
        id_token=identity if isinstance(identity, str) else "",
        last_refresh=stamp if isinstance(stamp, str) else "",
        expires_at=_claim_expiry(access),
    )


def _stamp_age(last_refresh: str, now: float) -> float | None:
    """How long ago ``last_refresh`` was, or None when it cannot be read."""
    text = (last_refresh or "").strip()
    if not text:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return now - parsed.timestamp()


def document_is_stale(document: _Document, now: float) -> bool:
    """Whether this stored document must be replaced before a launch.

    True when the access token is within the skew of expiry, or when the
    document's own refresh stamp is older than the platform's threshold. A
    document with NEITHER a readable expiry NOR a readable stamp is not stale:
    see this module's docstring on why a guess is not made here.
    """
    if document.expires_at is not None and now >= document.expires_at - REFRESH_SKEW_SECONDS:
        return True
    age = _stamp_age(document.last_refresh, now)
    return age is not None and age >= REFRESH_AGE_SECONDS


def _terminal(status: int, body: Any) -> bool:
    """Whether the endpoint's refusal is about the stored refresh token itself.

    Only a 4xx can be, and only when its own words say so: a 400 with no code is
    as likely to be a transport or proxy artefact, and treating that as a dead
    credential would ask the owner to sign in again over a blip.
    """
    if not 400 <= status < 500:
        return False
    code = ""
    description = ""
    if isinstance(body, dict):
        code = str(body.get("error") or "").strip().lower()
        description = str(body.get("error_description") or "").strip().lower()
    if code in _TERMINAL_CODES:
        return True
    return any(phrase in description for phrase in _TERMINAL_PHRASES)


def _spend(document: _Document, *, token_url: str, client_id: str) -> _Document:
    """RFC 6749 section 6 against the source's token endpoint, one attempt.

    Sent through the SSRF-hardened broker transport
    (:func:`tinyassets.connection_oauth.transport.request_json`), the same one the
    ``oauth2`` connection refresh uses -- not a plain client. The endpoint is
    derived from an UNSIGNED identity token, so the request carries a refresh
    token to a URL this process did not choose: HTTPS validation, the SSRF driver,
    the body cap and the secret scrubbing are exactly the protections that makes
    safe. A plain client here would have been a token-exfiltration path (Codex
    refute-review, P1 #1).

    A source that rotates returns a new refresh token; one that does not leaves
    the old one valid, so it is kept. The response is read field by field --
    never merged wholesale into the stored document, which would let the
    endpoint add keys to a document a subprocess is launched with.
    """
    from tinyassets.connection_oauth.transport import (
        OAuthError,
        request_json,
        validate_https_url,
    )

    secrets = tuple(
        value for value in (document.refresh_token, document.access_token, document.id_token)
        if value
    )
    try:
        validate_https_url(token_url)
        status, body = request_json("POST", token_url, form={
            "grant_type": "refresh_token",
            "refresh_token": document.refresh_token,
            "client_id": client_id,
        }, secrets=secrets)
    except ValueError:
        raise RefreshUnavailable("the sign-in endpoint is not usable") from None
    except OAuthError:
        # The transport's own failure (unreachable, refused host, oversized body).
        # Its detail is scrubbed but describes OUR request, so it is not echoed.
        raise RefreshUnavailable("the sign-in service could not be reached") from None
    if status >= 400:
        if _terminal(status, body):
            raise RefreshRejected(
                "the stored sign-in is no longer accepted; sign in again")
        raise RefreshUnavailable(f"the sign-in service answered {status}")
    if not isinstance(body, dict):
        raise RefreshUnavailable("the sign-in service answered in an unreadable shape")
    access = body.get("access_token")
    if not isinstance(access, str) or not access:
        raise RefreshUnavailable("the sign-in service returned no usable authorization")
    rotated = body.get("refresh_token")
    identity = body.get("id_token")
    return _rebuild(
        document,
        access_token=access,
        refresh_token=rotated if isinstance(rotated, str) and rotated else document.refresh_token,
        id_token=identity if isinstance(identity, str) and identity else document.id_token,
    )


def _rebuild(
    document: _Document, *, access_token: str, refresh_token: str, id_token: str,
) -> _Document:
    """The stored document with its tokens replaced and its stamp moved forward.

    Every other key the owner's sign-in wrote (auth mode, account id, and
    anything a newer CLI added) is preserved: the launch copy must stay the
    document the CLI reads, not a subset this module happens to know about.
    """
    doc = json.loads(document.text)
    tokens = dict(doc.get("tokens") or {})
    tokens["access_token"] = access_token
    tokens["refresh_token"] = refresh_token
    if id_token:
        tokens["id_token"] = id_token
    doc["tokens"] = tokens
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    doc["last_refresh"] = stamp
    text = json.dumps(doc)
    return _Document(
        text=text,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=tokens.get("id_token") or "",
        last_refresh=stamp,
        expires_at=_claim_expiry(access_token),
    )


def _stored(universe_dir: Path, service: str) -> tuple[dict[str, Any], str] | None:
    """The one subscription record for ``service`` and its inline document.

    None when there is no record, when there is more than one (the launch path
    refuses that too), or when the record stores a PATH instead of a document.
    """
    from tinyassets.credential_vault import load_credential_vault

    key = service.strip().lower()
    records = [
        record
        for record in load_credential_vault(universe_dir)
        if record.get("credential_type") == "llm_subscription"
        and str(record.get("service") or "").strip().lower() == key
    ]
    if len(records) != 1:
        return None
    record = records[0]
    encoded = record.get("auth_json_b64")
    if not isinstance(encoded, str) or not encoded.strip():
        return None
    return record, encoded.strip()


def refresh_before_launch(
    *,
    universe_dir: str | Path,
    service: str,
    owner_user_id: str,
    universe_id: str,
    token_url: str = "",
    client_id: str = "",
    now: float | None = None,
) -> bool:
    """Bring this universe's stored subscription document up to date.

    Returns True when a rotated document was written, False when nothing needed
    doing (no inline document, not stale, or another holder had already done it).
    Raises :class:`~tinyassets.credential_refresh.RefreshRejected` when the
    stored refresh token itself is finished, and
    :class:`~tinyassets.credential_refresh.RefreshUnavailable` for a transport or
    5xx failure — the caller decides what each means for the turn.

    Call BEFORE custody is resolved. Writing the vault changes
    ``_subscription_record_digest``, which is pinned into the provider binding,
    so a record rotated after custody resolution would make the launch refuse
    with "credential changed before launch snapshot". :func:`renew_accepted_source`
    is what carries the binding forward.
    """
    universe = Path(universe_dir)
    key = service.strip().lower()
    stored = _stored(universe, key)
    if stored is None:
        return False
    moment = time.time() if now is None else now
    document = _parse(stored[1])
    if not document_is_stale(document, moment):
        return False
    endpoint, identifier = _source_endpoint(document, token_url, client_id)
    if not endpoint or not identifier:
        # The credential does not say where it came from, or that issuer publishes
        # no usable metadata: launch with what is stored, exactly as before. Not a
        # failure, and not a place to guess a URL.
        return False
    rotated = False

    def read() -> _Document:
        current = _stored(universe, key)
        if current is None:
            raise RefreshError("the stored authorization is unreadable; reconnect")
        return _parse(current[1])

    def stale(current: _Document) -> bool:
        # Re-decided on the re-read: a holder before us may already have rotated,
        # and spending a single-use refresh token twice is the bug being fixed.
        return document_is_stale(current, time.time())

    def spend(current: _Document) -> _Document:
        nonlocal rotated
        fresh = _spend(current, token_url=endpoint, client_id=identifier)
        rotated = True
        return fresh

    from tinyassets.credential_vault import llm_subscription_credential_record

    refresh_credential(
        universe_dir=universe,
        lock_id=f"llm_subscription::{key}",
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        read=read,
        stale=stale,
        spend=spend,
        records=lambda fresh: [
            llm_subscription_credential_record(
                service=key,
                auth_json_b64=fresh.encoded(),
                last_refresh=fresh.last_refresh,
            )
        ],
        subject="sign-in",
    )
    return rotated


def _claims(token: str) -> dict[str, Any]:
    """The unverified claim set of a JWT, or an empty mapping.

    Unverified deliberately: nothing here is an authorization decision. These are
    claims about OUR OWN stored credential, read to find out where it came from.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return claims if isinstance(claims, dict) else {}
    except Exception:  # noqa: BLE001 - a token that is not a JWT says nothing
        return {}


def _issued_by(document: _Document) -> tuple[str, str]:
    """Where this credential was issued and to which client, FROM the credential.

    No name of any source appears in this module, and that is the requirement, not
    a coincidence: the platform gives users primitives and does not carry
    per-source knowledge (``scripts/check_channel_agnostic.py`` measures it). The
    identity token the owner's sign-in stored already says both things -- ``iss``
    is the authorization server, ``aud``/``azp``/``client_id`` is the client it
    was issued to -- so the record describes its own source and the substrate
    learns nothing about any particular one.

    It also means this works for credentials already deposited, which a field
    added at deposit time would not.
    """
    claims = _claims(document.id_token)
    issuer = str(claims.get("iss") or "").strip()
    client = claims.get("client_id") or claims.get("azp") or claims.get("aud")
    if isinstance(client, list):
        client = client[0] if len(client) == 1 else ""
    client = str(client or "").strip()
    if not issuer or not client:
        return "", ""
    return issuer, client


def _source_endpoint(document: _Document, token_url: str, client_id: str) -> tuple[str, str]:
    """The token endpoint and client id to refresh against.

    An explicit pair from the caller wins (that is how a test names a fixture
    endpoint). Otherwise the issuer comes off the stored identity token and its
    token endpoint from that issuer's own RFC 8414 / OpenID metadata -- so the
    refresh is spent where the credential was issued and nowhere else, and a
    guessed URL is never constructed. A credential that does not say where it came
    from is not refreshed.
    """
    if token_url and client_id:
        return token_url, client_id
    issuer, client = _issued_by(document)
    if not issuer or not client:
        return "", ""
    from tinyassets.connection_oauth.discovery import fetch_server_metadata
    from tinyassets.connection_oauth.transport import OAuthError

    try:
        metadata = fetch_server_metadata(issuer)
    except (OAuthError, ValueError):
        return "", ""
    return metadata.token_endpoint, client


def adopt_newer_on_disk_document(
    *,
    universe_dir: str | Path,
    service: str,
    owner_user_id: str | None,
    universe_id: str,
    now: float | None = None,
) -> bool:
    """Take a materialized home's document into the vault when it is NEWER.

    ``ensure_codex_home_from_vault`` no longer overwrites an on-disk document with
    the vault's, which is right — but on its own it leaves a rotation the CLI made
    in a writable home living ONLY on disk, where a platform refresh reading the
    vault would spend the older refresh token beside it. This is the other half:
    newest wins, and the vault is where "newest" has to end up.

    Newer is decided by the documents' own ``last_refresh`` stamps, under the same
    lock as every other write. A document with no readable stamp is never
    preferred over one that has a stamp: that is a guess, and the refresh token is
    single-use. Returns True when the on-disk document was adopted.

    Never raises for an unreadable document: a launch must not fail because a file
    beside its credential could not be parsed.
    """
    from tinyassets.credential_vault import llm_subscription_credential_record

    universe = Path(universe_dir)
    key = service.strip().lower()
    stored = _stored(universe, key)
    if stored is None:
        return False
    auth_file = _materialized_document(universe, stored[0])
    if auth_file is None:
        return False
    try:
        candidate = _parse(base64.b64encode(auth_file.read_bytes()).decode("ascii"))
        current = _parse(stored[1])
    except (OSError, RefreshError):
        return False
    moment = time.time() if now is None else now
    if not _strictly_newer(candidate, current, moment):
        return False

    def read() -> _Document:
        latest = _stored(universe, key)
        if latest is None:
            raise RefreshError("the stored authorization is unreadable; reconnect")
        return _parse(latest[1])

    try:
        refresh_credential(
            universe_dir=universe,
            lock_id=f"llm_subscription::{key}",
            owner_user_id=owner_user_id,
            universe_id=universe_id,
            read=read,
            # Re-decided inside the locks against whatever is stored NOW: a holder
            # before us may already have written something newer still.
            stale=lambda latest: _strictly_newer(candidate, latest, moment),
            # No network: the source already issued this document.
            spend=lambda latest: candidate,
            records=lambda fresh: [
                llm_subscription_credential_record(
                    service=key,
                    auth_json_b64=fresh.encoded(),
                    last_refresh=fresh.last_refresh,
                )
            ],
            subject="sign-in",
        )
    except RefreshError:
        return False
    return True


#: The file name a stored sign-in document is materialized under. Named by the
#: FORMAT, not by any source: this module resolves it out of the record's own
#: values rather than knowing which key any particular source uses.
_DOCUMENT_FILENAME = "auth.json"


def _materialized_document(universe: Path, record: dict[str, Any]) -> Path | None:
    """The record's own on-disk document, if it has one inside this universe.

    Every value of the record is treated as a possible path instead of a fixed
    list of key names, for two reasons. The key differs per source
    (``<source>_home`` / ``home`` / ``auth_home`` / ``path`` /
    ``<source>_json_path``), and naming them here would put per-source knowledge
    in the substrate, which is the thing that is measured and refused.

    Containment is enforced exactly as the vault enforces it: the resolved path
    must be inside the universe, and neither it nor the file may be a link. A
    value that is not a path simply does not resolve to one.
    """
    try:
        root = universe.resolve(strict=True)
    except OSError:
        return None
    for value in record.values():
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            resolved = Path(value.strip())
            resolved = resolved if resolved.is_absolute() else root / resolved
            resolved = resolved.resolve(strict=False)
            if not resolved.is_relative_to(root):
                continue
            candidate = (
                resolved if resolved.name == _DOCUMENT_FILENAME
                else resolved / _DOCUMENT_FILENAME
            )
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if candidate.parent.is_symlink():
                continue
            return candidate
        except (OSError, ValueError):
            continue
    return None


def _strictly_newer(candidate: _Document, current: _Document, now: float) -> bool:
    """Whether ``candidate`` is a different document with a strictly newer stamp."""
    if candidate.refresh_token == current.refresh_token:
        return False
    theirs = _stamp_age(candidate.last_refresh, now)
    ours = _stamp_age(current.last_refresh, now)
    if theirs is None:
        return False  # unstamped: never preferred, however different it looks
    return ours is None or theirs < ours


def refresh_deposited_subscriptions(
    *,
    base_path: str | Path,
    universe_dir: str | Path,
    owner_user_id: str,
    universe_id: str,
    launching: str = "",
) -> None:
    """The launch-path seam: make every refreshable stored document current.

    Called BEFORE custody is resolved, outside any transaction (it makes a
    network call, and holds the vault while it does). Iterates the universe's
    subscription records rather than being told a provider: a record is
    refreshable when it stores an inline document this module can read, which is
    a property of the record, not of a vendor. A record that is not refreshable
    launches exactly as it does today.

    ``launching`` names the ONE service this launch is about to use, and is the
    only one whose finished sign-in may raise. Raising for any of them let a
    second, unrelated subscription's dead credential kill a launch that was never
    going to use it (Codex refute-review, P1 #2) -- the owner has more than one
    deposited source precisely so one of them being dead does not matter. A
    non-launching source is still refreshed (it will be somebody's launch soon,
    and a stale document costs a turn), just never at this launch's expense. An
    empty ``launching`` means the caller does not know yet, so nothing raises.

    A raise is :class:`~tinyassets.exceptions.ProviderAuthenticationError`, so the
    router marks the source for reconnect and the turn continues to the next model
    the owner allowed -- instead of the cooldown a ``ProviderUnavailableError``
    would buy, which stops the turn.

    A TRANSPORT failure is swallowed: the stored document may still work, and a
    launch must not be lost to a blip in a service that is not even the one the
    turn is talking to.
    """
    from tinyassets.credential_vault import load_credential_vault

    universe = Path(universe_dir)
    launched = launching.strip().lower()
    try:
        services = sorted({
            str(record.get("service") or "").strip().lower()
            for record in load_credential_vault(universe)
            if record.get("credential_type") == "llm_subscription"
            and isinstance(record.get("auth_json_b64"), str)
        })
    except ValueError:
        # A malformed vault is the launch path's own refusal to make, with its
        # own words; it is not this seam's business to pre-empt it.
        return
    for service in services:
        if not service:
            continue
        # Adopt first: a document the CLI already rotated in a writable home is
        # newer than the vault's, and refreshing the vault's copy would spend a
        # refresh token that document has already replaced.
        adopted = adopt_newer_on_disk_document(
            universe_dir=universe,
            service=service,
            owner_user_id=owner_user_id,
            universe_id=universe_id,
        )
        try:
            rotated = refresh_before_launch(
                universe_dir=universe,
                service=service,
                owner_user_id=owner_user_id,
                universe_id=universe_id,
            )
        except RefreshRejected as exc:
            if service != launched:
                # Another source's dead credential. Recorded for its own owner's
                # next turn by the launch that actually uses it; never this
                # launch's failure.
                logger.info("a deposited sign-in for another source needs renewing")
                continue
            from tinyassets.exceptions import ProviderAuthenticationError

            raise ProviderAuthenticationError(
                f"{service} needs you to sign in again: {exc.detail}"
            ) from None
        except RefreshError:
            rotated = False  # transient: launch with what is stored
        if rotated or adopted:
            renew_accepted_source(
                base_path=base_path,
                universe_dir=universe,
                service=service,
                owner_user_id=owner_user_id,
                universe_id=universe_id,
            )


def renew_accepted_source(
    *,
    base_path: str | Path,
    universe_dir: str | Path,
    service: str,
    owner_user_id: str,
    universe_id: str,
) -> dict[str, Any]:
    """Carry the accepted source's binding onto a rotated document.

    ``_subscription_record_digest`` covers the credential material, and that
    digest is pinned into the provider binding, so a refresh that only wrote the
    vault would leave serving refusing with "connect your provider before
    enabling serving". This is the landed renewal path, whose whole purpose is
    renewing an accepted source WITHOUT reading renewal as new model consent: a
    refresh is the same account and the same accepted model list with new bytes.

    Returns the serving module's own non-secret projection; never raises for an
    authority refusal, so a successful refresh is not reported as a failure.
    """
    from tinyassets.onboarding.serving import ensure_founder_serving

    return ensure_founder_serving(
        base_path=base_path,
        universe_dir=universe_dir,
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        service=service.strip().lower(),
    )
