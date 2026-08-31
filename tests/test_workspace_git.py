"""Tests for the credential-blind git layer (``tinyassets.workspace_git``).

Two kinds of test live here. The pure ones drive the broker protocol, the
environment, the forced options, address pinning and stderr classification
with injected fakes, so they run identically on Linux and Windows. The bundle
tests drive a REAL ``git``: the whole point of the bundle path is what git
actually writes into ``.git/config``, which a fake launcher cannot prove.
They skip when git is not on PATH.
"""

from __future__ import annotations

import itertools
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tinyassets import workspace_git as wg
from tinyassets.workspace_git import (
    CredentialBroker,
    GitResult,
    WorkspaceGitError,
    classify_stderr,
    create_bundle,
    forced_git_options,
    git_environment,
    kill_git,
    libcurl_supports_multi_resolve,
    pin_address,
    populate_workspace_from_bundle,
    run_git,
    scrub_text,
    unbundle_into_fresh_repo,
    verify_bundle,
)

TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
IS_WINDOWS = os.name == "nt"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeCompleted:
    returncode: int = 0
    stdout: bytes = b""
    stderr: bytes = b""


class RecordingLauncher:
    """Stands in for ``subprocess.run`` and records exactly what it was given."""

    def __init__(self, result: FakeCompleted | None = None, raises: BaseException | None = None):
        self.result = result or FakeCompleted()
        self.raises = raises
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), dict(kwargs)))
        if self.raises is not None:
            raise self.raises
        return self.result

    @property
    def last_command(self) -> list[str]:
        return self.calls[-1][0]

    @property
    def last_kwargs(self) -> dict[str, object]:
        return self.calls[-1][1]


_SCRATCH_COUNTER = itertools.count()


def _fresh_scratch(tmp_path: Path) -> Path:
    """A new empty directory for one bundle verification."""
    scratch = tmp_path / f"vscratch-{next(_SCRATCH_COUNTER)}"
    scratch.mkdir()
    return scratch


