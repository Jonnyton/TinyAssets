"""Frozen endpoint reader/serializer/writer from deployed cd28c3806c44ff63612adb8fcc709b622f89a6fd.

Only unchanged leaf validators and ledger connection setup are shared. Keep the
frozen policy parser/projection/write methods unchanged: they are the rollback
oracle, not production code. This does not claim old-network execution proof.
"""
import json
from dataclasses import dataclass
from typing import Any

from tinyassets.storage.outbound_connections import (
    _SSRF_HOSTNAME_RE,
    ConnectionLedger,
    SsrfValidationError,
    _required,
    _validate_endpoint_methods,
    _validate_param_patterns,
    _validate_path_template,
    _validate_query_rules,
    validate_git_scopes,
)


@dataclass(frozen=True)
class OutboundEndpoint:
    """One allowlisted egress target for an ``http`` connection (design.md D2/D3).

    ``host`` is an exact hostname (lower-cased), ``path_template`` a ``/``-rooted
    template, ``methods`` the HTTP verbs permitted. The allowlist is the REAL
    confidentiality/egress boundary — a caller-supplied URL that does not match
    one of these is refused before any socket is opened.

    A ``{param}`` segment does NOT match "any non-empty segment": every
    placeholder MUST carry a declared value pattern in ``param_patterns`` (name →
    anchored regex the whole segment must full-match), so a tenant/target/id in a
    path segment cannot silently address a different account (Codex FIX 3).
    ``allowed_query`` names the ONLY query parameters permitted — an undeclared
    query parameter is REFUSED, never dropped — and ``query_patterns`` optionally
    constrains a declared query value. ``required_query`` names query parameters
    that MUST be present EXACTLY ONCE (a subset of ``allowed_query``), so an
    endpoint whose semantics depend on a validated parameter (github's contents
    ``?ref=`` — Codex FIX: "require exactly one validated ref query") cannot be
    called without it or with a duplicate. ``param_patterns``/``query_patterns``
    are stored as sorted ``(name, regex)`` pairs so the dataclass stays hashable.
    """

    host: str
    path_template: str
    methods: tuple[str, ...]
    param_patterns: tuple[tuple[str, str], ...] = ()
    allowed_query: tuple[str, ...] = ()
    query_patterns: tuple[tuple[str, str], ...] = ()
    required_query: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "path_template": self.path_template,
            "methods": list(self.methods),
            "param_patterns": {name: pat for name, pat in self.param_patterns},
            "allowed_query": list(self.allowed_query),
            "query_patterns": {name: pat for name, pat in self.query_patterns},
            "required_query": list(self.required_query),
        }


def _validate_endpoint(raw: Any) -> OutboundEndpoint:
    """Coerce+validate one stored/authored allowlist endpoint, or fail closed."""
    if isinstance(raw, OutboundEndpoint):
        raw = raw.as_dict()
    if not isinstance(raw, dict):
        raise SsrfValidationError("endpoint must be an object")
    host = str(raw.get("host", "")).strip().lower()
    if not host or "%" in host or not _SSRF_HOSTNAME_RE.match(host):
        # Allowlist hosts are real DNS hostnames only — never IP literals, never
        # single-label names — matching the transport's own hostname policy.
        raise SsrfValidationError("endpoint host is not a permitted hostname")
    path_template = _validate_path_template(raw.get("path_template"))
    allowed_query, query_patterns, required_query = _validate_query_rules(
        raw.get("allowed_query"), raw.get("query_patterns"), raw.get("required_query")
    )
    return OutboundEndpoint(
        host=host,
        path_template=path_template,
        methods=_validate_endpoint_methods(raw.get("methods")),
        param_patterns=_validate_param_patterns(path_template, raw.get("param_patterns")),
        allowed_query=allowed_query,
        query_patterns=query_patterns,
        required_query=required_query,
    )


def _parse_allowed_endpoints(raw: Any) -> tuple[OutboundEndpoint, ...]:
    """Parse the allowlist from create input or stored JSON; each is validated."""
    if raw is None or raw == "":
        return ()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raise SsrfValidationError("stored endpoint allowlist is invalid") from None
    if isinstance(raw, (list, tuple)):
        return tuple(_validate_endpoint(item) for item in raw)
    raise SsrfValidationError("endpoint allowlist must be a list")


class LegacyConnectionLedger(ConnectionLedger):
    def extend_http_connection_endpoints(
        self,
        *,
        connection_id: str,
        endpoints: Any,
        scopes: tuple[str, ...],
        expected_endpoints_json: str,
        expected_scopes_json: str,
    ) -> bool:
        """ADD endpoints to an existing http connection. Never remove or replace.

        A credential is deposited once and extended as the work needs it — the
        alternative was a fresh connection (and a fresh paste) per endpoint,
        because a deterministic id plus any policy difference read as a hard
        conflict.

        Two things keep this from being a widening primitive:

        * **Additive only.** The caller has already checked the new set is a
          superset; this re-checks nothing about intent but writes the union, so
          an endpoint another graph depends on cannot vanish here. Narrowing and
          removal stay unsupported (they are a different, destructive intent).
        * **CAS-guarded on BOTH columns it writes, always.** The UPDATE matches
          on the exact endpoint JSON AND the exact scopes JSON the caller read
          (both from one :meth:`policy_json` snapshot). Guarding endpoints alone
          let two scope-only widenings race: the first wrote scope B without
          touching the endpoints, so the second's CAS still matched and
          replaced B with A; an optional scopes guard let a caller skip it
          (Codex rounds 1-2 on the 2026-09-02 rail change).

        Returns True when the row was updated.
        """
        parsed = _parse_allowed_endpoints(endpoints)
        if not parsed:
            raise SsrfValidationError(
                "an http connection requires at least one allowed endpoint"
            )
        new_scopes = tuple(_required("scope", scope) for scope in scopes)
        validate_git_scopes(new_scopes, hosts=[endpoint.host for endpoint in parsed])
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbound_connections
                SET allowed_endpoints_json = ?, scopes_json = ?
                WHERE connection_id = ? AND allowed_endpoints_json = ?
                  AND scopes_json = ?
                """,
                (
                    json.dumps([ep.as_dict() for ep in parsed]),
                    json.dumps(list(new_scopes)),
                    connection_id,
                    expected_endpoints_json,
                    expected_scopes_json,
                ),
            )
            return cursor.rowcount > 0
