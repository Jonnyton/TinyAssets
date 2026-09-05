"""Codex CLI compatibility must preserve confinement and terminal evidence."""
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tinyassets.exceptions import ProviderError
from tinyassets.providers.base import ModelConfig
from tinyassets.providers.codex_provider import _structured_failure_excerpt


def _event(kind, **fields):
    return (json.dumps({"type": kind, **fields}) + "\n").encode()


def test_terminal_json_reason_wins_over_tracing_and_transient_errors():
    output = (
        _event("error", message="transient reconnect")
        + _event("turn.failed", error={"message": "first line\nmodel unavailable"})
        + _event("error", message="teardown noise")
    )
    assert _structured_failure_excerpt(output, "catalogue " + "x" * 5000, machine=True) == (
        "first line model unavailable"
    )


@pytest.mark.parametrize("raw", [b"", b"not json\n[]\n", _event("turn.failed", error=42)])
def test_unusable_json_falls_back_to_scrubbed_stderr(raw):
    assert _structured_failure_excerpt(raw, "model unavailable", machine=True) == (
        "model unavailable"
    )


def test_last_error_event_is_kept_without_a_turn_failed_event():
    raw = _event("error", message="first") + _event("error", message="last")
    assert _structured_failure_excerpt(raw, "noise", machine=True) == "last"
    assert _structured_failure_excerpt(raw, "plain stderr", machine=False) == "plain stderr"


def test_entire_json_message_is_scrubbed_before_clipping():
    secret = "sk-" + "Sensitive" * 25
    message = "start " + "x" * 105 + secret + "y" * 400 + " terminal cause"
    result = _structured_failure_excerpt(_event("error", message=message), "", machine=True)
    assert len(result) <= 240
    assert "Sensitive" not in result and "sk-" not in result
    assert result.startswith("start ") and result.endswith("terminal cause")


@pytest.mark.asyncio
@pytest.mark.parametrize("returncode", [1, 2])
async def test_real_provider_nonzero_paths_keep_json_reason_and_confinement(
    monkeypatch, tmp_path, returncode,
):
    from tinyassets.providers import codex_provider as provider

    auth_dir = tmp_path / "auth"
    auth_dir.mkdir()
    proc = AsyncMock()
    proc.returncode = returncode
    launch = AsyncMock(return_value=proc)
    monkeypatch.setattr(provider, "_resolve_codex_cmd", lambda: (["codex"], False))
    monkeypatch.setattr(provider, "get_sandbox_status", lambda: {
        "bwrap_available": True, "bwrap_path": "fake-bwrap",
    })
    monkeypatch.setattr(provider, "subprocess_env_for_provider", lambda *a, **kw: {
        "CODEX_HOME": str(auth_dir),
    })
    monkeypatch.setattr(provider, "_codex_sandbox_mounts", lambda command: [])
    monkeypatch.setattr(provider, "_codex_home_file_mounts", lambda path: [])
    monkeypatch.setattr(provider.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(provider, "_stream_codex_exec", AsyncMock(return_value=(
        _event("turn.failed", error={"message": "model rejected sk-secretsensitive123"}),
        b"tracing catalogue " + b"x" * 5000,
    )))
    with pytest.raises(ProviderError) as failure:
        await provider.CodexProvider().complete(
            "prompt", "system", ModelConfig(sandbox_workspace=True), universe_dir=tmp_path,
        )
    assert "model rejected [redacted]" in str(failure.value)
    assert "secretsensitive" not in str(failure.value)
    args = launch.call_args.args
    inner = args[args.index("--") + 1:]
    pairs = list(zip(inner, inner[1:]))
    assert ("--sandbox", "workspace-write") in pairs
    assert "--full-auto" not in inner
    assert "--dangerously-bypass-approvals-and-sandbox" not in inner
    for name in ("shell_tool", "apps", "plugins", "remote_plugin"):
        assert ("--disable", name) in pairs
    assert "--ignore-user-config" in inner and "--ignore-rules" in inner


def test_image_pin_and_keepalive_use_catalogue_compatible_launch():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    version = re.search(r"ARG CODEX_CLI_VERSION=(\d+)\.(\d+)\.(\d+)", dockerfile)
    assert version and tuple(map(int, version.groups())) >= (0, 146, 0)
    assert "python /tmp/codex_cli_smoke.py" in dockerfile
    keepalive = (root / ".github/workflows/codex-auth-keepalive.yml").read_text()
    assert "--full-auto" not in keepalive
    assert "codex exec --sandbox workspace-write" in keepalive
    for name in ("apps", "plugins", "remote_plugin"):
        assert f"--disable {name}" in keepalive