@pytest.fixture()
def empty_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture()
def posix_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive the POSIX branch on any host -- production is Linux, this box is not.

    Without this, every POSIX-only behaviour is asserted by its ABSENCE on
    Windows, and a mutation that deletes the behaviour stays green here.
    """
    monkeypatch.setattr(wg, "_IS_WINDOWS", False)


@pytest.fixture()
def windows_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wg, "_IS_WINDOWS", True)


@pytest.fixture()
def broker() -> CredentialBroker:
    made = CredentialBroker("https", "github.com", "owner/repo.git", "x-access-token", TOKEN)
    yield made
    made.close()


def _get_request(host: str = "github.com", path: str = "owner/repo.git") -> str:
    return f"operation=get\nprotocol=https\nhost={host}\npath={path}\n\n"


# ---------------------------------------------------------------------------
# 1. the module reads no environment variables
# ---------------------------------------------------------------------------


def test_module_source_never_reads_an_environment_variable() -> None:
    source = Path(wg.__file__).read_text(encoding="utf-8")
    # ``\benviron\b`` matches ``os.environ`` but not ``git_environment`` -- the
    # required public name contains the substring, so a substring grep cannot
    # be the assertion.
    assert re.search(r"\benviron\b", source) is None
    for forbidden in ("os.environ", "getenv", "putenv", "environb", "expandvars"):
        assert forbidden not in source


def test_module_docstring_states_the_boundary_verbatim() -> None:
    """The boundary statement is normative (design D1, round 3) -- not a gloss."""
    doc = " ".join((wg.__doc__ or "").split())
    assert "credential-blind" in doc.lower()
    for sentence in (
        "No credentialed git ever opens a workspace.",
        "No host-side git opens a workspace's ``.git`` after the workspace is "
        "published to user code.",
        "A host-side, credential-free initializer may populate a fresh, "
        "unpublished directory from a verified bundle.",
    ):
        assert " ".join(sentence.split()) in doc


# ---------------------------------------------------------------------------
# 2. CredentialBroker.answer -- the protocol, in process
# ---------------------------------------------------------------------------


def test_broker_answers_a_matching_get(broker: CredentialBroker) -> None:
    assert broker.answer(_get_request()) == f"username=x-access-token\npassword={TOKEN}\n"


def test_broker_answers_a_repeated_get_after_a_401(broker: CredentialBroker) -> None:
    first = broker.answer(_get_request())
    second = broker.answer(_get_request())
    assert first == second
    assert second is not None and TOKEN in second


def test_broker_matches_the_path_with_use_http_path_semantics(broker: CredentialBroker) -> None:
    for spelling in ("owner/repo", "owner/repo.git", "/owner/repo/", "/owner/repo.git"):
        assert broker.answer(_get_request(path=spelling)) is not None


def test_broker_refuses_another_path(broker: CredentialBroker) -> None:
    assert broker.answer(_get_request(path="owner/other")) is None
    assert broker.answer(_get_request(path="attacker/repo")) is None
    # a prefix is not a match
    assert broker.answer(_get_request(path="owner/repo-evil")) is None


def test_broker_refuses_another_host(broker: CredentialBroker) -> None:
    assert broker.answer(_get_request(host="evil.example")) is None
    assert broker.answer(_get_request(host="github.com.evil.example")) is None


def test_broker_accepts_the_default_port_and_refuses_another(broker: CredentialBroker) -> None:
    assert broker.answer(_get_request(host="github.com:443")) is not None
    assert broker.answer(_get_request(host="github.com:8443")) is None


def test_broker_refuses_another_protocol(broker: CredentialBroker) -> None:
    request = "operation=get\nprotocol=http\nhost=github.com\npath=owner/repo\n"
    assert broker.answer(request) is None


def test_broker_refuses_a_request_without_a_path(broker: CredentialBroker) -> None:
    assert broker.answer("operation=get\nprotocol=https\nhost=github.com\n") is None


def test_broker_refuses_another_username(broker: CredentialBroker) -> None:
    request = _get_request() + "username=someone-else\n"
    assert broker.answer(request) is None


def test_broker_ignores_store_and_erase(broker: CredentialBroker) -> None:
    for operation in ("store", "erase"):
        request = f"operation={operation}\nprotocol=https\nhost=github.com\npath=owner/repo\n"
        answered = broker.answer(request)
        assert answered == ""
        assert TOKEN not in (answered or "")


def test_broker_refuses_an_unknown_operation(broker: CredentialBroker) -> None:
    unknown = "operation=capability\nprotocol=https\nhost=github.com\npath=owner/repo\n"
    assert broker.answer(unknown) is None
    assert broker.answer("") is None


def test_broker_ignores_unknown_keys(broker: CredentialBroker) -> None:
    request = _get_request() + "wwwauth[]=Basic realm=x\ncapability[]=authtype\n"
    assert broker.answer(request) is not None


def test_broker_exposes_nothing_after_close() -> None:
    made = CredentialBroker("https", "github.com", "owner/repo", "x-access-token", TOKEN)
    assert made.answer(_get_request()) is not None
    made.close()
    assert made.answer(_get_request()) is None
    store = "operation=store\nprotocol=https\nhost=github.com\npath=owner/repo\n"
    assert made.answer(store) is None
    with pytest.raises(WorkspaceGitError) as caught:
        _ = made.helper_command
    assert caught.value.code == "bad_argument"
    made.close()  # idempotent


@pytest.mark.parametrize(
    "kwargs",
    [
        {"protocol": "http"},
        {"host": ""},
        {"path": ""},
        {"username": ""},
        {"secret": ""},
        {"secret": "short"},
        {"host": "github.com\nevil"},
        {"secret": f"{TOKEN}\nprotocol=https"},
        {"path": "/"},
    ],
)
def test_broker_refuses_a_malformed_construction(kwargs: dict[str, str]) -> None:
    fields = {
        "protocol": "https",
        "host": "github.com",
        "path": "owner/repo",
        "username": "x-access-token",
        "secret": TOKEN,
    }
    fields.update(kwargs)
    with pytest.raises(WorkspaceGitError) as caught:
        CredentialBroker(**fields)
    assert caught.value.code == "bad_argument"


# ---------------------------------------------------------------------------
# 3. the broker's transport
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not IS_WINDOWS, reason="POSIX transport is exercised on POSIX")
def test_serve_refuses_loudly_on_windows(tmp_path: Path, broker: CredentialBroker) -> None:
    with pytest.raises(WorkspaceGitError) as caught:
        broker.serve(socket_dir=tmp_path)
    assert caught.value.code == "transport"


@pytest.mark.skipif(IS_WINDOWS, reason="unix domain sockets")
def test_serve_answers_over_the_unix_socket(tmp_path: Path, broker: CredentialBroker) -> None:
    socket_dir = Path("/tmp") / f"wgb-{os.getpid()}"
    socket_dir.mkdir(parents=True, exist_ok=False)
    try:
        helper = broker.serve(socket_dir=socket_dir)
        assert helper.startswith("!")
        assert str(socket_dir / "credential.sock") in helper
        assert (socket_dir / "credential_helper.py").is_file()
        assert broker.helper_command == helper

        for _ in range(2):  # a 401 retry issues a second get
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(5.0)
            client.connect(str(socket_dir / "credential.sock"))
            client.sendall(_get_request().encode("utf-8"))
            client.shutdown(socket.SHUT_WR)
            received = b""
            while True:
                block = client.recv(4096)
                if not block:
                    break
                received += block
            client.close()
            assert received.decode() == f"username=x-access-token\npassword={TOKEN}\n"

        # a request for another repository is answered with nothing at all
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(5.0)
        client.connect(str(socket_dir / "credential.sock"))
        client.sendall(_get_request(path="attacker/repo").encode("utf-8"))
        client.shutdown(socket.SHUT_WR)
        assert client.recv(4096) == b""
        client.close()

        broker.close()
        assert not (socket_dir / "credential.sock").exists()
    finally:
        shutil.rmtree(socket_dir, ignore_errors=True)


def test_helper_command_is_unavailable_before_serving(broker: CredentialBroker) -> None:
    with pytest.raises(WorkspaceGitError):
        _ = broker.helper_command


# ---------------------------------------------------------------------------
# 4. secret registration and scrubbing
# ---------------------------------------------------------------------------


def test_a_live_broker_registers_its_secret_for_scrubbing() -> None:
    text = f"remote: https://x-access-token:{TOKEN}@github.com/owner/repo"
    with CredentialBroker("https", "github.com", "owner/repo", "u", TOKEN) as made:
        assert made.answer(_get_request()) is not None
        scrubbed = scrub_text(text)
        assert TOKEN not in scrubbed
        assert "[redacted]" in scrubbed
    # after close the exact secret is no longer registered; the generic
    # patterns still catch it
    assert TOKEN not in scrub_text(text)


def test_scrub_removes_generic_credential_shapes() -> None:
    raw = (
        "fatal: unable to access 'https://user:s3cr3t@github.com/o/r.git/'\n"
        "Authorization: Basic dXNlcjpwYXNz\n"
        "token ghp_0123456789ABCDEFGHIJKLMNOPQRSTUV used\n"
        "token github_pat_11ABCDEFG0123456789_abcdefghijklmnop used\n"
    )
    scrubbed = scrub_text(raw)
    assert "s3cr3t" not in scrubbed
    assert "dXNlcjpwYXNz" not in scrubbed
    assert "ghp_0123456789ABCDEFGHIJKLMNOPQRSTUV" not in scrubbed
    assert "github_pat_11ABCDEFG0123456789_abcdefghijklmnop" not in scrubbed
    assert scrubbed.count("[redacted]") >= 4


def test_error_messages_are_scrubbed_in_args_not_only_in_str() -> None:
    with CredentialBroker("https", "github.com", "owner/repo", "u", TOKEN):
        error = WorkspaceGitError("auth", f"git said {TOKEN}")
    assert TOKEN not in str(error)
    assert TOKEN not in repr(error)
    assert all(TOKEN not in str(arg) for arg in error.args)
    assert error.code == "auth"


def test_an_unknown_error_code_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        WorkspaceGitError("nonsense", "x")


# ---------------------------------------------------------------------------
# 5. git_environment
# ---------------------------------------------------------------------------


def test_git_environment_key_set_is_exactly_the_specified_list(empty_home: Path) -> None:
    built = git_environment(empty_home, path="/usr/bin")
    assert set(built) == {
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_TERMINAL_PROMPT",
        "GIT_ASKPASS",
        "HOME",
        "PATH",
        "LANG",
    }
    assert set(built) == set(wg.GIT_ENVIRONMENT_KEYS)


def test_git_environment_values(empty_home: Path) -> None:
    built = git_environment(empty_home, path="/usr/bin:/bin")
    null_device = "NUL" if IS_WINDOWS else "/dev/null"
    assert built["GIT_CONFIG_SYSTEM"] == null_device
    assert built["GIT_CONFIG_GLOBAL"] == null_device
    assert built["GIT_CONFIG_NOSYSTEM"] == "1"
    assert built["GIT_TERMINAL_PROMPT"] == "0"
    assert built["GIT_ASKPASS"] == ("NUL" if IS_WINDOWS else "/bin/false")
    assert built["HOME"] == str(empty_home)
    assert built["PATH"] == "/usr/bin:/bin"
    assert built["LANG"] == "C.UTF-8"


def test_git_environment_never_sets_a_trace_variable(empty_home: Path) -> None:
    built = git_environment(empty_home, path="/usr/bin")
    assert not [key for key in built if key.startswith("GIT_TRACE")]


def test_git_environment_refuses_a_non_empty_or_missing_home(tmp_path: Path) -> None:
    populated = tmp_path / "populated"
    populated.mkdir()
    (populated / ".gitconfig").write_text("[user]\n", encoding="utf-8")
    with pytest.raises(WorkspaceGitError) as caught:
        git_environment(populated, path="/usr/bin")
    assert caught.value.code == "bad_argument"
    with pytest.raises(WorkspaceGitError):
        git_environment(tmp_path / "missing", path="/usr/bin")


def test_git_environment_requires_an_explicit_path(empty_home: Path) -> None:
    with pytest.raises(WorkspaceGitError):
        git_environment(empty_home, path="")
    with pytest.raises(WorkspaceGitError):
        git_environment(empty_home, path="/usr/bin\nevil")


# ---------------------------------------------------------------------------
# 6. forced_git_options
# ---------------------------------------------------------------------------


def test_forced_git_options_is_the_exact_pinned_list() -> None:
    null_device = "NUL" if IS_WINDOWS else "/dev/null"
    assert forced_git_options("github.com", "140.82.121.4", "!python helper.py sock") == [
        "-c", f"core.hooksPath={null_device}",
        "-c", "core.fsmonitor=false",
        "-c", "credential.helper=",
        "-c", "credential.helper=!python helper.py sock",
        "-c", "credential.useHttpPath=true",
        "-c", "protocol.allow=never",
        "-c", "protocol.https.allow=always",
        "-c", "http.followRedirects=false",
        "-c", "submodule.recurse=false",
        "-c", "transfer.fsckObjects=true",
        "-c", "fetch.fsckObjects=true",
        "-c", "receive.fsckObjects=true",
        "-c", "http.curloptResolve=github.com:443:140.82.121.4",
    ]


def test_the_empty_credential_helper_comes_first() -> None:
    options = forced_git_options("github.com", "140.82.121.4", "!broker")
    helpers = [value for value in options if value.startswith("credential.helper=")]
    assert helpers == ["credential.helper=", "credential.helper=!broker"]
    # and the reset really precedes the broker in the argument list
    assert options.index("credential.helper=") < options.index("credential.helper=!broker")


def _resolve_rule(options: list[str]) -> str:
    rules = [value for value in options if value.startswith("http.curloptResolve=")]
    assert len(rules) == 1, f"expected exactly one resolve rule, got {rules}"
    return rules[0]


def test_resolve_rule_ipv4_only() -> None:
    options = forced_git_options("github.com", ["140.82.121.4", "140.82.121.3"], "!broker")
    assert _resolve_rule(options) == "http.curloptResolve=github.com:443:140.82.121.4,140.82.121.3"


def test_resolve_rule_ipv6_only_is_bracketed() -> None:
    options = forced_git_options(
        "github.com", ["2606:50c0:8000::153", "2606:50c0:8001::153"], "!broker"
    )
    assert _resolve_rule(options) == (
        "http.curloptResolve=github.com:443:[2606:50c0:8000::153],[2606:50c0:8001::153]"
    )


def test_resolve_rule_mixed_families_keeps_dns_order() -> None:
    options = forced_git_options(
        "github.com", ["2606:50c0:8000::153", "140.82.121.4"], "!broker"
    )
    assert _resolve_rule(options) == (
        "http.curloptResolve=github.com:443:[2606:50c0:8000::153],140.82.121.4"
    )


def test_a_single_address_still_produces_one_rule() -> None:
    for given in ("140.82.121.4", ["140.82.121.4"], ("140.82.121.4",)):
        options = forced_git_options("github.com", given, "!broker")
        assert _resolve_rule(options) == "http.curloptResolve=github.com:443:140.82.121.4"


def test_the_resolve_rule_host_is_canonical_lower_case() -> None:
    options = forced_git_options("GitHub.COM", ["140.82.121.4"], "!broker")
    assert _resolve_rule(options) == "http.curloptResolve=github.com:443:140.82.121.4"


def test_a_host_carrying_a_port_never_reaches_the_resolve_rule() -> None:
    """A resolve entry is (host, port, address); the port is ours, not input."""
    for hostile in ("github.com:8443", "github.com:443", "github.com:80"):
        with pytest.raises(WorkspaceGitError) as caught:
            forced_git_options(hostile, ["140.82.121.4"], "!broker")
        assert caught.value.code == "bad_argument"
    # and the rule we do emit pins 443 and nothing else
    rule = _resolve_rule(forced_git_options("github.com", ["140.82.121.4"], "!broker"))
    assert rule.split(":")[1] == "443"
    assert rule.count(":") == 2


def test_an_address_carrying_a_port_is_refused() -> None:
    with pytest.raises(WorkspaceGitError) as caught:
        forced_git_options("github.com", ["140.82.121.4:8443"], "!broker")
    assert caught.value.code == "bad_argument"


@pytest.mark.parametrize(
    "host,address,helper",
    [
        ("github.com", "not-an-ip", "!broker"),
        ("bad host", "140.82.121.4", "!broker"),
        ("github.com", "140.82.121.4", "!broker\ncore.hooksPath=/tmp/evil"),
        ("github.com", "140.82.121.4", ""),
        ("github.com", [], "!broker"),
        ("github.com", ["140.82.121.4", "10.0.0.5\nevil"], "!broker"),
    ],
)
def test_forced_git_options_refuses_injection(host: str, address, helper: str) -> None:
    with pytest.raises(WorkspaceGitError) as caught:
        forced_git_options(host, address, helper)
    assert caught.value.code == "bad_argument"


@pytest.mark.parametrize(
    "version_text,supported",
    [
        ("git 2.47.0\nlibcurl/7.59.0 OpenSSL/3.0", True),
        ("libcurl/7.59.1", True),
        ("libcurl/8.5.0 OpenSSL/3.0.13 zlib/1.3", True),
        ("libcurl/7.60", True),
        ("libcurl/7.58.0 OpenSSL/1.1.0", False),
        ("libcurl/7.29.0", False),
        ("libcurl/6.99.99", False),
        ("curl 8.5.0 (x86_64-pc-linux-gnu)", False),
        ("", False),
        ("libcurl/", False),
    ],
)
def test_libcurl_supports_multi_resolve(version_text: str, supported: bool) -> None:
    assert libcurl_supports_multi_resolve(version_text) is supported


def test_libcurl_gate_is_not_fooled_by_a_non_string() -> None:
    assert libcurl_supports_multi_resolve(None) is False
    assert libcurl_supports_multi_resolve(75900) is False


# ---------------------------------------------------------------------------
# 7. pin_address
# ---------------------------------------------------------------------------


def _classifier_stub(ip_text: str) -> str:
    """Mirrors the production contract: return the address, or raise."""
    if ip_text.startswith(("10.", "192.168.", "127.", "169.254.")):
        raise ValueError("resolved address is not globally routable")
    return ip_text


def test_pin_address_returns_every_validated_address_in_dns_order() -> None:
    resolved = ["140.82.121.4", "140.82.121.3", "2606:50c0:8000::153"]
    pinned = pin_address("github.com", lambda h, p: resolved, _classifier_stub)
    assert pinned == ("140.82.121.4", "140.82.121.3", "2606:50c0:8000::153")
    assert isinstance(pinned, tuple)
    # a dead first address must not be able to fail the whole operation, so the
    # siblings have to survive the call
    assert len(pinned) == len(resolved)


def test_pin_address_feeds_forced_git_options_directly() -> None:
    pinned = pin_address(
        "github.com", lambda h, p: ["140.82.121.4", "2606:50c0:8000::153"], _classifier_stub
    )
    rule = _resolve_rule(forced_git_options("github.com", pinned, "!broker"))
    assert rule == "http.curloptResolve=github.com:443:140.82.121.4,[2606:50c0:8000::153]"


def test_pin_address_refuses_a_split_answer_rather_than_taking_the_public_subset() -> None:
    resolved = ["140.82.121.4", "169.254.169.254", "140.82.121.3"]
    with pytest.raises(WorkspaceGitError) as caught:
        pin_address("github.com", lambda h, p: resolved, _classifier_stub)
    assert caught.value.code == "address_refused"
    # the refusal never echoes the offending address back
    assert "169.254.169.254" not in str(caught.value)


def test_pin_address_refuses_an_empty_resolution() -> None:
    with pytest.raises(WorkspaceGitError) as caught:
        pin_address("github.com", lambda h, p: [], _classifier_stub)
    assert caught.value.code == "address_refused"


def test_pin_address_refuses_when_the_resolver_fails() -> None:
    def boom(hostname: str, port: int) -> list[str]:
        raise OSError("dns is down")

    with pytest.raises(WorkspaceGitError) as caught:
        pin_address("github.com", boom, _classifier_stub)
    assert caught.value.code == "address_refused"


def test_pin_address_asks_the_resolver_for_port_443() -> None:
    seen: list[tuple[str, int]] = []

    def resolver(hostname: str, port: int) -> list[str]:
        seen.append((hostname, port))
        return ["140.82.121.4"]

    pin_address("github.com", resolver, _classifier_stub)
    assert seen == [("github.com", 443)]


def test_pin_address_defaults_are_the_production_outbound_driver_functions() -> None:
    from tinyassets.storage import outbound_connections

    assert wg._production_resolver() is outbound_connections._default_dns_resolver
    assert wg._production_classifier() is outbound_connections._classify_global_address


def test_pin_address_with_the_real_production_classifier() -> None:
    """The real classifier RAISES on refusal; pin_address must read that."""
    from tinyassets.storage import outbound_connections

    real = outbound_connections._classify_global_address
    assert pin_address("example.test", lambda h, p: ["93.184.216.34"], real) == ("93.184.216.34",)
    for private in ("10.0.0.5", "127.0.0.1", "169.254.169.254", "::1", "not-an-ip"):
        with pytest.raises(WorkspaceGitError) as caught:
            pin_address("example.test", lambda h, p: [private], real)
        assert caught.value.code == "address_refused"


# ---------------------------------------------------------------------------
# 8. run_git
# ---------------------------------------------------------------------------


def test_run_git_builds_git_options_then_argv(tmp_path: Path, empty_home: Path) -> None:
    launcher = RecordingLauncher()
    env = git_environment(empty_home, path="/usr/bin")
    run_git(
        ["clone", "--bare", "https://github.com/o/r.git", "staging"],
        cwd=tmp_path,
        env=env,
        options=["-c", "core.fsmonitor=false"],
        timeout_s=30,
        launcher=launcher,
    )
    assert launcher.last_command == [
        "git",
        "-c",
        "core.fsmonitor=false",
        "clone",
        "--bare",
        "https://github.com/o/r.git",
        "staging",
    ]


def test_run_git_never_inherits_and_never_offers_a_stdin(tmp_path: Path, empty_home: Path) -> None:
    launcher = RecordingLauncher()
    env = git_environment(empty_home, path="/usr/bin")
    run_git(["status"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher)
    kwargs = launcher.last_kwargs
    assert kwargs["env"] == dict(env)
    assert set(kwargs["env"]) == set(wg.GIT_ENVIRONMENT_KEYS)
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["timeout"] == 5.0


def test_run_git_disables_core_dumps_on_posix_only(tmp_path: Path, empty_home: Path) -> None:
    launcher = RecordingLauncher()
    env = git_environment(empty_home, path="/usr/bin")
    run_git(["status"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher)
    if IS_WINDOWS:
        assert "preexec_fn" not in launcher.last_kwargs
    else:
        assert launcher.last_kwargs["preexec_fn"] is wg._disable_core_dumps


def test_run_git_takes_an_injected_preexec(tmp_path: Path, empty_home: Path) -> None:
    launcher = RecordingLauncher()
    env = git_environment(empty_home, path="/usr/bin")
    marker: list[str] = []

    def child_setup() -> None:
        marker.append("ran")

    run_git(
        ["status"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher, preexec_fn=child_setup
    )
    assert launcher.last_kwargs["preexec_fn"] is child_setup


def test_run_git_starts_a_new_session_on_posix(
    tmp_path: Path, empty_home: Path, posix_mode: None
) -> None:
    """A new session means kill_git can signal the group, not just the pid."""
    launcher = RecordingLauncher()
    env = git_environment(empty_home, path="/usr/bin")
    run_git(["status"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher)
    assert launcher.last_kwargs["start_new_session"] is True
    assert launcher.last_kwargs["preexec_fn"] is wg._disable_core_dumps


def test_run_git_omits_posix_only_arguments_on_windows(
    tmp_path: Path, empty_home: Path, windows_mode: None
) -> None:
    """subprocess rejects both arguments there, so they must not be passed."""
    launcher = RecordingLauncher()
    env = git_environment(empty_home, path="/usr/bin")
    run_git(["status"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher)
    assert "start_new_session" not in launcher.last_kwargs
    assert "preexec_fn" not in launcher.last_kwargs


def test_run_git_refuses_a_trace_variable(tmp_path: Path, empty_home: Path) -> None:
    env = git_environment(empty_home, path="/usr/bin")
    env["GIT_TRACE_CURL"] = "1"
    with pytest.raises(WorkspaceGitError) as caught:
        run_git(["status"], cwd=tmp_path, env=env, timeout_s=5, launcher=RecordingLauncher())
    assert caught.value.code == "bad_argument"


def test_run_git_bounds_captured_output(tmp_path: Path, empty_home: Path) -> None:
    noise = b"x" * (200 * 1024) + b"TAIL"
    launcher = RecordingLauncher(FakeCompleted(returncode=1, stdout=noise, stderr=noise))
    env = git_environment(empty_home, path="/usr/bin")
    result = run_git(["status"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher)
    assert len(result.stdout_tail) == 64 * 1024
    assert len(result.stderr_scrubbed) == 64 * 1024
    assert result.stdout_tail.endswith("TAIL")
    assert result.stderr_scrubbed.endswith("TAIL")


def test_run_git_scrubs_a_token_out_of_both_streams(tmp_path: Path, empty_home: Path) -> None:
    raw = f"fatal: unable to access 'https://x-access-token:{TOKEN}@github.com/o/r.git/'".encode()
    launcher = RecordingLauncher(FakeCompleted(returncode=128, stdout=raw, stderr=raw))
    env = git_environment(empty_home, path="/usr/bin")
    with CredentialBroker("https", "github.com", "o/r", "x-access-token", TOKEN):
        result = run_git(["fetch"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher)
    assert TOKEN not in result.stderr_scrubbed
    assert TOKEN not in result.stdout_tail
    assert "[redacted]" in result.stderr_scrubbed
    assert "[redacted]" in result.stdout_tail


def test_run_git_maps_a_timeout_to_its_own_code(tmp_path: Path, empty_home: Path) -> None:
    launcher = RecordingLauncher(raises=subprocess.TimeoutExpired(cmd="git", timeout=1))
    env = git_environment(empty_home, path="/usr/bin")
    with pytest.raises(WorkspaceGitError) as caught:
        run_git(["fetch"], cwd=tmp_path, env=env, timeout_s=1, launcher=launcher)
    assert caught.value.code == "timeout"


def test_run_git_maps_a_missing_binary_to_transport(tmp_path: Path, empty_home: Path) -> None:
    launcher = RecordingLauncher(raises=FileNotFoundError("no git"))
    env = git_environment(empty_home, path="/usr/bin")
    with pytest.raises(WorkspaceGitError) as caught:
        run_git(["fetch"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher)
    assert caught.value.code == "transport"


@pytest.mark.parametrize(
    "argv,cwd_exists,timeout",
    [([], True, 5), (["status"], False, 5), (["status"], True, 0)],
)
def test_run_git_refuses_malformed_input(
    tmp_path: Path, empty_home: Path, argv: list[str], cwd_exists: bool, timeout: float
) -> None:
    env = git_environment(empty_home, path="/usr/bin")
    cwd = tmp_path if cwd_exists else tmp_path / "missing"
    with pytest.raises(WorkspaceGitError) as caught:
        run_git(argv, cwd=cwd, env=env, timeout_s=timeout, launcher=RecordingLauncher())
    assert caught.value.code == "bad_argument"


# ---------------------------------------------------------------------------
# 8b. kill_git
# ---------------------------------------------------------------------------


class FakeProc:
    """A started process that never existed -- no real signal is ever sent."""

    def __init__(self, pid: int = 4321, *, exits: bool = True, status: int = -9):
        self.pid = pid
        self.killed = False
        self.waited: list[float | None] = []
        self._exits = exits
        self._status = status

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        self.waited.append(timeout)
        if self._exits:
            return self._status
        raise subprocess.TimeoutExpired(cmd="git", timeout=timeout or 0)


@pytest.fixture()
def signal_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Intercept the real signal calls. A stray killpg would hit a real group."""
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(wg.os, "getpgid", lambda pid: pid + 1000, raising=False)
    monkeypatch.setattr(
        wg.os, "killpg", lambda pgid, sig: sent.append((pgid, sig)), raising=False
    )
    return sent


