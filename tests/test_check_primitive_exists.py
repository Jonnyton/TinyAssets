"""Tests for scripts/check_primitive_exists.py — pre-design cohit guard.

Each subcommand (action / bug / sha) is exercised against a temp git repo
that simulates origin/main. The repo holds a tiny api file with a known
action verb and a few seed commits so we can assert CLEAN / WARNING /
COLLISION outcomes without depending on the real workflow tree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import check_primitive_exists as cpe  # noqa: E402

# ── Fixture: a fake repo with origin/main ────────────────────────────────────


def _git(repo: Path, *args: str, env_extra: dict | None = None) -> None:
    env = {
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    if env_extra:
        env.update(env_extra)
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, env=env,
    )


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Fresh git repo with a `refs/remotes/origin/main` ref pointing at HEAD.

    Layout:
      workflow/api/branches.py       — fake action-map file containing a
                                       `validate_branch` map entry to
                                       simulate the dev-cohit-#2 case.
      docs/notes/bug042-mention.md   — file mentions BUG-042 by id.

    Commit history:
      [BUG-038 cited]  fix: handle BUG-038 cooldown drift
      [BUG-040 keyword] fix: tighten branch validation        (no BUG- in subject)
      [seed]           initial layout
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")

    api_dir = repo / "workflow" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "branches.py").write_text(
        '"""fake api file."""\n'
        "_ACTIONS = {\n"
        '    "validate_branch": _ext_branch_validate,\n'
        '    "build_branch": _ext_branch_build,\n'
        "}\n"
        "def _ext_branch_validate(): pass\n",
        encoding="utf-8",
    )
    notes = repo / "docs" / "notes"
    notes.mkdir(parents=True)
    (notes / "bug042-mention.md").write_text(
        "Note about BUG-042 — filed but no fix yet.\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "initial layout")

    # Add a commit referencing BUG-038 in subject (direct-id hit case).
    (repo / "workflow" / "api" / "branches.py").write_text(
        '"""fake api file v2."""\n'
        "_ACTIONS = {\n"
        '    "validate_branch": _ext_branch_validate,\n'
        '    "build_branch": _ext_branch_build,\n'
        "}\n"
        "def _ext_branch_validate(): pass\n"
        "# tweak\n",
        encoding="utf-8",
    )
    _git(repo, "commit", "-aq", "-m", "fix: handle BUG-038 cooldown drift")

    # Add a commit that fixes a bug WITHOUT naming the id in subject —
    # simulates the BUG-037 case (a288444 didn't say "BUG-037" in subject).
    (repo / "workflow" / "api" / "branches.py").write_text(
        '"""fake api file v3."""\n'
        "_ACTIONS = {\n"
        '    "validate_branch": _ext_branch_validate,\n'
        '    "build_branch": _ext_branch_build,\n'
        "}\n"
        "def _ext_branch_validate(): pass\n"
        "# tweak v3\n",
        encoding="utf-8",
    )
    _git(repo, "commit", "-aq", "-m", "fix: tighten branch validation")

    # Set up the origin/main ref the script expects.
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


# ── action subcommand ────────────────────────────────────────────────────────


def test_action_collision_on_known_verb(fake_repo: Path, capsys):
    rc = cpe.check_action("validate_branch", repo_root=fake_repo)
    out = capsys.readouterr().out
    assert rc == cpe.EXIT_COLLISION, out
    assert "COLLISION" in out
    assert "validate_branch" in out
    # Both shapes (handler + map_entry) get reported.
    assert "map_entry" in out
    assert "handler" in out


def test_action_clean_on_unknown_verb(fake_repo: Path, capsys):
    rc = cpe.check_action("zzznopenope", repo_root=fake_repo)
    out = capsys.readouterr().out
    assert rc == cpe.EXIT_CLEAN, out
    assert "CLEAN" in out


def test_action_rejects_bad_identifier(fake_repo: Path, capsys):
    rc = cpe.check_action("Has-Hyphens-And-Caps", repo_root=fake_repo)
    err = capsys.readouterr().err
    assert rc == cpe.EXIT_COLLISION, err
    assert "not a valid identifier" in err


# ── bug subcommand ───────────────────────────────────────────────────────────


def test_bug_collision_when_id_in_commit_subject(fake_repo: Path, capsys):
    """BUG-038 IS named in a commit subject — direct hit."""
    rc = cpe.check_bug("BUG-038", repo_root=fake_repo)
    out = capsys.readouterr().out
    assert rc == cpe.EXIT_COLLISION, out
    assert "COLLISION" in out
    assert "BUG-038" in out
    assert "cooldown drift" in out


def test_bug_warning_when_only_file_mentions_match(fake_repo: Path, capsys):
    """BUG-042 is mentioned in a doc file but no commit subject — warning tier
    matches the BUG-037 real-world case (fix sha a288444 didn't say BUG-037
    in its subject)."""
    rc = cpe.check_bug("BUG-042", repo_root=fake_repo)
    out = capsys.readouterr().out
    assert rc == cpe.EXIT_WARNING, out
    assert "WARNING" in out
    assert "BUG-042" in out
    assert "bug042-mention.md" in out


def test_bug_clean_on_unknown_id(fake_repo: Path, capsys):
    rc = cpe.check_bug("BUG-9999", repo_root=fake_repo)
    out = capsys.readouterr().out
    assert rc == cpe.EXIT_CLEAN, out
    assert "CLEAN" in out


def test_bug_rejects_malformed_id(fake_repo: Path, capsys):
    rc = cpe.check_bug("not-a-bug", repo_root=fake_repo)
    err = capsys.readouterr().err
    assert rc == cpe.EXIT_COLLISION, err
    assert "valid BUG-NNN" in err


def test_bug_id_normalized_with_zero_pad(fake_repo: Path, capsys):
    """`BUG-38` should normalize to `BUG-038` when matching commit subjects."""
    # Our fixture has 'fix: handle BUG-038 cooldown drift'. A query for BUG-38
    # (no zero pad) should still hit because we canonicalize before the grep.
    rc = cpe.check_bug("BUG-38", repo_root=fake_repo)
    out = capsys.readouterr().out
    # Direct grep is case-insensitive substring; "BUG-38" is a substring of
    # "BUG-038" so the grep WILL match — collision is the right verdict.
    assert rc == cpe.EXIT_COLLISION, out


# ── sha subcommand ───────────────────────────────────────────────────────────


def test_sha_clean_on_main_ancestor(fake_repo: Path, capsys):
    head = subprocess.run(
        ["git", "-C", str(fake_repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    rc = cpe.check_sha(head[:8], repo_root=fake_repo)
    out = capsys.readouterr().out
    assert rc == cpe.EXIT_CLEAN, out
    assert "CLEAN" in out
    assert "tighten branch validation" in out


def test_sha_collision_when_unresolvable(fake_repo: Path, capsys):
    rc = cpe.check_sha("deadbeef", repo_root=fake_repo)
    out = capsys.readouterr().out
    assert rc == cpe.EXIT_COLLISION, out
    assert "does not resolve" in out


def test_sha_collision_when_off_main(fake_repo: Path, capsys):
    """A commit on a feature branch that's NOT an ancestor of origin/main
    must report COLLISION — the daemon_registry doc-frontmatter cohit case."""
    # Make a feature branch, commit something there, do NOT merge it into main,
    # do NOT update origin/main ref.
    _git(fake_repo, "checkout", "-q", "-b", "feature/off-main")
    (fake_repo / "feature.txt").write_text("only on feature\n", encoding="utf-8")
    _git(fake_repo, "add", "feature.txt")
    _git(fake_repo, "commit", "-q", "-m", "feat: orphan commit")
    feature_sha = subprocess.run(
        ["git", "-C", str(fake_repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    _git(fake_repo, "checkout", "-q", "main")

    rc = cpe.check_sha(feature_sha[:10], repo_root=fake_repo)
    out = capsys.readouterr().out
    assert rc == cpe.EXIT_COLLISION, out
    assert "NOT on" in out
    assert "feature/off-main" in out


def test_sha_rejects_non_hex(fake_repo: Path, capsys):
    rc = cpe.check_sha("zzznotahex!", repo_root=fake_repo)
    err = capsys.readouterr().err
    assert rc == cpe.EXIT_COLLISION, err
    assert "does not look like a git sha" in err


# ── CLI entry point smoke ────────────────────────────────────────────────────


def test_cli_main_dispatches_action(monkeypatch, fake_repo: Path, capsys):
    monkeypatch.setattr(cpe, "REPO_ROOT", fake_repo)
    rc = cpe.main(["action", "zzznopenope"])
    assert rc == cpe.EXIT_CLEAN
    assert "CLEAN" in capsys.readouterr().out


def test_cli_main_dispatches_bug(monkeypatch, fake_repo: Path, capsys):
    monkeypatch.setattr(cpe, "REPO_ROOT", fake_repo)
    rc = cpe.main(["bug", "BUG-038"])
    assert rc == cpe.EXIT_COLLISION
    assert "COLLISION" in capsys.readouterr().out


def test_cli_main_requires_subcommand(capsys):
    with pytest.raises(SystemExit):
        cpe.main([])
