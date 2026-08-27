"""The broker child's startup failure must name its cause.

Regression cover for a live founder-visible outage: an X post failed for three
days behind the fixed string ``outbound proxy failed to start``. The child
swallowed the real exception (bare ``except Exception``) and the parent threw
away even the child's reply, so neither the founder, the universe, nor the host
could ever learn WHY -- a Hard Rule 8 (fail loudly, never silently) hole sitting
on the egress path.

These tests pin the contract that makes the next failure diagnosable, not the
specific cause of that outage.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.storage.outbound_connections import (
    _DEFAULT_PROXY_STARTUP_TIMEOUT_S,
    _MAX_PROXY_STARTUP_TIMEOUT_S,
    _PROXY_STARTUP_TIMEOUT_VAR,
    ConnectionLedger,
    ProxyRequestError,
    _describe_child_exit,
    _proxy_startup_timeout_seconds,
    _run_proxy_worker,
)

#: The budget that shipped before this fix. A cold ``spawn`` re-import of the
#: package chain can exceed it on a loaded host, so the default must clear it.
_LEGACY_STARTUP_BUDGET_S = 5.0


class _CapturingChannel:
    """Stands in for the child's end of the pipe; records what it was sent."""

    def __init__(self) -> None:
        self.sent: list[object] = []
        self.closed = False

    def send_bytes(self, payload: bytes) -> None:
        self.sent.append(json.loads(payload.decode("utf-8")))

    def close(self) -> None:
        self.closed = True


def test_worker_startup_failure_reports_the_exception_class_not_a_fixed_string():
    channel = _CapturingChannel()

    # An unregistered factory reference makes `_load_dispatch_factory` raise
    # ValueError -- standing in for the real causes (a runtime_root mkdir denial,
    # a ledger sqlite open failure, an import error in the spawned child).
    _run_proxy_worker(channel, "not-a-registered-factory", {}, "grant-1", ())

    assert channel.closed is True
    assert len(channel.sent) == 1
    message = channel.sent[0]
    assert message["op"] == "startup_failed"
    # The class crosses the wire; the traceback goes to the child's stderr.
    assert message["cause"] == "ValueError"


def test_worker_startup_failure_carries_no_config_values_across_the_wire():
    """The cause is a class name only -- never config, paths, or credentials."""
    channel = _CapturingChannel()
    secret = "s3cret-credential-material"

    _run_proxy_worker(
        channel,
        "not-a-registered-factory",
        {"credential_ref": secret, "ledger_db_path": "/data/private/ledger.db"},
        "grant-1",
        (),
    )

    serialized = json.dumps(channel.sent)
    assert secret not in serialized
    assert "/data/private" not in serialized


def test_scoped_proxy_start_failure_names_a_cause(tmp_path):
    """A real spawned child that cannot start reports more than the old string."""
    # Block the proxy runtime root with a regular file: the child's
    # `runtime_root.mkdir(parents=True)` then raises inside the factory.
    (tmp_path / ".outbound-proxy").write_text("not a directory", encoding="utf-8")

    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
    ledger.create_connection(
        connection_id="conn-1",
        owner_user_id="user-1",
        connection_class="issue-writer",
        scopes=("issues:write",),
        provider="test-fixture.issue",
        destination="github.com/acme/widgets",
        credential_ref="test-fixture://nonsecret",
    )
    ledger.grant_connection(
        grant_id="grant-1",
        connection_id="conn-1",
        owner_user_id="user-1",
        universe_id="universe-1",
    )

    with pytest.raises(ProxyRequestError) as caught:
        ledger.resolve_scoped_proxy(
            universe_id="universe-1",
            connection_class="issue-writer",
        )

    message = str(caught.value)
    # The point of the fix: the operator can tell WHICH failure this was.
    assert message != "outbound proxy failed to start"
    assert message.startswith("outbound proxy failed to start: ")
    cause = message.split(": ", 1)[1]
    assert cause and cause.isidentifier()


def test_startup_timeout_default_clears_the_legacy_budget(monkeypatch):
    monkeypatch.delenv(_PROXY_STARTUP_TIMEOUT_VAR, raising=False)
    assert _proxy_startup_timeout_seconds() == _DEFAULT_PROXY_STARTUP_TIMEOUT_S
    assert _DEFAULT_PROXY_STARTUP_TIMEOUT_S > _LEGACY_STARTUP_BUDGET_S