def test_kill_git_signals_the_whole_process_group(signal_spy, posix_mode: None) -> None:
    proc = FakeProc(pid=4321)
    assert kill_git(proc) == -9
    # the GROUP, not the pid: a double-forked helper must die too
    assert signal_spy == [(5321, wg._KILL_SIGNAL)]
    if not IS_WINDOWS:
        assert wg._KILL_SIGNAL is signal.SIGKILL


def test_kill_git_on_windows_can_only_reach_the_pid(signal_spy, windows_mode: None) -> None:
    proc = FakeProc(pid=4321)
    assert kill_git(proc) == -9
    assert signal_spy == []
    assert proc.killed is True


def test_kill_git_falls_back_to_the_pid_when_the_group_is_gone(
    monkeypatch: pytest.MonkeyPatch, posix_mode: None
) -> None:
    def gone(pgid: int, sig: int) -> None:
        raise ProcessLookupError("already reaped")

    monkeypatch.setattr(wg.os, "getpgid", lambda pid: pid, raising=False)
    monkeypatch.setattr(wg.os, "killpg", gone, raising=False)
    proc = FakeProc()
    assert kill_git(proc) == -9
    assert proc.killed is True


def test_kill_git_waits_with_a_bounded_timeout(signal_spy) -> None:
    proc = FakeProc()
    kill_git(proc, timeout_s=2.5)
    assert proc.waited == [2.5]


