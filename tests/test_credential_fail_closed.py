"""Credential subprocesses launch only from assigned snapshots."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tinyassets.exceptions import ProviderUnavailableError
from tinyassets.providers.base import subprocess_env_for_provider


@pytest.fixture
def host_credentials(monkeypatch):
    monkeypatch.setenv("CODEX_HOME", "C:/host/codex")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "C:/host/claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "host-oauth")
    monkeypatch.setenv("OPENAI_API_KEY", "host-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "host-anthropic")
    monkeypatch.setenv("FUTURE_PROVIDER_MASTER_TOKEN", "host-future")


@pytest.mark.parametrize("provider", ("codex", "claude-code"))
def test_missing_snapshot_never_inherits_host_or_environment_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host_credentials,
    provider: str,
) -> None:
    universe = tmp_path / "universe"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(universe))
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")

    with pytest.raises(
        ProviderUnavailableError,
        match="assigned credential snapshot",
    ):
        subprocess_env_for_provider(provider, universe_dir=universe)
    with pytest.raises(
        ProviderUnavailableError,
        match="assigned credential snapshot",
    ):
        subprocess_env_for_provider(provider, universe_dir=None)


def test_codex_snapshot_is_exact_and_host_secret_free(
    tmp_path: Path,
    host_credentials,
) -> None:
    universe = tmp_path / "universe"
    snapshot = universe / ".credentials" / "launch" / "codex"
    snapshot.mkdir(parents=True)
    (snapshot / "auth.json").write_text('{"tokens":{"access_token":"assigned"}}')

    env = subprocess_env_for_provider(
        "codex",
        universe_dir=universe,
        credential_snapshot_dir=snapshot,
    )

    assert env["CODEX_HOME"] == str(snapshot.resolve())
    assert env["HOME"].startswith(str(universe.resolve()))
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "FUTURE_PROVIDER_MASTER_TOKEN" not in env


def test_claude_snapshot_uses_only_snapshot_token(
    tmp_path: Path,
    host_credentials,
) -> None:
    universe = tmp_path / "universe"
    snapshot = universe / ".credentials" / "launch" / "claude"
    snapshot.mkdir(parents=True)
    (snapshot / ".oauth-token").write_text("assigned-oauth", encoding="utf-8")

    env = subprocess_env_for_provider(
        "claude-code",
        universe_dir=universe,
        credential_snapshot_dir=snapshot,
    )

    assert env["CLAUDE_CONFIG_DIR"] == str(snapshot.resolve())
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "assigned-oauth"
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] != os.environ["CLAUDE_CODE_OAUTH_TOKEN"]
    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env


def test_snapshot_must_be_a_real_directory_inside_universe(tmp_path: Path) -> None:
    universe = tmp_path / "universe"
    universe.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ProviderUnavailableError, match="credential resolution"):
        subprocess_env_for_provider(
            "codex",
            universe_dir=universe,
            credential_snapshot_dir=outside,
        )
    with pytest.raises(ProviderUnavailableError, match="credential resolution"):
        subprocess_env_for_provider(
            "codex",
            universe_dir=universe,
            credential_snapshot_dir=universe / "missing",
        )


def test_snapshot_symlink_is_rejected(tmp_path: Path) -> None:
    universe = tmp_path / "universe"
    target = universe / "target"
    target.mkdir(parents=True)
    link = universe / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")

    with pytest.raises(ProviderUnavailableError, match="credential resolution"):
        subprocess_env_for_provider(
            "codex",
            universe_dir=universe,
            credential_snapshot_dir=link,
        )


@pytest.mark.parametrize("provider", ("future-cli", "gemini", "CODEX"))
def test_noncanonical_cli_provider_cannot_use_snapshot(
    tmp_path: Path,
    provider: str,
) -> None:
    universe = tmp_path / "universe"
    snapshot = universe / "snapshot"
    snapshot.mkdir(parents=True)

    with pytest.raises(ProviderUnavailableError, match="credential resolution"):
        subprocess_env_for_provider(
            provider,
            universe_dir=universe,
            credential_snapshot_dir=snapshot,
        )


def test_malformed_claude_token_is_sanitized(tmp_path: Path) -> None:
    universe = tmp_path / "universe"
    snapshot = universe / "snapshot"
    snapshot.mkdir(parents=True)
    (snapshot / ".oauth-token").write_text("", encoding="utf-8")

    with pytest.raises(ProviderUnavailableError, match="credential resolution") as caught:
        subprocess_env_for_provider(
            "claude-code",
            universe_dir=universe,
            credential_snapshot_dir=snapshot,
        )

    assert str(snapshot) not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
