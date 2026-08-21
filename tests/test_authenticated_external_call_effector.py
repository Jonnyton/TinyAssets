"""The ONE generic channel primitive — proof the shape is right.

A universe wires ANY external service by creating an ``http`` connection + a
grant + a node that emits an ``authenticated_external_call`` packet. The
platform holds ZERO per-channel code: a brand-new API works identically with no
platform change. These tests prove:

  * a generic call succeeds with the EXACT wire request the packet described;
  * the credential is applied INSIDE the broker worker (resolved from the vault),
    never carried by the packet or the effector — credential-blindness;
  * an out-of-allowlist path is refused before any socket opens;
  * a SECOND, arbitrary service (different host + a different auth scheme) works
    with NO new module code — plug-and-play;
  * a grant bound to another universe is refused (isolation);
  * the module names NO channel.

Test seams mirror the project's own split (``test_outbound_connection_ledger``):
the credential-blind SPAWNED-worker path is exercised for real to prove the
credential is resolved by the worker, while the successful loopback WIRE-REQUEST
assertions run the REAL broker dispatch + REAL general vault resolver + REAL
SSRF driver in-process with an injected loopback socket — because the spawned
child re-imports with production SSRF seams (https-only, global-address-only,
TLS-verified), a monkeypatch cannot cross the spawn boundary, so a loopback can
never be reached through it. The two together cover the whole contract.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socket
import ssl
import threading
from pathlib import Path

from tinyassets.credential_vault import write_credential_vault
from tinyassets.effectors import authenticated_external_call as aec
from tinyassets.effectors.authenticated_external_call import (
    EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
    run_authenticated_external_call_effector,
)
from tinyassets.storage import outbound_connections as _oc
from tinyassets.storage.outbound_connections import (
    ConnectionLedger,
    _build_credential_broker_dispatch,
    _SsrfHardenedHttpDriver,
)

_HTTP_FLAG = "TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED"


# --------------------------------------------------------------------------- #
# Scaffolding
# --------------------------------------------------------------------------- #
def _setup(
    tmp_path,
    *,
    universe_id="universe-1",
    provider="http",
    destination="api.example.com",
    auth_scheme="bearer",
    token="real-vault-http-token",
    vault_name="conn-secret",
    endpoints=None,
    scopes=("POST",),
    grant_universe=None,
    grant_consent_for=True,
):
    """REAL vault http record + http connection + per-universe grant."""
    data_root = tmp_path
    universe_dir = data_root / universe_id
    write_credential_vault(
        universe_dir,
        [{"credential_type": "http", "destination": vault_name, "token": token}],
    )
    db_path = data_root / "outbound.db"
    ledger = ConnectionLedger(
        db_path, verify_authenticated_principal=lambda: "user-1"
    )
    ledger.create_connection(
        connection_id="conn-http",
        owner_user_id="user-1",
        connection_class="outbound-http",
        scopes=scopes,
        provider=provider,
        destination=destination,
        credential_ref=f"vault://http/{vault_name}",
        connection_type="http",
        auth_scheme=auth_scheme,
        allowed_endpoints=endpoints
        or [{"host": destination, "path_template": "/v1/messages", "methods": ["POST"]}],
    )
    ledger.grant_connection(
        grant_id="grant-http",
        connection_id="conn-http",
        owner_user_id="user-1",
        universe_id=grant_universe or universe_id,
    )
    if grant_consent_for:
        # A connection grant alone is NOT sufficient to fire an effect; a live
        # authenticated_external_call also requires an active effector-consent
        # grant for the destination (soul authority is UNDECLARED here, which
        # passes the soul gate). Negative tests pass grant_consent_for=False.
        from tinyassets.storage.effector_consents import grant_consent

        grant_consent(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
            destination=destination,
            granted_by="test",
        )
    return data_root, universe_dir, db_path


class _Loopback:
    """A recording loopback HTTP endpoint the injected driver connects to."""

    def __init__(self):
        self.recorded: list[dict] = []
        recorded = self.recorded

        class _Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_a):  # noqa: ANN001, ANN002
                return

            def _handle(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length) if length else b""
                recorded.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": {k: v for k, v in self.headers.items()},
                        "body": body,
                    }
                )
                payload = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = _handle  # noqa: N815
            do_POST = _handle  # noqa: N815

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def _install_loopback_driver(monkeypatch, port):
    """Point the (module-global) SSRF driver at the loopback socket."""

    class _PassThroughTLS:
        def __init__(self):
            self.verify_mode = ssl.CERT_NONE
            self.check_hostname = False

        def wrap_socket(self, sock, server_hostname=None):  # noqa: ANN001
            return sock

    def open_socket(_address, timeout, _src):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    def factory(*_a, **_k):
        return _SsrfHardenedHttpDriver(
            resolver=lambda _h, _p: ["127.0.0.1"],
            validator=lambda addr: addr,
            open_socket=open_socket,
            ssl_context=_PassThroughTLS(),
            allowed_ports=frozenset({443}),
        )

    monkeypatch.setattr(_oc, "_SsrfHardenedHttpDriver", factory)


def _install_inprocess_proxy(
    monkeypatch, *, db_path, universe_dir, grant_id, provider, destination, runtime_root
):
    """Substitute the effector's proxy seam with an in-process REAL broker.

    Builds the exact production dispatch (``_build_credential_broker_dispatch``)
    the spawned worker runs — REAL general vault resolver + REAL SSRF driver
    (loopback socket injected via :func:`_install_loopback_driver`, which MUST be
    installed first). Only the process spawn is elided so the loopback is
    reachable and the exact wire request can be asserted.
    """
    config = {
        "allow_test_fixtures": False,
        "allow_http_connections": True,
        "ledger_db_path": str(Path(db_path).resolve()),
        "universe_dir": str(Path(universe_dir).resolve()),
        "provider": provider,
        "destination": destination,
        "connection_type": "http",
        "owner_user_id": "user-1",
        "runtime_root": str(Path(runtime_root).resolve()),
    }
    dispatch = _build_credential_broker_dispatch(config)

    class _InProcessProxy:
        def __init__(self):
            self.closed = False

        def request(self, verb, request):
            return dispatch(grant_id, verb, request)

        def close(self):
            self.closed = True

    proxy = _InProcessProxy()
    monkeypatch.setattr(aec, "_open_connection_proxy", lambda **_k: proxy)
    return proxy


def _read_audit(data_root, grant_id):
    runtime_id = hashlib.sha256(grant_id.encode("utf-8")).hexdigest()
    path = Path(data_root) / ".outbound-proxy" / runtime_id / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------- #
# (a) + (b) success with exact wire request + worker-applied credential
# --------------------------------------------------------------------------- #
def test_generic_call_succeeds_with_exact_wire_request_and_worker_applied_credential(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(_HTTP_FLAG, "1")
    data_root, universe_dir, db_path = _setup(tmp_path)
    loop = _Loopback()
    _install_loopback_driver(monkeypatch, loop.port)
    proxy = _install_inprocess_proxy(
        monkeypatch,
        db_path=db_path,
        universe_dir=universe_dir,
        grant_id="grant-http",
        provider="http",
        destination="api.example.com",
        runtime_root=tmp_path / "rt1",
    )

    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {
            "method": "POST",
            "path": "/v1/messages",
            "body": {"text": "hello world"},
        },
    }
    run_state = {"out": json.dumps(packet)}
    try:
        evidence = run_authenticated_external_call_effector(
            node_id="n1",
            output_keys=["out"],
            run_state=run_state,
            base_path=str(universe_dir),
            run_id="r1",
        )
    finally:
        loop.stop()

    assert evidence["delivered"] is True
    assert evidence["response"]["status"] == 200
    assert evidence["url"] == "https://api.example.com/v1/messages"

    # (a) the EXACT wire request the packet described reached the destination.
    assert len(loop.recorded) == 1
    rec = loop.recorded[0]
    assert rec["method"] == "POST"
    assert rec["path"] == "/v1/messages"
    assert json.loads(rec["body"]) == {"text": "hello world"}

    # (b) the credential was applied BY THE WORKER, resolved from the vault —
    # the packet and the effector evidence never carried it.
    assert rec["headers"]["Authorization"] == "Bearer real-vault-http-token"
    assert "real-vault-http-token" not in json.dumps(packet)
    assert "real-vault-http-token" not in json.dumps(evidence)
    assert proxy.closed is True  # the effector always tears the proxy down


# --------------------------------------------------------------------------- #
# (c) out-of-allowlist path is refused BEFORE any socket
# --------------------------------------------------------------------------- #
def test_out_of_allowlist_path_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(_HTTP_FLAG, "1")
    data_root, universe_dir, db_path = _setup(tmp_path)  # allowlist: only /v1/messages
    loop = _Loopback()
    _install_loopback_driver(monkeypatch, loop.port)
    _install_inprocess_proxy(
        monkeypatch,
        db_path=db_path,
        universe_dir=universe_dir,
        grant_id="grant-http",
        provider="http",
        destination="api.example.com",
        runtime_root=tmp_path / "rt3",
    )

    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {"path": "/v1/secret-exfil", "body": {"x": 1}},
    }
    run_state = {"out": json.dumps(packet)}
    try:
        evidence = run_authenticated_external_call_effector(
            node_id="n",
            output_keys=["out"],
            run_state=run_state,
            base_path=str(universe_dir),
        )
    finally:
        loop.stop()

    assert evidence.get("delivered") is not True
    assert evidence["error_kind"] == "outbound_request_failed"
    # Refused at the allowlist BEFORE any socket — nothing reached the endpoint.
    assert loop.recorded == []
    assert "real-vault-http-token" not in json.dumps(evidence)


# --------------------------------------------------------------------------- #
# Plug-and-play: a SECOND arbitrary service with NO new platform code
# --------------------------------------------------------------------------- #
def test_second_arbitrary_channel_works_with_zero_platform_code(tmp_path, monkeypatch):
    monkeypatch.setenv(_HTTP_FLAG, "1")
    # A service the platform has never heard of — different host, different auth
    # scheme (custom header instead of bearer). No module code changes.
    data_root, universe_dir, db_path = _setup(
        tmp_path,
        provider="http",
        destination="api.brand-new-service.test",
        auth_scheme="header",
        token="other-secret",
        vault_name="other-conn",
        endpoints=[
            {
                "host": "api.brand-new-service.test",
                "path_template": "/send",
                "methods": ["POST"],
            }
        ],
    )
    loop = _Loopback()
    _install_loopback_driver(monkeypatch, loop.port)
    _install_inprocess_proxy(
        monkeypatch,
        db_path=db_path,
        universe_dir=universe_dir,
        grant_id="grant-http",
        provider="http",
        destination="api.brand-new-service.test",
        runtime_root=tmp_path / "rt2",
    )

    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {
            "path": "/send",
            "header_name": "X-Api-Key",
            "body": {"msg": "hi"},
        },
    }
    run_state = {"o": json.dumps(packet)}
    try:
        evidence = run_authenticated_external_call_effector(
            node_id="n",
            output_keys=["o"],
            run_state=run_state,
            base_path=str(universe_dir),
        )
    finally:
        loop.stop()

    assert evidence["delivered"] is True
    rec = loop.recorded[0]
    assert rec["method"] == "POST"
    assert rec["path"] == "/send"
    # The DIFFERENT auth scheme applied the credential in the DIFFERENT header.
    assert rec["headers"]["X-Api-Key"] == "other-secret"
    assert "Authorization" not in rec["headers"]
    assert "other-secret" not in json.dumps(evidence)


# --------------------------------------------------------------------------- #
# Real spawned worker: credential resolved by the worker; effector stays blind
# --------------------------------------------------------------------------- #
def test_real_spawned_worker_resolves_credential_and_stays_blind(tmp_path, monkeypatch):
    monkeypatch.setenv(_HTTP_FLAG, "1")
    data_root, universe_dir, db_path = _setup(tmp_path)

    # A non-allowlisted host: the REAL spawned worker RESOLVES the credential from
    # the vault, then the allowlist refuses the destination — proving the worker
    # (not the effector) applied the credential. NO _open_connection_proxy or
    # driver monkeypatch: this is the genuine spawned-worker path.
    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {"host": "not-allowed.example", "path": "/v1/messages", "body": {"x": 1}},
    }
    run_state = {"out": json.dumps(packet)}
    evidence = run_authenticated_external_call_effector(
        node_id="n",
        output_keys=["out"],
        run_state=run_state,
        base_path=str(universe_dir),
    )

    assert evidence["error_kind"] == "outbound_request_failed"
    assert "real-vault-http-token" not in json.dumps(evidence)

    audit = _read_audit(data_root, "grant-http")
    # "destination request failed" (reached the driver) NOT "credential
    # unavailable" — the worker DID resolve the vault credential.
    assert [r["reason"] for r in audit] == ["destination request failed"]
    assert "real-vault-http-token" not in json.dumps(audit)


# --------------------------------------------------------------------------- #
# Isolation: a grant bound to another universe cannot be borrowed
# --------------------------------------------------------------------------- #
def test_grant_from_another_universe_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(_HTTP_FLAG, "1")
    data_root, universe_dir, db_path = _setup(
        tmp_path, universe_id="universe-1", grant_universe="universe-1"
    )
    other_dir = data_root / "universe-2"
    other_dir.mkdir(exist_ok=True)

    def _must_not_open(**_k):
        raise AssertionError("proxy must not open for a cross-universe grant")

    monkeypatch.setattr(aec, "_open_connection_proxy", _must_not_open)

    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {"path": "/v1/messages", "body": {"x": 1}},
    }
    run_state = {"out": json.dumps(packet)}
    evidence = run_authenticated_external_call_effector(
        node_id="n",
        output_keys=["out"],
        run_state=run_state,
        base_path=str(other_dir),  # running universe-2; grant is bound to universe-1
    )
    assert evidence["error_kind"] == "grant_not_for_universe"


# --------------------------------------------------------------------------- #
# Shape guards + declaration + static "no channel" proof
# --------------------------------------------------------------------------- #
def test_missing_packet_returns_no_matching_packet(tmp_path):
    evidence = run_authenticated_external_call_effector(
        node_id="n",
        output_keys=["out"],
        run_state={"out": "not a packet"},
        base_path=str(tmp_path / "universe-1"),
    )
    assert evidence["error_kind"] == "no_matching_packet"


def test_method_that_disagrees_with_verb_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(_HTTP_FLAG, "1")
    data_root, universe_dir, db_path = _setup(tmp_path)

    monkeypatch.setattr(
        aec, "_open_connection_proxy", lambda **_k: (_ for _ in ()).throw(AssertionError)
    )
    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {"method": "GET", "path": "/v1/messages"},
    }
    evidence = run_authenticated_external_call_effector(
        node_id="n",
        output_keys=["out"],
        run_state={"out": json.dumps(packet)},
        base_path=str(universe_dir),
    )
    assert evidence["error_kind"] == "method_mismatch"


def test_ambiguous_host_without_explicit_host_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(_HTTP_FLAG, "1")
    data_root, universe_dir, db_path = _setup(
        tmp_path,
        endpoints=[
            {"host": "api-a.test", "path_template": "/v1/messages", "methods": ["POST"]},
            {"host": "api-b.test", "path_template": "/v1/messages", "methods": ["POST"]},
        ],
    )
    monkeypatch.setattr(
        aec, "_open_connection_proxy", lambda **_k: (_ for _ in ()).throw(AssertionError)
    )
    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {"path": "/v1/messages"},  # no host, and two are allowlisted
    }
    evidence = run_authenticated_external_call_effector(
        node_id="n",
        output_keys=["out"],
        run_state={"out": json.dumps(packet)},
        base_path=str(universe_dir),
    )
    assert evidence["error_kind"] == "host_ambiguous"


def test_sink_is_registered_and_dispatchable_from_a_branch():
    # A node that declares effects=[the sink] routes to THIS effector via the
    # channel-agnostic dispatch map in effectors/__init__ — the "declaration"
    # mechanism (no per-channel allowlist, no github registry).
    from types import SimpleNamespace

    from tinyassets import effectors as effectors_pkg

    assert effectors_pkg.EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL == (
        EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL
    )
    assert hasattr(effectors_pkg, "run_authenticated_external_call_effector")

    # A branch whose node declares the sink routes to the generic effector and
    # comes back with per-sink evidence. With no packet/connection set up the
    # effector returns a structured error — but NOT "unknown_sink", which proves
    # the dispatch matched the sink to the generic effector (routing, not success).
    branch = SimpleNamespace(
        node_defs=[
            SimpleNamespace(
                node_id="n1",
                output_keys=["out"],
                effects=[EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL],
            )
        ]
    )
    evidence = effectors_pkg.run_effects_for_branch(
        branch=branch,
        run_state={},
        base_path=None,
        run_id="r1",
    )
    assert EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL in evidence["n1"]
    assert (
        evidence["n1"][EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL].get("error_kind")
        != "unknown_sink"
    )


def test_module_names_no_channel():
    src = Path(aec.__file__).read_text(encoding="utf-8").lower()
    for banned in (
        "github",
        "slack",
        "twitter",
        "x.com",
        "tweet",
        "pull_request",
        "postmessage",
        "anthropic",
        "openai",
    ):
        assert banned not in src, f"channel-specific token {banned!r} leaked in"


# --------------------------------------------------------------------------- #
# Authorization gates (Codex reject 2026-08-20): a connection grant ALONE must
# NOT fire an effect — soul authority must not DENY, and effector consent for
# the destination must be active. These prove the generic effector keeps the
# gates the deleted per-channel effectors enforced.
# --------------------------------------------------------------------------- #
def test_missing_consent_refuses_before_any_egress(tmp_path, monkeypatch):
    # A connection grant WITHOUT an effector-consent grant is refused at the
    # authorization gate — BEFORE the worker opens, so nothing reaches the wire.
    monkeypatch.setenv(_HTTP_FLAG, "1")
    data_root, universe_dir, db_path = _setup(tmp_path, grant_consent_for=False)
    loop = _Loopback()
    _install_loopback_driver(monkeypatch, loop.port)
    _install_inprocess_proxy(
        monkeypatch,
        db_path=db_path,
        universe_dir=universe_dir,
        grant_id="grant-http",
        provider="http",
        destination="api.example.com",
        runtime_root=tmp_path / "rt-noconsent",
    )
    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {"method": "POST", "path": "/v1/messages", "body": {"text": "x"}},
    }
    try:
        evidence = run_authenticated_external_call_effector(
            node_id="n1",
            output_keys=["out"],
            run_state={"out": json.dumps(packet)},
            base_path=str(universe_dir),
            run_id="r1",
        )
    finally:
        loop.stop()
    assert evidence["error_kind"] == "missing_consent"
    assert evidence.get("dry_run") is True
    assert evidence.get("delivered") is not True
    # Decisive proof: NOTHING reached the destination.
    assert loop.recorded == []


def test_revoked_consent_refuses_the_call(tmp_path, monkeypatch):
    # Consent granted then revoked must close the gate — an active connection
    # grant must NOT bypass a revoked destination consent.
    monkeypatch.setenv(_HTTP_FLAG, "1")
    data_root, universe_dir, db_path = _setup(tmp_path)  # grants consent
    from tinyassets.storage.effector_consents import revoke_consent

    revoke_consent(
        universe_dir,
        sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        destination="api.example.com",
    )
    packet = {
        "sink": EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        "connection_id": "conn-http",
        "grant_id": "grant-http",
        "verb": "POST",
        "request": {"method": "POST", "path": "/v1/messages", "body": {"text": "x"}},
    }
    evidence = run_authenticated_external_call_effector(
        node_id="n1",
        output_keys=["out"],
        run_state={"out": json.dumps(packet)},
        base_path=str(universe_dir),
        run_id="r1",
    )
    assert evidence["error_kind"] == "missing_consent"