def test_kill_git_raises_when_the_process_will_not_die(signal_spy) -> None:
    proc = FakeProc(exits=False)
    with pytest.raises(WorkspaceGitError) as caught:
        kill_git(proc, timeout_s=0.1)
    assert caught.value.code == "timeout"


def test_kill_git_refuses_something_that_is_not_a_process(signal_spy) -> None:
    for candidate in (None, object(), "git"):
        with pytest.raises(WorkspaceGitError) as caught:
            kill_git(candidate)
        assert caught.value.code == "bad_argument"


# ---------------------------------------------------------------------------
# 9. stderr classification
# ---------------------------------------------------------------------------


CLASS_FIXTURES: dict[str, str] = {
    "auth": (
        "remote: Invalid username or password.\n"
        "fatal: Authentication failed for 'https://github.com/owner/repo.git/'\n"
    ),
    "not_found": (
        "remote: Repository not found.\n"
        "fatal: repository 'https://github.com/owner/repo.git/' not found\n"
    ),
    "non_fast_forward": (
        " ! [rejected]        main -> main (non-fast-forward)\n"
        "error: failed to push some refs to 'https://github.com/owner/repo.git'\n"
    ),
    "protected": (
        "remote: error: GH006: Protected branch update failed for refs/heads/main.\n"
        "remote: error: Required status check \"ci\" is expected.\n"
    ),
    "transport": (
        "fatal: unable to access 'https://github.com/owner/repo.git/': "
        "Could not resolve host: github.com\n"
    ),
    "verification": (
        "error: object file .git/objects/ab/cdef is empty\n"
        "fatal: fsck error in packed object\n"
    ),
    "other": "fatal: your local changes to the following files would be overwritten\n",
}


