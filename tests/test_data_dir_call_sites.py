"""Row B cleanup: regression guard for the two call sites that were
bypassing ``tinyassets.storage.data_dir()``.

Pre-Row-B-cleanup state: both call sites bypassed ``data_dir()`` and
defaulted to CWD-relative ``output`` → /app/output in a container →
ephemeral writes lost on restart. Auth sessions specifically: users had
to re-authenticate after every container restart.

These tests prove both call sites now honor ``$TINYASSETS_DATA_DIR``.
The pre-commit hook (invariant 5) prevents the bypass pattern from
re-emerging structurally; this test catches semantic regressions at
the call site level.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """Strip env vars the resolver reads so each test starts at zero."""
    for name in ("TINYASSETS_DATA_DIR",):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_auth_provider_honors_workflow_data_dir(clean_env, tmp_path):
    """OAuthProvider's default db_path routes through data_dir()."""
    target = tmp_path / "auth-root"
    clean_env.setenv("TINYASSETS_DATA_DIR", str(target))

    from tinyassets.auth import provider

    ap = provider.OAuthProvider()
    db_path = ap._db_path
    assert db_path.parent.resolve() == target.resolve(), (
        f"OAuthProvider db not rooted at TINYASSETS_DATA_DIR: "
        f"got {db_path.parent.resolve()!r}, expected {target.resolve()!r}"
    )
    assert db_path.name == ".auth.db"


def test_node_evaluator_honors_workflow_data_dir(clean_env, tmp_path):
    """NodeEvaluator's default db_path routes through data_dir()."""
    target = tmp_path / "eval-root"
    clean_env.setenv("TINYASSETS_DATA_DIR", str(target))

    from tinyassets.node_eval import NodeEvaluator

    ne = NodeEvaluator()
    db_path = ne._db_path
    assert db_path.parent.resolve() == target.resolve(), (
        f"NodeEvaluator db not rooted at TINYASSETS_DATA_DIR: "
        f"got {db_path.parent.resolve()!r}, expected {target.resolve()!r}"
    )
    assert db_path.name == ".node_eval.db"


def test_auth_provider_absolute_even_without_env(clean_env, tmp_path):
    """No env → resolver default → still absolute (no CWD drift)."""
    from tinyassets.auth import provider

    ap = provider.OAuthProvider()
    assert ap._db_path.is_absolute(), (
        "OAuthProvider.db_path is not absolute — container CWD-drift risk"
    )


def test_node_evaluator_absolute_even_without_env(clean_env, tmp_path):
    """No env → resolver default → still absolute (no CWD drift)."""
    from tinyassets.node_eval import NodeEvaluator

    ne = NodeEvaluator()
    assert ne._db_path.is_absolute(), (
        "NodeEvaluator.db_path is not absolute — container CWD-drift risk"
    )


def test_explicit_db_path_still_works(clean_env, tmp_path):
    """Caller-supplied db_path is respected (constructor injection still works)."""
    from tinyassets.auth import provider

    override = tmp_path / "explicit.db"
    ap = provider.OAuthProvider(db_path=override)
    assert ap._db_path == override
