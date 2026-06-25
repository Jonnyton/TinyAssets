"""Tests for scripts/wt.py teardown helpers.

Guards the branch-delete flag selection: ``git branch -d`` is ancestor-based
and refuses squash-merged branches (this repo's default merge style), which
would strand the local branch after ``wt.py done``. Once the merge is proven
squash-aware, teardown must force-delete with ``-D``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))  # so wt.py's sibling import (git_squash_merge) resolves
_SPEC = importlib.util.spec_from_file_location("wt", _SCRIPTS / "wt.py")
wt = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules["wt"] = wt
_SPEC.loader.exec_module(wt)


def test_proven_merged_uses_force_delete():
    # Squash-merged branch: proven merged but NOT an ancestor -> -d would refuse.
    assert wt._branch_delete_flag(merged=True, force=False) == "-D"


def test_force_uses_force_delete():
    assert wt._branch_delete_flag(merged=False, force=True) == "-D"


def test_unmerged_unforced_stays_safe_delete():
    # Unreachable in cmd_done (it bails first), but the helper stays conservative.
    assert wt._branch_delete_flag(merged=False, force=False) == "-d"