@pytest.mark.parametrize("expected,fixture", sorted(CLASS_FIXTURES.items()))
def test_classify_stderr(expected: str, fixture: str) -> None:
    assert classify_stderr(fixture) == expected


def test_every_declared_class_has_a_fixture() -> None:
    assert set(CLASS_FIXTURES) == set(wg.STDERR_CLASSES)


def test_classify_stderr_is_total() -> None:
    for text in ("", "   ", "something entirely unexpected"):
        assert classify_stderr(text) in wg.STDERR_CLASSES


def test_git_result_carries_the_class(tmp_path: Path, empty_home: Path) -> None:
    launcher = RecordingLauncher(
        FakeCompleted(returncode=128, stderr=CLASS_FIXTURES["auth"].encode())
    )
    env = git_environment(empty_home, path="/usr/bin")
    result = run_git(["fetch"], cwd=tmp_path, env=env, timeout_s=5, launcher=launcher)
    assert isinstance(result, GitResult)
    assert result.stderr_class == "auth"
    assert result.ok is False


# ---------------------------------------------------------------------------
# 10. bundle helpers against a real git
# ---------------------------------------------------------------------------

GIT_BINARY = shutil.which("git")
needs_git = pytest.mark.skipif(GIT_BINARY is None, reason="git is not on PATH")


