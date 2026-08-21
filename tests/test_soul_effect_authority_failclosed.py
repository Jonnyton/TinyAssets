"""Soul effect-authority must FAIL CLOSED on an unreadable existing soul.

Codex reject 2026-08-20: ``read_universe_soul`` swallows an ``OSError`` to
``None``, and ``effect_authority_from_soul`` turned that into ``()`` ->
``UNDECLARED``, so a soul-file read FAILURE could silently downgrade a real
DENY to a pass and let an otherwise-denied external effect fire. An existing-
but-unreadable soul must resolve to DENIED; only a genuinely absent soul is the
legitimate UNDECLARED.
"""

from __future__ import annotations

import pytest

import tinyassets.universe_soul as us
from tinyassets.effectors.authority import (
    DENIED,
    UNDECLARED,
    resolve_soul_effect_authority,
)
from tinyassets.universe_soul import effect_authority_from_soul, soul_path

_SINK = "authenticated_external_call"
_DEST = "api.example.com"


def test_unreadable_existing_soul_fails_closed_to_denied(tmp_path, monkeypatch):
    universe_dir = tmp_path / "u1"
    universe_dir.mkdir()
    # A soul file EXISTS on disk...
    soul_path(universe_dir).write_text("# soul\n", encoding="utf-8")
    # ...but the read hits an OSError, which read_universe_soul swallows to None.
    monkeypatch.setattr(us, "read_universe_soul", lambda _d: None)

    # effect_authority_from_soul must NOT report () (which reads as UNDECLARED);
    # an existing-but-unreadable soul RAISES so authority resolution fails closed.
    with pytest.raises(OSError):
        effect_authority_from_soul(universe_dir)

    # And the resolver maps that failure to DENIED, never UNDECLARED — so a real
    # DENY cannot be bypassed by making the soul unreadable.
    assert resolve_soul_effect_authority(universe_dir, _SINK, _DEST) == DENIED


def test_absent_soul_is_undeclared_not_denied(tmp_path):
    universe_dir = tmp_path / "u2"
    universe_dir.mkdir()
    # No soul file at all -> genuinely absent -> UNDECLARED (the legitimate pass
    # that keeps a soul-less universe from being blocked on every effect).
    assert effect_authority_from_soul(universe_dir) == ()
    assert resolve_soul_effect_authority(universe_dir, _SINK, _DEST) == UNDECLARED


def test_actual_read_failure_on_existing_soul_fails_closed(tmp_path):
    # A REAL read failure (no mock): the soul path EXISTS but is a directory, so
    # read_text raises IsADirectoryError (an OSError) that read_universe_soul
    # swallows to None. lstat() confirms the path exists -> fail closed -> DENIED.
    # This is the path Codex flagged is_file() could wrongly pass through.
    universe_dir = tmp_path / "u3"
    universe_dir.mkdir()
    soul_path(universe_dir).mkdir()  # exists, but unreadable as a file
    with pytest.raises(OSError):
        effect_authority_from_soul(universe_dir)
    assert resolve_soul_effect_authority(universe_dir, _SINK, _DEST) == DENIED
