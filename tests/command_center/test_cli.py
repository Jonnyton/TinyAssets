"""Fail-closed CLI and checked-in browser bootstrap contracts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import command_center
import command_center.__main__ as entrypoint
import command_center.server as server
from command_center.collector import Config

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
VALID_ENV_TOKEN = "village_token_0123456789abcdef"


def _capture_cli_config(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> Config:
    captured: list[Config] = []
    monkeypatch.setattr(entrypoint, "serve", captured.append)
    entrypoint.main(argv)
    assert len(captured) == 1
    return captured[0]


def _app_source() -> str:
    return (
        Path(command_center.__file__).with_name("web") / "app.js"
    ).read_text(encoding="utf-8")


def _source_between(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def test_config_and_cli_default_to_literal_ipv4_loopback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TINYASSETS_VILLAGE_TOKEN", raising=False)

    assert Config(root=tmp_path).host == "127.0.0.1"
    cfg = _capture_cli_config(monkeypatch, [])

    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8787


def test_bare_cli_generates_a_fresh_bounded_url_safe_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TINYASSETS_VILLAGE_TOKEN", raising=False)

    first = _capture_cli_config(monkeypatch, []).token
    second = _capture_cli_config(monkeypatch, []).token

    assert isinstance(first, str)
    assert isinstance(second, str)
    assert TOKEN_RE.fullmatch(first)
    assert TOKEN_RE.fullmatch(second)
    assert first != second


def test_cli_uses_environment_village_and_mcp_tokens(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TINYASSETS_VILLAGE_TOKEN", VALID_ENV_TOKEN)
    monkeypatch.setenv("WORKFLOW_MCP_TOKEN", "platform-bearer-from-environment")

    cfg = _capture_cli_config(monkeypatch, [])

    assert cfg.token == VALID_ENV_TOKEN
    assert cfg.mcp_token == "platform-bearer-from-environment"


@pytest.mark.parametrize("flag", ["--token", "--mcp-token"])
def test_cli_rejects_secret_valued_arguments_before_serve(
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
) -> None:
    called = False

    def unexpected_serve(_cfg: Config) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(entrypoint, "serve", unexpected_serve)

    with pytest.raises(SystemExit) as exc_info:
        entrypoint.main([flag, VALID_ENV_TOKEN])

    assert exc_info.value.code == 2
    assert called is False


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("port", [0, 1, 65535])
def test_cli_accepts_only_supported_loopback_and_port_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    host: str,
    port: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TINYASSETS_VILLAGE_TOKEN", VALID_ENV_TOKEN)

    cfg = _capture_cli_config(
        monkeypatch,
        ["--host", host, "--port", str(port)],
    )

    assert cfg.host == host
    assert cfg.port == port


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("--host", ""),
        ("--host", "0.0.0.0"),
        ("--host", "localhost"),
        ("--host", "192.168.1.25"),
        ("--host", "127.0.0.2"),
        ("--port", "-1"),
        ("--port", "65536"),
    ],
)
def test_invalid_listener_configuration_fails_before_serve(
    monkeypatch: pytest.MonkeyPatch,
    argument: str,
    value: str,
) -> None:
    called = False

    def unexpected_serve(_cfg: Config) -> None:
        nonlocal called
        called = True

    monkeypatch.setenv("TINYASSETS_VILLAGE_TOKEN", VALID_ENV_TOKEN)
    monkeypatch.setattr(entrypoint, "serve", unexpected_serve)

    with pytest.raises(SystemExit) as exc_info:
        entrypoint.main([argument, value])

    assert exc_info.value.code == 2
    assert called is False


@pytest.mark.parametrize(
    "token",
    [
        "",
        "a" * 19,
        "a" * 129,
        "contains a space but is long",
        "not.url.safe.but.long-enough",
        "unicode-token-\N{SNOWMAN}-long-enough",
    ],
)
def test_invalid_environment_token_fails_before_serve(
    monkeypatch: pytest.MonkeyPatch,
    token: str,
) -> None:
    called = False

    def unexpected_serve(_cfg: Config) -> None:
        nonlocal called
        called = True

    monkeypatch.setenv("TINYASSETS_VILLAGE_TOKEN", token)
    monkeypatch.setattr(entrypoint, "serve", unexpected_serve)

    with pytest.raises(SystemExit) as exc_info:
        entrypoint.main([])

    assert exc_info.value.code == 2
    assert called is False


@pytest.mark.parametrize(
    ("host", "server_address", "expected"),
    [
        (
            "127.0.0.1",
            ("127.0.0.1", 43123),
            f"http://127.0.0.1:43123/#token={VALID_ENV_TOKEN}",
        ),
        (
            "::1",
            ("::1", 43124, 0, 0),
            f"http://[::1]:43124/#token={VALID_ENV_TOKEN}",
        ),
    ],
)
def test_serve_prints_fragment_url_with_actual_bound_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    host: str,
    server_address: tuple[object, ...],
    expected: str,
) -> None:
    cache_events: list[str] = []

    class FakeCache:
        def __init__(self, _cfg: Config) -> None:
            cache_events.append("constructed")

        def start(self) -> None:
            cache_events.append("started")

        def stop(self) -> None:
            cache_events.append("stopped")

    class FakeServer:
        def __init__(self, address: tuple[str, int], _handler: object) -> None:
            assert address == (host, 0)
            self.server_address = server_address

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            cache_events.append("closed")

    monkeypatch.setattr(server, "StateCache", FakeCache)
    monkeypatch.setattr(server, "ThreadingHTTPServer", FakeServer)
    cfg = Config(
        root=tmp_path,
        host=host,
        port=0,
        token=VALID_ENV_TOKEN,
        directory_url=None,
    )

    server.serve(cfg)

    output = capsys.readouterr().out
    assert expected in output
    assert "?token=" not in output
    assert f":0/#token={VALID_ENV_TOKEN}" not in output
    assert cache_events == ["constructed", "started", "stopped", "closed"]


def test_browser_bootstrap_uses_fragment_and_tab_scoped_storage() -> None:
    source = _app_source()
    bootstrap = source[: source.index("const PROVIDERS")]

    assert re.search(r"\.hash\b", bootstrap)
    assert re.search(r"\.get\([\"']token[\"']\)", bootstrap)
    assert "sessionStorage.getItem" in bootstrap
    assert "sessionStorage.setItem" in bootstrap
    assert "history.replaceState" in bootstrap
    assert "localStorage" not in source
    assert bootstrap.index("history.replaceState") < source.index(
        'document.addEventListener("DOMContentLoaded"'
    )


def test_browser_synchronously_scrubs_legacy_query_without_promotion() -> None:
    source = _app_source()
    bootstrap = source[: source.index("const PROVIDERS")]

    assert re.search(
        r"(?:searchParams|queryParams|params)\.delete\([\"']token[\"']\)",
        bootstrap,
    )
    assert not re.search(r"(?:params|searchParams)\.get\([\"']token[\"']\)", source)


def test_browser_api_uses_header_only_authentication() -> None:
    source = _app_source()
    api_source = _source_between(source, "function api(", "\nfunction toast")

    assert "X-Village-Token" in api_source
    assert "fetch(" in api_source
    assert "token=" not in api_source
    assert "URLSearchParams" not in api_source
    assert "encodeURIComponent(TOKEN)" not in api_source


def test_browser_share_reconstructs_a_fragment_token_url() -> None:
    source = _app_source()
    share_source = _source_between(
        source,
        '$("btn-share").addEventListener',
        "  // replay",
    )

    assert re.search(r"(?:\.hash\s*=|#token=)", share_source)
    assert "token" in share_source
    assert "TOKEN" in share_source
    assert "navigator.clipboard" in share_source
    assert "writeText(location.href)" not in share_source
    assert "?token=" not in share_source


def test_cli_help_describes_secure_loopback_without_secret_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        entrypoint.main(["--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "127.0.0.1" in help_text
    assert "--token" not in help_text
    assert "--mcp-token" not in help_text
    assert "phone" not in help_text.lower()