def _real_env(home: Path) -> dict[str, str]:
    env = git_environment(home, path=str(Path(GIT_BINARY).parent))
    if IS_WINDOWS:
        # git.exe needs these to start at all; neither carries git config.
        for key in ("SystemRoot", "COMSPEC"):
            value = os.environ.get(key)
            if value:
                env[key] = value
    return env


@pytest.fixture()
def real_git(tmp_path: Path):
    if GIT_BINARY is None:
        pytest.skip("git is not on PATH")
    home = tmp_path / "githome"
    home.mkdir()
    env = _real_env(home)

    def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [GIT_BINARY, *argv],
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )

    repo = tmp_path / "source"
    repo.mkdir()
    run(["init", "--quiet", "."], repo)
    (repo / "README.md").write_text("workspace\n", encoding="utf-8")
    run(["add", "README.md"], repo)
    run(
        ["-c", "user.name=Tiny", "-c", "user.email=tiny@universes.tinyassets.io",
         "commit", "--quiet", "-m", "first"],
        repo,
    )
    sha = run(["rev-parse", "HEAD"], repo).stdout.strip()
    return {"env": env, "repo": repo, "sha": sha, "run": run}


@needs_git
def test_create_bundle_refuses_a_sha_that_is_not_40_hex(tmp_path: Path, real_git) -> None:
    for bad in ("HEAD", "abc", real_git["sha"].upper(), real_git["sha"] + "0"):
        with pytest.raises(WorkspaceGitError) as caught:
            create_bundle(
                real_git["repo"], bad, tmp_path / "b.bundle",
                env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
            )
        assert caught.value.code == "bad_argument"


@needs_git
def test_create_bundle_refuses_to_overwrite(tmp_path: Path, real_git) -> None:
    existing = tmp_path / "b.bundle"
    existing.write_bytes(b"old")
    with pytest.raises(WorkspaceGitError) as caught:
        create_bundle(
            real_git["repo"], real_git["sha"], existing,
            env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
        )
    assert caught.value.code == "bad_argument"
    assert existing.read_bytes() == b"old"