@pytest.mark.parametrize("raw", ["12", "12.5", "  12.5  "])
def test_startup_timeout_honors_a_host_override(monkeypatch, raw):
    monkeypatch.setenv(_PROXY_STARTUP_TIMEOUT_VAR, raw)
    assert _proxy_startup_timeout_seconds() == pytest.approx(12.0, abs=0.5)


@pytest.mark.parametrize("raw", ["", "   ", "not-a-number", "0", "-3", "nan", "inf"])
def test_startup_timeout_falls_back_on_an_unusable_override(monkeypatch, raw):
    """A bad override must never yield a zero/negative budget that fails instantly."""
    monkeypatch.setenv(_PROXY_STARTUP_TIMEOUT_VAR, raw)
    assert _proxy_startup_timeout_seconds() == _DEFAULT_PROXY_STARTUP_TIMEOUT_S


# --- Cross-family review round 1 (Codex, ADAPT) -----------------------------
# Codex found the exit reporting INVERTED: `_abandon()` terminated the child
# before reading `exitcode`, so our own SIGTERM (-15) overwrote the real status
# and every timeout was reported as "process exited". It also found that on
# Linux a dead child closes the pipe, so the read hits EOF and used to surface
# as the unrelated "received an invalid message" -- the most likely production
# shape. These pin both.


def _ledger_for(tmp_path):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
    ledger.create_connection(
        connection_id="conn-1",
        owner_user_id="user-1",
        connection_class="issue-writer",
        scopes=("issues:write",),
        provider="test-fixture.issue",
        destination="github.com/acme/widgets",
        credential_ref="test-fixture://nonsecret",
    )
    ledger.grant_connection(
        grant_id="grant-1",
        connection_id="conn-1",
        owner_user_id="user-1",
        universe_id="universe-1",
    )
    return ledger


def test_a_live_but_slow_child_is_reported_as_a_timeout_not_a_process_exit(
    tmp_path, monkeypatch
):
    """The regression Codex caught: our own SIGTERM must not become the verdict."""
    # A budget far below the child's real startup cost, so poll() gives up while
    # the child is still ALIVE. Before the fix this reported "exitcode -15".
    monkeypatch.setenv(_PROXY_STARTUP_TIMEOUT_VAR, "0.001")

    with pytest.raises(ProxyRequestError) as caught:
        _ledger_for(tmp_path).resolve_scoped_proxy(
            universe_id="universe-1",
            connection_class="issue-writer",
        )

    message = str(caught.value)
    assert "did not finish starting within" in message
    assert "exitcode" not in message
    assert "killed by signal" not in message


def test_a_child_that_cannot_be_spawned_still_gets_the_diagnostic_contract(
    tmp_path, monkeypatch
):
    """A `worker.start()` failure used to bypass the contract entirely."""

    class _Unspawnable:
        def __reduce__(self):
            raise TypeError("this object refuses to pickle")

    # `spawn` pickles the child's args, so an unpicklable config kills start().
    monkeypatch.setattr(
        "tinyassets.storage.outbound_connections._outbound_http_enabled",
        lambda: _Unspawnable(),
    )

    with pytest.raises(ProxyRequestError) as caught:
        _ledger_for(tmp_path).resolve_scoped_proxy(
            universe_id="universe-1",
            connection_class="issue-writer",
        )

    assert "could not be spawned" in str(caught.value)


@pytest.mark.parametrize(
    ("exitcode", "expected"),
    [
        (None, ""),
        (0, " (exitcode 0)"),
        (1, " (exitcode 1)"),
        (-9, " (killed by signal 9)"),   # the OOM killer
        (-15, " (killed by signal 15)"),  # SIGTERM
    ],
)
def test_child_exit_is_described_as_a_signal_when_it_was_a_signal(exitcode, expected):
    assert _describe_child_exit(exitcode) == expected


def test_startup_timeout_is_capped(monkeypatch):
    """An unbounded budget lets hung startups stall the small run-executor pool."""
    monkeypatch.setenv(_PROXY_STARTUP_TIMEOUT_VAR, "99999")
    assert _proxy_startup_timeout_seconds() == _MAX_PROXY_STARTUP_TIMEOUT_S


def test_an_explicitly_invalid_budget_is_announced_not_swallowed(monkeypatch, capsys):
    monkeypatch.setenv(_PROXY_STARTUP_TIMEOUT_VAR, "not-a-number")
    assert _proxy_startup_timeout_seconds() == _DEFAULT_PROXY_STARTUP_TIMEOUT_S
    assert _PROXY_STARTUP_TIMEOUT_VAR in capsys.readouterr().err
