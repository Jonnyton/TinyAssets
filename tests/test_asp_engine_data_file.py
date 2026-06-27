"""BUG-026 — data/world_rules.lp must be present in a standard install layout.

asp_engine.py resolves `_DEFAULT_RULES_PATH` as `parents[2]/data/world_rules.lp`
relative to the module file. In the Docker image the module lives at
`/app/tinyassets/constraints/asp_engine.py`, so parents[2] = `/app` and the
expected path is `/app/data/world_rules.lp`. The Dockerfile was missing a
COPY for this file, causing ASP validation to silently fail in cloud deploys.

Fix: `COPY data/world_rules.lp /app/data/world_rules.lp` in Dockerfile.

These tests guard that:
1. The resolved path is not None and has the expected suffix.
2. The file actually exists in the working checkout (catches missing/moved file).
3. The file is non-empty and parseable as text (catches empty placeholder).
4. ASPEngine falls back gracefully when the default rules file is absent.
"""
from __future__ import annotations

import logging
from pathlib import Path

from tinyassets.constraints.asp_engine import _DEFAULT_RULES_PATH


class TestDefaultRulesPath:
    def test_path_resolves_to_lp_file(self):
        assert _DEFAULT_RULES_PATH.suffix == ".lp"
        assert _DEFAULT_RULES_PATH.name == "world_rules.lp"

    def test_path_exists_in_checkout(self):
        assert _DEFAULT_RULES_PATH.exists(), (
            f"data/world_rules.lp not found at {_DEFAULT_RULES_PATH}. "
            "The file must exist in the repo so it can be COPYed into the "
            "Docker image via `COPY data/world_rules.lp /app/data/world_rules.lp`."
        )

    def test_file_is_non_empty(self):
        assert _DEFAULT_RULES_PATH.stat().st_size > 0, (
            "world_rules.lp is empty — ASP engine would have no rules to apply."
        )

    def test_file_is_readable_text(self):
        content = _DEFAULT_RULES_PATH.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_data_dir_parent_matches_package_root(self):
        """parents[2] of asp_engine.py must be the repo/package root where
        data/ lives, not some arbitrary ancestor.
        """
        from tinyassets.constraints import asp_engine as _mod
        mod_path = Path(_mod.__file__).resolve()
        expected_root = mod_path.parents[2]
        assert (_DEFAULT_RULES_PATH.parent.parent == expected_root), (
            f"_DEFAULT_RULES_PATH parent chain mismatch: "
            f"expected {expected_root}/data/world_rules.lp"
        )


class TestASPEngineAbsentFile:
    def test_engine_init_with_missing_rules_does_not_crash(self, tmp_path):
        """ASPEngine should not crash at __init__ time when the rules file
        is absent — it only loads at validate() time."""
        from tinyassets.constraints.asp_engine import ASPEngine

        absent = tmp_path / "nonexistent.lp"
        engine = ASPEngine(base_rules_path=absent)
        assert engine is not None

    def test_engine_logs_warning_when_rules_file_missing(self, tmp_path, caplog):
        """When the rules file is missing, ASPEngine logs a warning at init
        time rather than crashing. The _base_rules string is empty."""
        from tinyassets.constraints.asp_engine import ASPEngine

        absent = tmp_path / "nonexistent.lp"
        with caplog.at_level(logging.WARNING, logger="tinyassets.constraints.asp_engine"):
            engine = ASPEngine(base_rules_path=absent)
        assert engine._base_rules == ""
        assert any("not found" in m.lower() for m in caplog.messages)
