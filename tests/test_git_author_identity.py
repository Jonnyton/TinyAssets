"""Phase 7.4 v1 — git author identity resolution.

Covers the narrow v1 contract in :mod:`workflow.identity`:

- ``WORKFLOW_GIT_AUTHOR`` env var overrides everything (verbatim).
- Otherwise ``actor`` arg or ``UNIVERSE_SERVER_USER`` → slugged
  ``Workflow User <slug@users.noreply.workflow.local>``.
- Empty/None/invalid slug → ``anonymous``.

Also pins the ``git_bridge.commit(author=None)`` default so the
composite helpers can omit the argument and let identity resolve.
"""

from __future__ import annotations

import pytest

from workflow.identity import git_author

_DOMAIN = "users.noreply.workflow.local"
_DISPLAY = "Workflow User"


@pytest.fixture(autouse=True)
def _clean_identity_env(monkeypatch: pytest.MonkeyPatch):
    """Every test starts without Workflow identity env vars set."""
    monkeypatch.delenv("WORKFLOW_GIT_AUTHOR", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_USER", raising=False)
    yield


def test_no_env_no_actor_falls_back_to_anonymous():
    assert git_author() == f"{_DISPLAY} <anonymous@{_DOMAIN}>"


def test_universe_server_user_env_slugs_into_composite(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    assert git_author() == f"{_DISPLAY} <alice@{_DOMAIN}>"


def test_spaces_and_caps_are_slugified(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "Alice Smith")
    assert git_author() == f"{_DISPLAY} <alice-smith@{_DOMAIN}>"


def test_special_chars_stripped_by_slug(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "  User@#$Name  ")
    assert git_author() == f"{_DISPLAY} <user-name@{_DOMAIN}>"


def test_workflow_git_author_env_is_verbatim(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GIT_AUTHOR", "Alice Real <alice@example.com>",
    )
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "would-be-ignored")
    assert git_author() == "Alice Real <alice@example.com>"


def test_workflow_git_author_env_strips_surrounding_whitespace(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GIT_AUTHOR", "  Bob <b@x.io>  ",
    )
    assert git_author() == "Bob <b@x.io>"


def test_workflow_git_author_blank_falls_through_to_composite(monkeypatch):
    monkeypatch.setenv("WORKFLOW_GIT_AUTHOR", "   ")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "charlie")
    assert git_author() == f"{_DISPLAY} <charlie@{_DOMAIN}>"


def test_actor_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "env-user")
    assert git_author(actor="bob") == f"{_DISPLAY} <bob@{_DOMAIN}>"


def test_actor_empty_string_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "env-user")
    # Empty actor is treated as "no actor provided", not as
    # "explicitly anonymous" — env still wins.
    assert git_author(actor="") == f"{_DISPLAY} <env-user@{_DOMAIN}>"


def test_actor_none_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "env-user")
    assert git_author(actor=None) == f"{_DISPLAY} <env-user@{_DOMAIN}>"


def test_actor_whitespace_only_falls_back_to_anonymous():
    # No env set; actor is pure whitespace — slug of empty → anonymous.
    assert git_author(actor="   ") == f"{_DISPLAY} <anonymous@{_DOMAIN}>"


# ─── git_bridge.commit default author wiring ──────────────────────────────


def test_git_bridge_commit_resolves_default_author(monkeypatch, tmp_path):
    """Calling commit() without ``author`` routes through git_author()."""
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git not available")

    from workflow import git_bridge

    git_bridge.invalidate_cache()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main"], cwd=str(repo),
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "ci@example.invalid"], cwd=str(repo),
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI Bot"], cwd=str(repo),
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=str(repo),
        check=True, capture_output=True,
    )
    (repo / "seed.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "seed.txt"], cwd=str(repo),
        check=True, capture_output=True,
    )

    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.delenv("WORKFLOW_GIT_AUTHOR", raising=False)

    # No author argument — default identity should be used
    result = git_bridge.commit("seed commit", repo_path=repo)
    assert result.ok, result.error

    logged = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>"], cwd=str(repo),
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert logged == f"{_DISPLAY} <alice@{_DOMAIN}>"
    git_bridge.invalidate_cache()
