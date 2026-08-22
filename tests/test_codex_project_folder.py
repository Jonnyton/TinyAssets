"""The served converse turn mounts the universe as a read/WRITE project folder
(its brain) but exposes ONLY the markdown docs — never the credential vault,
auth snapshots, private config, state DBs, or any subdirectory.

Live 2026-08-22: the founder asked for the universe to work like a customizable
harness + project folder the agent reads and evolves. Isolation is at the
universe boundary (OS sandbox + per-universe credentials), so within a universe
the agent may freely read/write its brain — but system state must stay masked.
"""

from __future__ import annotations

import pytest

from tinyassets.providers.codex_provider import (
    _project_folder_mounts,
    _secret_mask_args,
)


def _mk_universe(tmp_path):
    u = tmp_path / "u-owner"
    u.mkdir()
    # Brain docs (must be exposed rw, in place).
    (u / "identity.md").write_text("name: tiny", encoding="utf-8")
    (u / "soul.edit.md").write_text("soul", encoding="utf-8")
    # System state (must be masked).
    (u / ".credential-vault.json").write_text('{"secret":"x"}', encoding="utf-8")
    (u / "config.yaml").write_text("secret: y", encoding="utf-8")
    (u / "checkpoints.db").write_text("db", encoding="utf-8")
    (u / ".soul.lock").write_text("", encoding="utf-8")
    (u / ".credentials").mkdir()
    (u / ".credentials" / "codex").mkdir()
    (u / "wiki").mkdir()
    return u


def _pairs(args):
    return list(zip(args, args[1:]))


def _triples(args):
    return list(zip(args, args[1:], args[2:]))


def test_project_folder_binds_rw_and_exposes_only_markdown(tmp_path):
    u = _mk_universe(tmp_path)
    args = _project_folder_mounts(u)
    # The universe is bound READ-WRITE (edits persist) — not ro-bind, not tmpfs.
    assert ("--bind", str(u), "/workspace") in _triples(args)
    assert ("--ro-bind", str(u), "/workspace") not in _triples(args)
    # Brain docs are NOT masked (left visible in the rw bind).
    assert "/workspace/identity.md" not in args
    assert "/workspace/soul.edit.md" not in args


def test_project_folder_masks_all_system_state(tmp_path):
    u = _mk_universe(tmp_path)
    args = _project_folder_mounts(u)
    pairs = _pairs(args)
    triples = _triples(args)
    # Secret FILES blinded with /dev/null.
    for name in (".credential-vault.json", "config.yaml", "checkpoints.db", ".soul.lock"):
        assert ("--ro-bind", "/dev/null", f"/workspace/{name}") in triples, name
    # Secret/opaque DIRECTORIES overlaid with an empty tmpfs.
    for name in (".credentials", "wiki"):
        assert ("--tmpfs", f"/workspace/{name}") in pairs, name


def test_symlink_named_like_a_doc_is_masked_not_followed(tmp_path):
    """A crafted `evil.md` symlink to the vault must be masked, never exposed."""
    u = _mk_universe(tmp_path)
    link = u / "evil.md"
    try:
        link.symlink_to(u / ".credential-vault.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform/user")
    args = _project_folder_mounts(u)
    # It is masked (blinded), NOT left exposed as a readable brain doc.
    assert ("--ro-bind", "/dev/null", "/workspace/evil.md") in _triples(args)


def test_secret_mask_args_targets_the_known_secrets(tmp_path):
    u = _mk_universe(tmp_path)
    args = _secret_mask_args(u)
    triples = _triples(args)
    pairs = _pairs(args)
    assert ("--ro-bind", "/dev/null", "/workspace/.credential-vault.json") in triples
    assert ("--ro-bind", "/dev/null", "/workspace/config.yaml") in triples
    assert ("--tmpfs", "/workspace/.credentials") in pairs
    # It does NOT touch brain docs.
    assert "/workspace/identity.md" not in args