@needs_git
def test_create_bundle_deletes_its_temporary_ref(tmp_path: Path, real_git) -> None:
    create_bundle(
        real_git["repo"], real_git["sha"], tmp_path / "b.bundle",
        env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
    )
    listed = subprocess.run(
        [GIT_BINARY, "for-each-ref", "--format=%(refname)"],
        cwd=str(real_git["repo"]),
        env=real_git["env"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "refs/tiny/export" not in listed.stdout


@needs_git
def test_verify_bundle_returns_the_refs_it_carries(tmp_path: Path, real_git) -> None:
    bundle = tmp_path / "b.bundle"
    create_bundle(
        real_git["repo"], real_git["sha"], bundle,
        env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    refs = verify_bundle(bundle, max_bytes=10_000_000, scratch_dir=scratch, env=real_git["env"])
    assert refs == ["refs/tiny/export"]


@needs_git
def test_verify_bundle_refuses_an_oversized_bundle(tmp_path: Path, real_git) -> None:
    bundle = tmp_path / "b.bundle"
    create_bundle(
        real_git["repo"], real_git["sha"], bundle,
        env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(WorkspaceGitError) as caught:
        verify_bundle(bundle, max_bytes=16, scratch_dir=scratch, env=real_git["env"])
    assert caught.value.code == "verification"


@needs_git
def test_verify_bundle_refuses_something_that_is_not_a_regular_file(
    tmp_path: Path, real_git
) -> None:
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    for candidate in (directory, tmp_path / "missing.bundle"):
        with pytest.raises(WorkspaceGitError) as caught:
            verify_bundle(candidate, max_bytes=1000, scratch_dir=scratch, env=real_git["env"])
        assert caught.value.code == "verification"


@needs_git
def test_verify_bundle_rejects_a_file_that_is_not_a_bundle(tmp_path: Path, real_git) -> None:
    fake = tmp_path / "fake.bundle"
    fake.write_bytes(b"not a bundle at all")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(WorkspaceGitError) as caught:
        verify_bundle(fake, max_bytes=1000, scratch_dir=scratch, env=real_git["env"])
    assert caught.value.code == "verification"


@needs_git
def test_unbundle_leaves_no_remote_and_no_host_path(tmp_path: Path, real_git) -> None:
    bundle = tmp_path / "b.bundle"
    create_bundle(
        real_git["repo"], real_git["sha"], bundle,
        env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
    )
    dest = tmp_path / "workspace"
    sha = unbundle_into_fresh_repo(
        bundle, dest, ref_name="refs/tiny/export", env=real_git["env"]
    )
    assert sha == real_git["sha"]

    config_text = (dest / ".git" / "config").read_text(encoding="utf-8")
    assert "remote" not in config_text
    assert str(bundle) not in config_text
    assert bundle.resolve().as_posix() not in config_text
    assert str(real_git["repo"]) not in config_text

    remote = subprocess.run(
        [GIT_BINARY, "config", "--get", "remote.origin.url"],
        cwd=str(dest),
        env=real_git["env"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert remote.stdout.strip() == ""
    assert remote.returncode != 0


@needs_git
def test_unbundle_refuses_a_non_empty_destination(tmp_path: Path, real_git) -> None:
    bundle = tmp_path / "b.bundle"
    create_bundle(
        real_git["repo"], real_git["sha"], bundle,
        env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
    )
    dest = tmp_path / "workspace"
    dest.mkdir()
    (dest / "squatter").write_text("x", encoding="utf-8")
    with pytest.raises(WorkspaceGitError) as caught:
        unbundle_into_fresh_repo(bundle, dest, ref_name="refs/tiny/export", env=real_git["env"])
    assert caught.value.code == "bad_argument"


@needs_git
def test_unbundle_refuses_a_missing_bundle(tmp_path: Path, real_git) -> None:
    with pytest.raises(WorkspaceGitError) as caught:
        unbundle_into_fresh_repo(
            tmp_path / "missing.bundle",
            tmp_path / "workspace",
            ref_name="refs/tiny/export",
            env=real_git["env"],
        )
    assert caught.value.code == "verification"


@needs_git
def test_populate_workspace_checks_the_commit_out_on_a_local_branch(
    tmp_path: Path, real_git
) -> None:
    bundle = tmp_path / "b.bundle"
    create_bundle(
        real_git["repo"], real_git["sha"], bundle,
        env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
    )
    dest = tmp_path / "workspace"
    sha = populate_workspace_from_bundle(
        bundle, dest, "refs/tiny/export", "tiny/u-abc/slug", env=real_git["env"]
    )
    assert sha == real_git["sha"]
    assert (dest / "README.md").read_text(encoding="utf-8") == "workspace\n"
    branch = subprocess.run(
        [GIT_BINARY, "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(dest),
        env=real_git["env"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert branch.stdout.strip() == "tiny/u-abc/slug"


# ---------------------------------------------------------------------------
# 10b. bundles must be prerequisite-free
# ---------------------------------------------------------------------------

DEEP_HISTORY_COMMITS = 60  # > 50, so the bundle cannot be mistaken for shallow


@pytest.fixture(scope="module")
def deep_repo(tmp_path_factory) -> dict:
    """A repository with more than 50 commits, built once for this module."""
    if GIT_BINARY is None:
        pytest.skip("git is not on PATH")
    root = tmp_path_factory.mktemp("deep")
    home = root / "githome"
    home.mkdir()
    env = _real_env(home)
    repo = root / "source"
    repo.mkdir()

    def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [GIT_BINARY, *argv], cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120, check=True,
        )

    run(["init", "--quiet", "."], repo)
    (repo / "README.md").write_text("deep\n", encoding="utf-8")
    run(["add", "README.md"], repo)
    identity = ["-c", "user.name=Tiny", "-c", "user.email=tiny@universes.tinyassets.io"]
    run([*identity, "commit", "--quiet", "-m", "first"], repo)
    for index in range(DEEP_HISTORY_COMMITS - 1):
        run([*identity, "commit", "--quiet", "--allow-empty", "-m", f"c{index}"], repo)
    sha = run(["rev-parse", "HEAD"], repo).stdout.strip()
    parent = run(["rev-parse", "HEAD~1"], repo).stdout.strip()
    count = run(["rev-list", "--count", "HEAD"], repo).stdout.strip()
    assert count == str(DEEP_HISTORY_COMMITS), count
    return {"env": env, "repo": repo, "sha": sha, "parent": parent, "run": run, "root": root}


@needs_git
def test_a_bundle_of_a_deep_history_carries_all_of_it(tmp_path: Path, deep_repo) -> None:
    """>50 commits: the bundle must be complete, not a shallow-looking slice."""
    bundle = tmp_path / "deep.bundle"
    create_bundle(
        deep_repo["repo"], deep_repo["sha"], bundle,
        env=deep_repo["env"], scratch_dir=_fresh_scratch(tmp_path),
    )
    refs = verify_bundle(
        bundle, max_bytes=50_000_000, scratch_dir=_fresh_scratch(tmp_path), env=deep_repo["env"]
    )
    assert refs == ["refs/tiny/export"]

    dest = tmp_path / "workspace"
    sha = populate_workspace_from_bundle(
        bundle, dest, "refs/tiny/export", "tiny/u/deep", env=deep_repo["env"]
    )
    assert sha == deep_repo["sha"]
    counted = subprocess.run(
        [GIT_BINARY, "rev-list", "--count", "HEAD"],
        cwd=str(dest), env=deep_repo["env"], stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=60,
    )
    assert counted.stdout.strip() == str(DEEP_HISTORY_COMMITS)
    assert not (dest / ".git" / "shallow").exists()


@needs_git
def test_verify_bundle_refuses_a_bundle_that_needs_objects_it_lacks(
    tmp_path: Path, deep_repo
) -> None:
    """A real thin bundle: a `HEAD~1..HEAD` range records a prerequisite.

    The range has to name a ref -- a raw `<sha>..<sha>` range packages no ref
    and git refuses to create an empty bundle at all.
    """
    thin = tmp_path / "thin.bundle"
    deep_repo["run"](["bundle", "create", str(thin), "HEAD~1..HEAD"], deep_repo["repo"])
    assert thin.is_file()
    with pytest.raises(WorkspaceGitError) as caught:
        verify_bundle(
            thin, max_bytes=50_000_000, scratch_dir=_fresh_scratch(tmp_path),
            env=deep_repo["env"],
        )
    assert caught.value.code == "verification"
    assert "prerequisite" in str(caught.value)


class PrerequisiteReportingLauncher:
    """A git whose `bundle verify` reports prerequisites, and whose `bundle
    create` writes a file -- the shape create_bundle's self-check exists for."""

    def __init__(self, bundle_path: Path):
        self.bundle_path = bundle_path

    def _subcommand(self, command: list[str]) -> tuple[str, str]:
        rest = command[1:]
        while rest and (rest[0] == "-c" or rest[0] == "--no-replace-objects"):
            rest = rest[2:] if rest[0] == "-c" else rest[1:]
        return (rest[0] if rest else "", rest[1] if len(rest) > 1 else "")

    def __call__(self, command, **kwargs):
        head, tail = self._subcommand(list(command))
        if head == "bundle" and tail == "create":
            self.bundle_path.write_bytes(b"a bundle with prerequisites")
            return FakeCompleted()
        if head == "bundle" and tail == "verify":
            return FakeCompleted(
                returncode=1,
                stderr=b"error: Repository lacks these prerequisite commits:\n"
                b"error: dfa69fe97186221151839f99c0b42b5b2e6c8219 \n",
            )
        return FakeCompleted()


def test_create_bundle_refuses_and_deletes_its_own_thin_output(
    tmp_path: Path, empty_home: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = tmp_path / "out.bundle"
    with pytest.raises(WorkspaceGitError) as caught:
        create_bundle(
            repo, "0" * 40, bundle,
            env=git_environment(empty_home, path="/usr/bin"),
            scratch_dir=_fresh_scratch(tmp_path),
            launcher=PrerequisiteReportingLauncher(bundle),
        )
    assert caught.value.code == "verification"
    assert "prerequisite-free" in str(caught.value)
    # an unverifiable bundle must not be left for a caller to pick up
    assert not bundle.exists()


@needs_git
def test_create_bundle_verifies_a_good_bundle_without_complaint(
    tmp_path: Path, real_git
) -> None:
    """The self-check must not be a guard that always fires."""
    bundle = tmp_path / "b.bundle"
    returned = create_bundle(
        real_git["repo"], real_git["sha"], bundle,
        env=real_git["env"], scratch_dir=_fresh_scratch(tmp_path),
    )
    assert returned == bundle
    assert bundle.is_file()


@needs_git
def test_create_bundle_needs_an_empty_scratch_dir(tmp_path: Path, real_git) -> None:
    dirty = tmp_path / "dirty"
    dirty.mkdir()
    (dirty / "squatter").write_text("x", encoding="utf-8")
    with pytest.raises(WorkspaceGitError) as caught:
        create_bundle(
            real_git["repo"], real_git["sha"], tmp_path / "b.bundle",
            env=real_git["env"], scratch_dir=dirty,
        )
    assert caught.value.code == "bad_argument"


# The two post-population guards below never fire on a healthy git, so a real
# round trip cannot prove they work -- deleting them leaves the happy-path test
# green. A scripted launcher puts git in the state the guard exists for.


class ScriptedGitLauncher:
    """A git that reports whatever the test needs it to report."""

    def __init__(self, dest: Path, *, remote_url: str = "", config_text: str = ""):
        self.dest = dest
        self.remote_url = remote_url
        self.config_text = config_text

    def _subcommand(self, command: list[str]) -> str:
        rest = command[1:]
        while rest and rest[0] == "-c":
            rest = rest[2:]
        return rest[0] if rest else ""

    def __call__(self, command, **kwargs):
        subcommand = self._subcommand(list(command))
        if subcommand == "init":
            git_dir = self.dest / ".git"
            git_dir.mkdir(parents=True, exist_ok=True)
            (git_dir / "config").write_text(self.config_text, encoding="utf-8")
            return FakeCompleted()
        if subcommand == "rev-parse":
            return FakeCompleted(stdout=b"0" * 40 + b"\n")
        if subcommand == "config":
            return FakeCompleted(
                returncode=0 if self.remote_url else 1,
                stdout=self.remote_url.encode(),
            )
        return FakeCompleted()


def test_unbundle_refuses_a_populated_repo_that_carries_a_remote(
    tmp_path: Path, empty_home: Path
) -> None:
    bundle = tmp_path / "b.bundle"
    bundle.write_bytes(b"pretend bundle")
    dest = tmp_path / "workspace"
    launcher = ScriptedGitLauncher(dest, remote_url="https://github.com/owner/repo.git")
    with pytest.raises(WorkspaceGitError) as caught:
        unbundle_into_fresh_repo(
            bundle,
            dest,
            ref_name="refs/tiny/export",
            env=git_environment(empty_home, path="/usr/bin"),
            launcher=launcher,
        )
    assert caught.value.code == "verification"
    assert "remote" in str(caught.value)


def test_unbundle_refuses_a_populated_repo_that_records_the_bundle_path(
    tmp_path: Path, empty_home: Path
) -> None:
    bundle = tmp_path / "b.bundle"
    bundle.write_bytes(b"pretend bundle")
    dest = tmp_path / "workspace"
    launcher = ScriptedGitLauncher(
        dest, config_text=f"[core]\n\tbundleuri = {bundle}\n"
    )
    with pytest.raises(WorkspaceGitError) as caught:
        unbundle_into_fresh_repo(
            bundle,
            dest,
            ref_name="refs/tiny/export",
            env=git_environment(empty_home, path="/usr/bin"),
            launcher=launcher,
        )
    assert caught.value.code == "verification"
    assert "host path" in str(caught.value)


def test_unbundle_accepts_a_clean_population(tmp_path: Path, empty_home: Path) -> None:
    """The guards above must not fire on a repo that is actually clean."""
    bundle = tmp_path / "b.bundle"
    bundle.write_bytes(b"pretend bundle")
    dest = tmp_path / "workspace"
    launcher = ScriptedGitLauncher(dest, config_text="[core]\n\tbare = false\n")
    sha = unbundle_into_fresh_repo(
        bundle,
        dest,
        ref_name="refs/tiny/export",
        env=git_environment(empty_home, path="/usr/bin"),
        launcher=launcher,
    )
    assert sha == "0" * 40


@pytest.mark.parametrize(
    "ref",
    ["", "-evil", "refs/../evil", "refs/tiny/export.lock", "refs/tiny//export", "refs/tiny/"],
)
def test_ref_names_are_validated(tmp_path: Path, ref: str) -> None:
    with pytest.raises(WorkspaceGitError) as caught:
        wg._require_ref(ref, "test ref")
    assert caught.value.code == "bad_argument"


def test_bundle_helpers_never_touch_the_real_subprocess_by_default() -> None:
    """The launcher is injectable on every helper -- nothing hardwires run()."""
    import inspect

    for function in (create_bundle, verify_bundle, unbundle_into_fresh_repo,
                     populate_workspace_from_bundle, run_git):
        parameters = inspect.signature(function).parameters
        assert "launcher" in parameters
        assert parameters["launcher"].default is subprocess.run
        assert "env" in parameters


def test_python_is_recent_enough_for_the_typing_used() -> None:
    assert sys.version_info >= (3, 11)
