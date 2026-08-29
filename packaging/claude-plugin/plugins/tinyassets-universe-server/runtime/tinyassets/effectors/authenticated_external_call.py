"""The ONE generic outbound channel primitive (Pipedream model).

The PLATFORM knows NOTHING about any specific channel. There is no per-service
code here — no hard-coded hostname, no per-channel auth-header assembly, no
per-service branch. A universe adds ANY outbound integration — even an API this
platform has never heard of — with ZERO platform changes, by:

  1. Creating an ``http`` outbound connection (the Pipedream "connected
     account"): a vault ``credential_ref`` + an ``auth_scheme``
     (bearer/basic/header/oauth1a/none) + a per-endpoint egress allowlist
     (host + path_template + methods, including the ``{name+}`` multi-segment
     tail). See ``storage/outbound_connections.ConnectionLedger``.
  2. Granting that connection to the universe (``grant_effector_consent`` /
     ``grant_connection``).
  3. Emitting an ``authenticated_external_call`` packet from a node that
     DESCRIBES the actual API request.

The packet is fully user-specified; the platform validates SHAPE, not channel:

    {
      "sink": "authenticated_external_call",
      "connection_id": "<the http connection to use>",
      "grant_id":      "<the grant binding that connection to THIS universe>",
      "verb":          "<the connection scope string — for http, the HTTP method>",
      "request": {
        "method":  "POST",           # optional; must equal ``verb`` if present
        "host":    "api.example.com", # optional; falls back to the connection's
                                      #   single allowlisted host
        "path":    "/v1/messages",    # request path (matched by the allowlist)
        "query":   {"k": "v"},        # optional; validated by the allowlist
        "headers": {"X-Extra": "1"},  # optional NON-auth headers
        "header_name": "X-Api-Key",   # optional; only for the "header" auth scheme
        "body":    {...} | "..."      # optional; dict/list json-encoded by worker
      }
    }

BODY TRANSFORMS. Besides shape, this effector knows exactly two more things:
one encoding, and the run it belongs to. Anywhere in ``request.body`` a
one-key object whose key is one of the five names below is applied before the
request leaves - so a node writes TEXT and references BYTES, and never
hand-produces base64 or re-types a file (live 2026-08-29: model-generated
base64 came back ``422 not valid Base64``, then as valid base64 of a
transcribed file that lost 87 lines, then a "repair" that re-typed the file
with 36 differences). The names are namespaced so a user's own API payload
that happens to use ``$ref`` (JSON Schema) or ``$set`` is never hijacked:

    {"$ta.base64": X}         the base64 of X's UTF-8 bytes
    {"$ta.from_base64": X}    the UTF-8 text of base64 X (whitespace-tolerant)
    {"$ta.ref": "key.a.0.b"}  a value from the run's state - the root ``key``
                              MUST be one of the emitting node's declared
                              ``input_keys`` (or a state_schema-defaulted key,
                              or the node's own output key); JSON-encoded
                              strings are traversed, lists by index
    {"$ta.effect": "node.response.body.x"}
                              a value from the evidence of an EARLIER node's
                              effect in the SAME run (effects fire in node
                              order); ``response.body`` is the sanitized text
                              the worker returned, traversed as JSON
    {"$ta.concat": [X, ...]}  the texts joined

X may itself be a transform (nesting is bounded at 32). So "append one line
to a fetched file" is a two-node branch: ``fetch`` emits a GET packet;
``write`` emits

    {"sha":     {"$ta.effect": "fetch.response.body.sha"},
     "content": {"$ta.base64": {"$ta.concat": [
                    {"$ta.from_base64": {"$ta.effect": "fetch.response.body.content"}},
                    "the new line\n"]}}}

and the model authored only the line - in ONE run, so the fetched bytes never
pass through a model or a second ``run_graph``. Refusals are whole: a wrong
type, an unresolvable or unfenced path, bytes that are not text, or a
transformed body over ``_MAX_TRANSFORMED_BODY_BYTES`` return the secret-free
``invalid_body_transform`` error and nothing is sent. A body with no transform
is sent byte-for-byte as before (including any ``$``-keyed objects of its own).

CREDENTIAL-BLINDNESS. This effector NEVER resolves or sees the credential. It
resolves an exact scoped proxy under the universe's own authority and hands the
wire request to ``proxy.request(verb, request)``. The credential is applied
INSIDE the spawned broker worker (``_run_proxy_worker`` +
``_SsrfHardenedHttpDriver``); the secret never exists in this process. The
effector returns the worker's sanitized ``{status, reason, headers, body}`` as
evidence, or a secret-free error dict — it NEVER raises to the run-completion
path.

ISOLATION. ``universe_id`` is derived from server-owned run context
(``base_path``), never the packet. A packet may only name a grant that is bound
to the universe RUNNING the graph: the effector refuses any grant whose
``universe_id`` does not match, so a copied/remixed graph cannot borrow another
universe's connections. The authenticated principal is the grant's OWN stored
owner — read from the trusted grant row, gated by that universe match — never a
payload-supplied identity.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import urllib.parse
from pathlib import Path
from typing import Any

from tinyassets.effectors.authority import DENIED as SOUL_AUTHORITY_DENIED
from tinyassets.effectors.authority import resolve_soul_effect_authority

logger = logging.getLogger(__name__)

#: The one generic sink. A node that declares ``effects=[…this…]`` and emits a
#: matching packet routes here regardless of which external service it targets.
EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL = "authenticated_external_call"


# --------------------------------------------------------------------------- #
# Packet reading (shape only — no channel knowledge)
# --------------------------------------------------------------------------- #
def _parse_packet(value: Any) -> dict[str, Any] | None:
    """Return the packet dict iff ``value`` is a matching packet, else None."""
    if isinstance(value, dict):
        packet = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            packet = json.loads(stripped)
        except (TypeError, ValueError):
            return None
        if not isinstance(packet, dict):
            return None
    else:
        return None
    if packet.get("sink") != EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL:
        return None
    return packet


def _find_packet(
    *,
    output_keys: list[str],
    run_state: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    for key in output_keys or []:
        if not isinstance(key, str) or key not in run_state:
            continue
        packet = _parse_packet(run_state.get(key))
        if packet is not None:
            return key, packet
    return None, None


def _str_field(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    return value.strip() if isinstance(value, str) else ""


# --------------------------------------------------------------------------- #
# Body transforms - one encoding and the run's own data, applied before the wire
# --------------------------------------------------------------------------- #
_OP_BASE64 = "$ta.base64"
_OP_FROM_BASE64 = "$ta.from_base64"
_OP_REF = "$ta.ref"
_OP_EFFECT = "$ta.effect"
_OP_CONCAT = "$ta.concat"
_TRANSFORM_OPS = (_OP_BASE64, _OP_FROM_BASE64, _OP_REF, _OP_EFFECT, _OP_CONCAT)
_MAX_TRANSFORM_DEPTH = 32
#: A transformed body is serialized in-process before the worker frames it
#: (the frame itself is bounded at 16 MiB downstream); bound it here so a
#: reference to a large blob fails predictably instead of allocating first.
_MAX_TRANSFORMED_BODY_BYTES = 8 * 1024 * 1024


class _TransformError(ValueError):
    """A malformed transform. The message names paths and types, never values."""


def _is_transform(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and len(value) == 1
        and next(iter(value)) in _TRANSFORM_OPS
    )


def _walk(path: str, root: Any, *, label: str) -> Any:
    """Descend a dotted path; JSON-encoded strings are traversed, lists by index."""
    node: Any = root
    walked: list[str] = []
    for part in path.split("."):
        here = ".".join(walked) or "<root>"
        if isinstance(node, str):
            stripped = node.strip()
            if stripped[:1] not in ("{", "["):
                raise _TransformError(f"{label} {path!r}: value at {here} is text, not JSON")
            try:
                node = json.loads(stripped)
            except ValueError as exc:
                raise _TransformError(f"{label} {path!r}: value at {here} is not JSON") from exc
        if isinstance(node, dict):
            if part not in node:
                raise _TransformError(f"{label} {path!r}: no key {part!r} at {here}")
            node = node[part]
        elif isinstance(node, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise _TransformError(
                    f"{label} {path!r}: {part!r} is not a list index at {here}"
                ) from exc
            if not -len(node) <= index < len(node):
                raise _TransformError(f"{label} {path!r}: index {index} out of range at {here}")
            node = node[index]
        else:
            raise _TransformError(
                f"{label} {path!r}: cannot descend into {type(node).__name__} at {here}"
            )
        walked.append(part)
    return node


def _split_root(path: Any, label: str) -> tuple[str, str]:
    if not isinstance(path, str) or not path.strip():
        raise _TransformError(f"{label} must be a non-empty dotted path")
    root, _, rest = path.partition(".")
    return root, rest


class _TransformContext:
    """What a packet may read: its node's fenced state view and earlier effects."""

    __slots__ = ("run_state", "allowed_state_keys", "prior_effects")

    def __init__(self, run_state, allowed_state_keys, prior_effects):
        self.run_state = run_state or {}
        self.allowed_state_keys = None if allowed_state_keys is None else set(allowed_state_keys)
        self.prior_effects = prior_effects or {}

    def ref(self, path: Any) -> Any:
        root, rest = _split_root(path, _OP_REF)
        if self.allowed_state_keys is None:
            raise _TransformError(
                f"{_OP_REF} {path!r}: this node declares no readable state keys"
            )
        if root not in self.allowed_state_keys:
            raise _TransformError(
                f"{_OP_REF} {path!r}: {root!r} is not among the node's declared "
                "input_keys (or schema-defaulted keys)"
            )
        if root not in self.run_state:
            raise _TransformError(f"{_OP_REF} {path!r}: {root!r} is not in the run's state")
        value = self.run_state[root]
        return _walk(rest, value, label=_OP_REF) if rest else value

    def effect(self, path: Any) -> Any:
        root, rest = _split_root(path, _OP_EFFECT)
        if root not in self.prior_effects:
            raise _TransformError(
                f"{_OP_EFFECT} {path!r}: no earlier node {root!r} with an "
                f"{EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL} effect in this run"
            )
        value = self.prior_effects[root]
        return _walk(rest, value, label=_OP_EFFECT) if rest else value


