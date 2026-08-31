"""Tests for tinyassets.sandbox.detect — bwrap detection module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tinyassets.sandbox import (
    _BWRAP_FAILURE_PATTERNS,
    SandboxStatus,
    SandboxUnavailableError,
    check_bwrap_output,
    detect_bwrap,
)

# ─── SandboxStatus dataclass ──────────────────────────────────────────────────

class TestSandboxStatus:
    def test_available_true(self):
        s = SandboxStatus(available=True, bwrap_path="/usr/bin/bwrap", version="bwrap 0.6.0")
        assert s.available is True

    def test_available_false_with_reason(self):
        s = SandboxStatus(available=False, reason="not on PATH")
        assert s.available is False
        assert s.reason == "not on PATH"

    def test_to_dict_includes_all_fields(self):
        s = SandboxStatus(
            available=True, reason=None, bwrap_path="/usr/bin/bwrap", version="0.6.0",
        )
        d = s.to_dict()
        assert "available" in d
        assert "reason" in d
        assert "bwrap_path" in d
        assert "version" in d

    def test_defaults(self):
        s = SandboxStatus(available=False)
        assert s.reason is None
        assert s.bwrap_path is None
        assert s.version is None


# ─── SandboxUnavailableError ──────────────────────────────────────────────────

class TestSandboxUnavailableError:
    def test_is_exception(self):
        err = SandboxUnavailableError("test")
        assert isinstance(err, Exception)

    def test_message_preserved(self):
        err = SandboxUnavailableError("sandbox gone")
        assert "sandbox gone" in str(err)


# ─── check_bwrap_output ───────────────────────────────────────────────────────

class TestCheckBwrapOutput:
    def test_raises_on_namespace_pattern(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        with pytest.raises(SandboxUnavailableError):
            check_bwrap_output("bwrap: No permissions to create a new namespace")

    def test_raises_on_namespace_pattern_without_article(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        with pytest.raises(SandboxUnavailableError):
            check_bwrap_output("bwrap: No permissions to create new namespace")

    def test_raises_on_no_such_file_pattern(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        with pytest.raises(SandboxUnavailableError):
            check_bwrap_output("bwrap: No such file or directory")

    def test_raises_on_sandbox_init_failed(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        with pytest.raises(SandboxUnavailableError):
            check_bwrap_output("sandbox initialization failed: something went wrong")

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        with pytest.raises(SandboxUnavailableError):
            check_bwrap_output("BWRAP: NO PERMISSIONS TO CREATE A NEW NAMESPACE")

    def test_no_raise_on_normal_output(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        check_bwrap_output("Successfully compiled the node")
        check_bwrap_output("")
        check_bwrap_output("some other error without the magic string")

    def test_error_message_contains_fix_options(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        with pytest.raises(SandboxUnavailableError, match="Fix options"):
            check_bwrap_output("bwrap: No permissions to create a new namespace")

    def test_all_patterns_raise(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        for pattern in _BWRAP_FAILURE_PATTERNS:
            with pytest.raises(SandboxUnavailableError):
                check_bwrap_output(pattern)

    def test_noop_on_non_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        check_bwrap_output("bwrap: No permissions to create a new namespace")


# ─── detect_bwrap ─────────────────────────────────────────────────────────────

class TestDetectBwrap:
    def test_non_linux_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        status = detect_bwrap()
        assert status.available is False
        assert "win32" in (status.reason or "")

    def test_bwrap_not_on_path_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        with patch("shutil.which", return_value=None):
            status = detect_bwrap()
        assert status.available is False
        assert "PATH" in (status.reason or "")

    def test_bwrap_version_and_launch_success_returns_available(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        version_result = type("R", (), {
            "returncode": 0,
            "stdout": "bwrap 0.6.0",
            "stderr": "",
        })()
        launch_result = type("R", (), {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        })()
        with patch("shutil.which", return_value="/usr/bin/bwrap"):
            with patch("subprocess.run", side_effect=[version_result, launch_result]) as run_mock:
                status = detect_bwrap()
        assert status.available is True
        assert status.bwrap_path == "/usr/bin/bwrap"
        assert status.version == "bwrap 0.6.0"
        assert status.reason is None
        assert run_mock.call_count == 2

    def test_bwrap_launch_failure_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        version_result = type("R", (), {
            "returncode": 0,
            "stdout": "bwrap 0.6.0",
            "stderr": "",
        })()
        launch_result = type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "bwrap: No permissions to create new namespace",
        })()
        with patch("shutil.which", return_value="/usr/bin/bwrap"):
            with patch("subprocess.run", side_effect=[version_result, launch_result]):
                status = detect_bwrap()
        assert status.available is False
        assert status.bwrap_path == "/usr/bin/bwrap"
        assert "functional probe" in (status.reason or "")
        assert "No permissions" in (status.reason or "")

    def test_bwrap_version_fails_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        mock_result = type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "permission denied",
        })()
        with patch("shutil.which", return_value="/usr/bin/bwrap"):
            with patch("subprocess.run", return_value=mock_result):
                status = detect_bwrap()
        assert status.available is False
        assert status.bwrap_path == "/usr/bin/bwrap"
        assert "permission denied" in (status.reason or "")

    def test_probe_oserror_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        with patch("shutil.which", return_value="/usr/bin/bwrap"):
            with patch("subprocess.run", side_effect=OSError("spawn failed")):
                status = detect_bwrap()
        assert status.available is False
        assert "probe error" in (status.reason or "")

    def test_returns_sandbox_status_type(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        status = detect_bwrap()
        assert isinstance(status, SandboxStatus)

    def test_available_false_when_returncode_nonzero(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        mock_result = type("R", (), {
            "returncode": 2,
            "stdout": "",
            "stderr": "",
        })()
        with patch("shutil.which", return_value="/usr/bin/bwrap"):
            with patch("subprocess.run", return_value=mock_result):
                status = detect_bwrap()
        assert status.available is False


def test_the_functional_probe_asks_what_the_launcher_asks() -> None:
    """A probe that runs different flags than the launcher answers a different
    question. This one used to run ``bwrap --ro-bind / / /bin/sh -c true``
    while the launcher runs ``--unshare-all --clearenv`` with its own binds;
    measured side by side, the probe failed with "Creating new namespace
    failed" on a host where the real launch succeeded, so every code node would
    have been refused on a host where the jail works.
    """
    import sys

    from tinyassets.node_sandbox import _bwrap_argv
    from tinyassets.sandbox.detect import _functional_probe_argv

    argv = _functional_probe_argv("/usr/bin/bwrap")
    launcher = _bwrap_argv(bwrap_path="/usr/bin/bwrap")

    assert argv[: len(launcher)] == launcher, (
        "the probe must be built from the launcher's own argv, not a "
        "hand-written approximation of it"
    )
    assert argv[len(launcher) :] == [sys.executable, "-c", ""]
    for flag in ("--unshare-all", "--clearenv", "--die-with-parent"):
        assert flag in argv, f"the probe lost the launcher's {flag}"
    # The old spelling asked an easier question and a different one.
    assert argv[1:3] != ["--ro-bind", "/"], "the probe reverted to the loose root bind"
    assert "/bin/sh" not in argv, (
        "/bin/sh need not exist inside a private root; probe with the "
        "interpreter the launcher already binds"
    )
