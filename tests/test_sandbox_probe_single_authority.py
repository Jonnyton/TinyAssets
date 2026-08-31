"""There must be exactly ONE bwrap probe, and it must ask the launcher's question.

#2736 fixed ``tinyassets/sandbox/detect.py`` to build its functional probe from
the launcher's own argv. A second, older probe survived in
``tinyassets/providers/base.py`` -- ``bwrap --ro-bind / / /bin/sh -c true`` --
and the two disagreed on a real host.

Measured 2026-08-31 inside the Linux oracle container (bwrap 0.12.0,
``--security-opt seccomp=unconfined``)::

    $ bwrap --ro-bind / / /bin/sh -c true
    bwrap: Creating new namespace failed: Operation not permitted   # rc=1
    $ bwrap --die-with-parent --new-session --unshare-all --clearenv ... -- python -c ""
    # rc=0

So the host ran the jail exactly as production uses it while the probe called
it unavailable. That is not cosmetic: ``tests/test_node_sandbox.py`` gates
``requires_bwrap`` on ``probe_sandbox_available``, so six hostile-code jail
tests -- among them the positive control asserting the jail runs a node at all
-- SKIPPED on CI and on the oracle instead of running. A skipped boundary test
looks exactly like a passing one in a summary line.

These tests pin the property, not the wording: whatever the probe becomes, both
callers must reach the same one, and it must be built from the launcher's argv.
"""
from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from tinyassets.providers.base import probe_sandbox_available


def _captured_probe_argv(monkeypatch) -> list[str]:
    """The argv `probe_sandbox_available` actually executes for its launch test.

    Captured from the real call rather than reconstructed, because the whole
    defect was a second argv nobody was looking at.
    """
    monkeypatch.setattr("sys.platform", "linux")
    calls: list[list[str]] = []

    class _R:
        returncode = 0
        stdout = "bwrap 0.12.0"
        stderr = ""

    def _fake_run(argv, *a, **kw):
        calls.append(list(argv))
        return _R()

    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        with patch("subprocess.run", side_effect=_fake_run):
            probe_sandbox_available()

    assert len(calls) == 2, f"expected a --version call then a launch call, got {calls}"
    return calls[1]


def test_the_probe_asks_what_the_launcher_asks(monkeypatch) -> None:
    """The launch probe must carry the launcher's isolation flags."""
    argv = _captured_probe_argv(monkeypatch)
    for flag in ("--unshare-all", "--clearenv", "--die-with-parent", "--new-session"):
        assert flag in argv, (
            f"the functional probe does not pass {flag}, so it is asking a "
            f"different question than the launcher: {argv}"
        )


def test_the_old_divergent_probe_is_gone(monkeypatch) -> None:
    """`--ro-bind / /` with /bin/sh is the shape that disagreed. It must not return."""
    argv = _captured_probe_argv(monkeypatch)
    joined = " ".join(argv)
    assert "--ro-bind / /" not in joined, f"the old probe shape is back: {argv}"
    assert "/bin/sh" not in argv, (
        "/bin/sh need not exist inside a private root; the launcher's own "
        f"interpreter is the right command: {argv}"
    )


def test_both_call_sites_reach_the_same_probe(monkeypatch) -> None:
    """`providers.base` must DELEGATE, not carry its own implementation.

    Asserted through behaviour: patching the single authority must change what
    `probe_sandbox_available` returns. If it kept a private probe, it would not.
    """
    import tinyassets.sandbox.detect as detect
    from tinyassets.sandbox.detect import SandboxStatus

    sentinel = SandboxStatus(available=False, reason="sentinel from the one probe")
    monkeypatch.setattr(detect, "detect_bwrap", lambda: sentinel)

    result = probe_sandbox_available()
    assert result["bwrap_available"] is False
    assert result["reason"] == "sentinel from the one probe", (
        "providers.base did not go through sandbox.detect - it still owns a "
        "second probe"
    )


def test_providers_base_builds_no_bwrap_arguments_of_its_own() -> None:
    """Source-level backstop: a copied argv is invisible to behaviour tests
    until the day the two hosts disagree, which is the day it costs something.

    Parsed, not grepped. The docstring in that module quotes the old probe on
    purpose, and a line-wise search cannot tell prose from an argument list --
    an AST walk compares whole string CONSTANTS, so `"--ro-bind"` as an argv
    element is caught while the same characters inside a docstring are not.
    """
    import ast

    import tinyassets.providers.base as base

    tree = ast.parse(inspect.getsource(base))
    flags = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("--")
    }
    bwrap_flags = flags & {
        "--ro-bind", "--bind", "--unshare-all", "--clearenv", "--proc",
        "--dev", "--tmpfs", "--die-with-parent", "--new-session", "--chdir",
    }
    assert not bwrap_flags, (
        "providers/base.py builds bwrap arguments again; the probe belongs to "
        f"sandbox/detect.py alone: {sorted(bwrap_flags)}"
    )


@pytest.mark.parametrize(
    "status_kwargs, expect_available, expect_reason_contains",
    [
        ({"available": True, "reason": None}, True, None),
        ({"available": False, "reason": "bwrap not found on PATH"}, False, "PATH"),
        (
            {"available": False, "reason": "bwrap functional probe exited 1: nope"},
            False,
            "functional probe",
        ),
    ],
)
def test_the_dict_contract_survives_the_delegation(
    monkeypatch, status_kwargs, expect_available, expect_reason_contains
) -> None:
    """Callers and the status surface read these two keys; keep them exact."""
    import tinyassets.sandbox.detect as detect
    from tinyassets.sandbox.detect import SandboxStatus

    monkeypatch.setattr(detect, "detect_bwrap", lambda: SandboxStatus(**status_kwargs))
    result = probe_sandbox_available()

    assert set(result) == {"bwrap_available", "reason"}
    assert result["bwrap_available"] is expect_available
    if expect_reason_contains is None:
        assert result["reason"] is None
    else:
        assert expect_reason_contains in str(result["reason"])
