"""The served founder converse turn mounts the universe as a FULLY-OPEN
read/WRITE project folder (its customizable harness + brain): the agent may
read, edit, and create files of ANY type there, and the only things masked are
the well-known credential paths — the deposited-LLM vault, the auth snapshots,
and the private config.

Live 2026-08-22: the founder asked for the universe to work like a customizable
harness + project folder the agent (and user) fully control — able to model the
agent off any harness (Hermes, OpenClaw, Codex, Kimi plugins) or a blend,
starting from the seed. Isolation is at the universe boundary (OS sandbox +
per-universe credentials), so within a universe the agent has full access; only
credentials are held back (and are being relocated OUT of the universe entirely).
"""

from __future__ import annotations

from tinyassets.providers.codex_provider import (
    _project_folder_mounts,
    _secret_mask_args,
)


def _mk_universe(tmp_path):
    u = tmp_path / "u-owner"
    u.mkdir()
    # Brain / harness content — all agent-accessible (any file type).
    (u / "identity.md").write_text("name: tiny", encoding="utf-8")
    (u / "soul.edit.md").write_text("soul", encoding="utf-8")
    (u / "checkpoints.db").write_text("db", encoding="utf-8")  # NOT a credential
    (u / "hooks.py").write_text("# a harness the founder builds", encoding="utf-8")
    # Credentials — the ONLY things masked.
    (u / ".credential-vault.json").write_text('{"secret":"x"}', encoding="utf-8")
    (u / "config.yaml").write_text("secret: y", encoding="utf-8")
    (u / ".credentials").mkdir()
    (u / ".credentials" / "codex").mkdir()
    return u


def _pairs(args):
    return list(zip(args, args[1:]))


def _triples(args):
    return list(zip(args, args[1:], args[2:]))


def test_universe_is_bound_read_write(tmp_path):
    u = _mk_universe(tmp_path)
    args = _project_folder_mounts(u)
    # READ-WRITE bind (edits persist) — not ro, not tmpfs.
    assert ("--bind", str(u), "/workspace") in _triples(args)
    assert ("--ro-bind", str(u), "/workspace") not in _triples(args)


def test_only_credentials_are_masked_everything_else_is_open(tmp_path):
    u = _mk_universe(tmp_path)
    args = _project_folder_mounts(u)
    triples = _triples(args)
    pairs = _pairs(args)
    # Credential files blinded with /dev/null; the auth dir overlaid with tmpfs.
    assert ("--ro-bind", "/dev/null", "/workspace/.credential-vault.json") in triples
    assert ("--ro-bind", "/dev/null", "/workspace/config.yaml") in triples
    assert ("--tmpfs", "/workspace/.credentials") in pairs
    # EVERYTHING else — brain docs, DBs, arbitrary harness files — is NOT masked
    # (the folder is fully the founder's to control).
    for name in ("identity.md", "soul.edit.md", "checkpoints.db", "hooks.py"):
        assert f"/workspace/{name}" not in args, name


def test_secret_mask_args_targets_only_the_known_credentials(tmp_path):
    u = _mk_universe(tmp_path)
    args = _secret_mask_args(u)
    triples = _triples(args)
    pairs = _pairs(args)
    assert ("--ro-bind", "/dev/null", "/workspace/.credential-vault.json") in triples
    assert ("--ro-bind", "/dev/null", "/workspace/config.yaml") in triples
    assert ("--tmpfs", "/workspace/.credentials") in pairs
    # It never touches brain / harness content.
    assert "/workspace/identity.md" not in args
    assert "/workspace/checkpoints.db" not in args