def _as_text(value: Any, what: str) -> str:
    if isinstance(value, str):
        return value
    raise _TransformError(f"{what} must resolve to text, got {type(value).__name__}")


def _apply_transforms(value: Any, ctx: _TransformContext, depth: int = 0) -> Any:
    if depth > _MAX_TRANSFORM_DEPTH:
        raise _TransformError(f"body transforms nested deeper than {_MAX_TRANSFORM_DEPTH}")
    if _is_transform(value):
        op, arg = next(iter(value.items()))
        if op == _OP_REF:
            return ctx.ref(arg)
        if op == _OP_EFFECT:
            return ctx.effect(arg)
        if op == _OP_CONCAT:
            if not isinstance(arg, list):
                raise _TransformError(f"{_OP_CONCAT} takes a list")
            return "".join(
                _as_text(_apply_transforms(part, ctx, depth + 1), f"{_OP_CONCAT} part")
                for part in arg
            )
        if op == _OP_FROM_BASE64:
            text = _as_text(_apply_transforms(arg, ctx, depth + 1), _OP_FROM_BASE64)
            try:
                raw = base64.b64decode("".join(text.split()), validate=True)
            except (binascii.Error, ValueError) as exc:
                raise _TransformError(f"{_OP_FROM_BASE64}: not valid base64") from exc
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise _TransformError(f"{_OP_FROM_BASE64}: bytes are not UTF-8 text") from exc
        text = _as_text(_apply_transforms(arg, ctx, depth + 1), _OP_BASE64)
        return base64.b64encode(text.encode("utf-8")).decode("ascii")
    if isinstance(value, dict):
        return {key: _apply_transforms(item, ctx, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_apply_transforms(item, ctx, depth + 1) for item in value]
    return value


def _has_transform(value: Any) -> bool:
    if _is_transform(value):
        return True
    if isinstance(value, dict):
        return any(_has_transform(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_transform(v) for v in value)
    return False


def apply_body_transforms(
    body: Any,
    run_state: dict[str, Any] | None = None,
    *,
    allowed_state_keys: list[str] | set[str] | None = None,
    prior_effects: dict[str, Any] | None = None,
) -> tuple[Any, str | None]:
    """Return ``(body, None)`` with every transform applied, or ``(None, why)``.

    A body without transforms is returned as the SAME object, untouched.
    ``allowed_state_keys`` fences ``$ta.ref`` (``None`` = nothing readable);
    ``prior_effects`` maps earlier node ids to their effect evidence.
    """
    if not _has_transform(body):
        return body, None
    ctx = _TransformContext(run_state, allowed_state_keys, prior_effects)
    try:
        transformed = _apply_transforms(body, ctx)
        serialized = transformed if isinstance(transformed, str) else json.dumps(transformed)
        size = len(serialized.encode("utf-8"))
        if size > _MAX_TRANSFORMED_BODY_BYTES:
            raise _TransformError(
                f"transformed body is {size} bytes; the bound is "
                f"{_MAX_TRANSFORMED_BODY_BYTES}"
            )
        return transformed, None
    except _TransformError as exc:
        return None, str(exc)


# --------------------------------------------------------------------------- #
# Run-context resolution (server-owned; never from the packet)
# --------------------------------------------------------------------------- #
def _universe_id(base_path: str | Path | None) -> str:
    """The universe whose authority this run binds to — from ``base_path`` only.

    ``runs.py`` passes the universe DIR as ``base_path`` (``data_root/<uid>``), so
    the trailing component IS the universe id. Never taken from the packet.
    """
    if base_path is None:
        return ""
    try:
        return Path(base_path).name.strip()
    except (TypeError, ValueError):
        return ""


def _ledger_db_path(base_path: str | Path | None) -> Path | None:
    """The outbound ledger DB lives at the DATA ROOT (``base_path.parent``)."""
    if base_path is None:
        return None
    try:
        return Path(base_path).parent / "outbound.db"
    except (TypeError, ValueError):
        return None


def _check_consent(universe_dir: Path, destination: str) -> bool:
    """Whether an active effector-consent grant exists for this destination.

    A connection grant proves the universe MAY use the connection; a live
    external effect additionally requires the owner's explicit effector consent
    for the destination. Fail closed (return False) on empty destination or any
    lookup failure — a live call must never proceed on a crashed consent check.
    """
    if not destination:
        return False
    try:
        from tinyassets.storage.effector_consents import is_consent_active

        return is_consent_active(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
            destination=destination,
        )
    except Exception:
        logger.exception("authenticated_external_call consent lookup crashed")
        return False


# --------------------------------------------------------------------------- #
# Wire-request assembly (generic; the allowlist in the worker is the boundary)
# --------------------------------------------------------------------------- #
def _resolve_host(request: dict[str, Any], connection_view: Any) -> tuple[str, str]:
    """Return ``(host, error_kind)``; ``error_kind`` empty on success.

    Host precedence: an explicit ``request.host`` (the user fully specifies the
    call), else the connection's single allowlisted host. A connection spanning
    multiple hosts with no explicit ``host`` is ambiguous and refused — the user
    must say which. The worker's allowlist re-validates whatever host is used.
    """
    explicit = _str_field(request, "host")
    if explicit:
        return explicit, ""
    hosts = {
        ep.host
        for ep in getattr(connection_view, "allowed_endpoints", ()) or ()
        if getattr(ep, "host", "")
    }
    if len(hosts) == 1:
        return next(iter(hosts)), ""
    if not hosts:
        return "", "no_allowlisted_host"
    return "", "host_ambiguous"


def _build_url(request: dict[str, Any], host: str) -> tuple[str, str]:
    """Return ``(url, error_kind)``. Accepts an absolute ``url`` or ``host``+``path``.

    Query params come from a ``query`` mapping (never smuggled inside ``path`` when
    a ``query`` is also supplied). The URL is built here but the real egress
    boundary is the per-connection allowlist enforced inside the worker.
    """
    absolute = _str_field(request, "url")
    if absolute:
        return absolute, ""
    path = request.get("path")
    if not isinstance(path, str) or not path:
        return "", "missing_path"
    if not path.startswith("/"):
        return "", "invalid_path"
    query = request.get("query")
    query_string = ""
    if query is not None:
        if not isinstance(query, dict):
            return "", "invalid_query"
        if "?" in path:
            return "", "query_in_path_conflict"
        query_string = urllib.parse.urlencode(
            {str(k): str(v) for k, v in query.items()}
        )
    url = f"https://{host}{path}"
    if query_string:
        url = f"{url}?{query_string}"
    return url, ""


# --------------------------------------------------------------------------- #
# Proxy seam — the ONLY place the ledger is touched. Kept small + named so the
# credential-blind spawned-worker path is the default and tests can substitute
# an in-process loopback broker for wire-request assertions (the child re-imports
# with production SSRF seams, so a monkeypatch cannot cross the spawn boundary —
# exactly why the project splits "credential-blindness through the real worker"
# from "successful wire-request assertion via an injected driver").
# --------------------------------------------------------------------------- #
def _read_connection_context(
    *, db_path: Path, grant_id: str, connection_id: str, universe_id: str
) -> tuple[Any, Any, str]:
    """Return ``(grant, connection_view, error_kind)`` — plain reads, no principal.

    Enforces the isolation gate: the grant must exist, be active, and be bound to
    the RUNNING universe. ``error_kind`` empty on success.
    """
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(db_path)
    grant = ledger.get_grant(grant_id)
    if grant is None:
        return None, None, "unknown_grant"
    if getattr(grant, "revoked_at", None) is not None:
        return None, None, "revoked_grant"
    if getattr(grant, "universe_id", "") != universe_id:
        # The isolation boundary: a packet cannot select a grant from a
        # different universe than the one running this graph.
        return None, None, "grant_not_for_universe"
    if getattr(grant, "connection_id", "") != connection_id:
        return None, None, "grant_connection_mismatch"
    view = ledger.get_connection_view(connection_id)
    if view is None:
        return None, None, "unknown_connection"
    return grant, view, ""


def _open_connection_proxy(
    *,
    db_path: Path,
    universe_id: str,
    grant_id: str,
    connection_id: str,
    owner_user_id: str,
) -> Any:
    """Resolve the exact scoped, credential-blind proxy under universe authority.

    The authenticated principal is the grant's OWN stored owner (trusted grant
    row), gated upstream by the universe match. ``resolve_exact_scoped_proxy``
    spawns the broker worker; the credential is resolved and applied inside it.
    """
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(
        db_path,
        verify_authenticated_principal=lambda: owner_user_id,
    )
    return ledger.resolve_exact_scoped_proxy(
        universe_id=universe_id,
        grant_id=grant_id,
        connection_id=connection_id,
    )


# --------------------------------------------------------------------------- #
# The effector
# --------------------------------------------------------------------------- #
def run_authenticated_external_call_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
    dry_run: bool | None = None,
    allowed_state_keys: list[str] | set[str] | None = None,
    prior_effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch one ``authenticated_external_call`` packet. NEVER raises.

    Every refusal or failure is returned as a secret-free evidence dict with an
    ``error_kind``. Success returns the worker's sanitized response plus a small
    amount of non-secret metadata.
    """
    del dry_run  # gate orchestration owns the dry-run decision; kept for compat
    try:
        return _run(
            node_id=node_id,
            output_keys=output_keys,
            run_state=run_state,
            base_path=base_path,
            run_id=run_id,
            allowed_state_keys=allowed_state_keys,
            prior_effects=prior_effects,
        )
    except Exception as exc:  # defensive — never raise from the completion path
        logger.exception(
            "authenticated_external_call effector crashed for node %s", node_id
        )
        return {
            "error": f"effector crashed: {exc}",
            "error_kind": "effector_crashed",
        }


def _run(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None,
    run_id: str,
    allowed_state_keys: list[str] | set[str] | None = None,
    prior_effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matched_key, packet = _find_packet(output_keys=output_keys, run_state=run_state)
    if packet is None:
        return {
            "error": (
                f"node '{node_id}' declared effects=["
                f"{EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL}] but no output_key held "
                "a parseable authenticated_external_call packet"
            ),
            "error_kind": "no_matching_packet",
        }

    connection_id = _str_field(packet, "connection_id")
    grant_id = _str_field(packet, "grant_id")
    if not connection_id:
        return {"error": "packet.connection_id is required", "error_kind": "invalid_packet"}
    if not grant_id:
        return {"error": "packet.grant_id is required", "error_kind": "invalid_packet"}

    request = packet.get("request")
    if not isinstance(request, dict):
        return {"error": "packet.request must be a mapping", "error_kind": "invalid_packet"}

    # verb = the connection scope. For http connections this IS the HTTP method
    # (the worker uses it as the method). Accept either the top-level verb or
    # request.method; if both are present they must agree.
    verb = _str_field(packet, "verb")
    request_method = _str_field(request, "method")
    if not verb:
        verb = request_method
    if not verb:
        return {"error": "packet.verb is required", "error_kind": "invalid_packet"}
    if request_method and request_method.upper() != verb.upper():
        return {
            "error": "request.method does not match verb",
            "error_kind": "method_mismatch",
            "verb": verb,
            "requested_method": request_method,
        }

    universe_id = _universe_id(base_path)
    db_path = _ledger_db_path(base_path)
    if not universe_id or db_path is None:
        # No trusted universe context ⇒ fail closed (never borrow a default).
        return {
            "error": "no universe authority is bound to this run",
            "error_kind": "no_universe_authority",
            "matched_output_key": matched_key,
        }

    grant, view, gate_error = _read_connection_context(
        db_path=db_path,
        grant_id=grant_id,
        connection_id=connection_id,
        universe_id=universe_id,
    )
    if gate_error:
        return {
            "error": f"connection authority refused: {gate_error}",
            "error_kind": gate_error,
            "matched_output_key": matched_key,
            "connection_id": connection_id,
            "grant_id": grant_id,
            "universe_id": universe_id,
        }

    # Authorization gates — parity with every prior per-channel effector. The
    # connection grant above proves the universe MAY use this connection, but a
    # LIVE external effect additionally requires: (1) the running universe's soul
    # to not DENY the (sink, destination), and (2) an active effector-consent
    # grant for the destination. A connection grant ALONE is not sufficient to
    # fire an effect — fail closed on either gate. The destination is the
    # connection's own configured destination (a stable, server-owned value,
    # never taken from the packet).
    universe_dir = Path(base_path)
    destination = str(getattr(view, "destination", "") or "").strip()
    authority = resolve_soul_effect_authority(
        universe_dir,
        EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        destination,
    )
    if authority == SOUL_AUTHORITY_DENIED:
        return {
            "dry_run": True,
            "reason": "soul_authority_denied",
            "error_kind": "soul_authority_denied",
            "destination": destination,
            "connection_id": connection_id,
            "matched_output_key": matched_key,
        }
    if not _check_consent(universe_dir, destination):
        return {
            "dry_run": True,
            "reason": "missing_consent",
            "error_kind": "missing_consent",
            "destination": destination,
            "connection_id": connection_id,
            "matched_output_key": matched_key,
            "hint": (
                "A live authenticated_external_call requires an active effector-"
                "consent grant for this connection's destination; grant it through "
                "the internal consent surface before the effect can fire."
            ),
        }

    host, host_error = _resolve_host(request, view)
    if host_error:
        return {
            "error": f"could not resolve request host: {host_error}",
            "error_kind": host_error,
            "matched_output_key": matched_key,
            "connection_id": connection_id,
        }

    url, url_error = _build_url(request, host)
    if url_error:
        return {
            "error": f"could not build request url: {url_error}",
            "error_kind": url_error,
            "matched_output_key": matched_key,
            "connection_id": connection_id,
        }

    wire_request: dict[str, Any] = {"url": url}
    headers = request.get("headers")
    if headers is not None:
        wire_request["headers"] = headers
    if "body" in request:
        body, transform_error = apply_body_transforms(
            request.get("body"), run_state,
            allowed_state_keys=allowed_state_keys, prior_effects=prior_effects,
        )
        if transform_error:
            # Refused whole: a half-transformed body must never reach the wire.
            return {
                "error": f"body transform refused: {transform_error}",
                "error_kind": "invalid_body_transform",
                "matched_output_key": matched_key,
                "connection_id": connection_id,
            }
        wire_request["body"] = body
    header_name = _str_field(request, "header_name")
    if header_name:
        wire_request["header_name"] = header_name

    proxy = None
    try:
        proxy = _open_connection_proxy(
            db_path=db_path,
            universe_id=universe_id,
            grant_id=grant_id,
            connection_id=connection_id,
            owner_user_id=getattr(grant, "owner_user_id", ""),
        )
        response = proxy.request(verb, wire_request)
    except Exception as exc:
        # Secret-free by construction: the proxy/broker raise only sanitized,
        # credential-free errors across the governed boundary.
        return {
            "error": f"outbound request failed: {type(exc).__name__}",
            "error_kind": "outbound_request_failed",
            "detail": str(exc),
            "matched_output_key": matched_key,
            "connection_id": connection_id,
            "grant_id": grant_id,
            "verb": verb,
            "url": url,
        }
    finally:
        if proxy is not None:
            try:
                proxy.close()
            except Exception:  # pragma: no cover — best-effort teardown
                logger.debug("proxy close failed for node %s", node_id, exc_info=True)

    return {
        "delivered": True,
        "response": response,
        "matched_output_key": matched_key,
        "connection_id": connection_id,
        "grant_id": grant_id,
        "verb": verb,
        "url": url,
    }


__all__ = [
    "EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL",
    "apply_body_transforms",
    "run_authenticated_external_call_effector",
]
