"""Tests for task #30: universe inspect cross_surface_hint field."""
import json
from pathlib import Path
from unittest.mock import patch

from tinyassets.api.prompts import _CONTROL_STATION_PROMPT


def _call_inspect(universe_id="test-u"):
    from tinyassets.api.universe import _action_inspect_universe

    fake_udir = Path("/fake") / universe_id

    def fake_is_dir():
        return True

    with (
        # _action_inspect_universe lives in tinyassets.api.universe and
        # imports these symbols directly (not via re-export). Patch at the
        # consumer site (api.universe) for it to take effect.
        patch("tinyassets.api.universe._default_universe", return_value=universe_id),
        patch("tinyassets.api.universe._universe_dir", return_value=fake_udir),
        patch.object(Path, "is_dir", return_value=True),
        patch("tinyassets.api.universe._read_json", return_value=None),
        patch("tinyassets.api.universe._read_text", return_value=""),
        patch("tinyassets.api.universe._daemon_liveness", return_value={
            "phase": "idle", "phase_human": "Idle", "is_paused": False,
            "has_premise": False, "has_work": False, "last_activity_at": "",
            "staleness": "fresh", "word_count": 0, "word_count_sample": "",
            "accept_rate": 0, "accept_rate_sample": "",
        }),
        patch("tinyassets.api.universe._list_output_tree", return_value=[]),
        patch("tinyassets.api.universe._base_path", return_value=Path("/fake")),
    ):
        return json.loads(_action_inspect_universe(universe_id=universe_id))


class TestInspectCrossSurfaceHint:
    def test_cross_surface_hint_present(self):
        """inspect response always includes cross_surface_hint."""
        result = _call_inspect()
        assert "cross_surface_hint" in result

    def test_cross_surface_hint_has_note(self):
        """cross_surface_hint.note is a non-empty string."""
        result = _call_inspect()
        hint = result["cross_surface_hint"]
        assert isinstance(hint.get("note"), str)
        assert hint["note"]

    def test_cross_surface_hint_has_four_paths(self):
        """cross_surface_hint.paths has exactly 4 entries."""
        result = _call_inspect()
        paths = result["cross_surface_hint"]["paths"]
        assert isinstance(paths, list)
        assert len(paths) == 4

    def test_cross_surface_hint_path_actions(self):
        """All 4 required discovery paths are present."""
        result = _call_inspect()
        actions = {p["action"] for p in result["cross_surface_hint"]["paths"]}
        assert "extensions action=list_branches" in actions
        assert "goals action=list" in actions
        assert "wiki action=search" in actions
        assert "universe action=list" in actions

    def test_cross_surface_hint_paths_have_purpose(self):
        """Every path entry has a non-empty purpose field."""
        result = _call_inspect()
        for p in result["cross_surface_hint"]["paths"]:
            assert p.get("purpose"), f"Missing purpose on path: {p}"

    def test_existing_fields_still_present(self):
        """cross_surface_hint addition does not remove universe_id or daemon."""
        result = _call_inspect()
        assert "universe_id" in result
        assert "daemon" in result


class TestPromptCrossDomainRule:
    def test_prompt_mentions_cross_surface_hint(self):
        """The routing rules section names cross_surface_hint so chatbots know the field."""
        assert "cross_surface_hint" in _CONTROL_STATION_PROMPT

    def test_prompt_cross_domain_pivot_rule_present(self):
        """The prompt tells chatbots to pivot on domain mismatch, not say 'fantasy-only'."""
        assert "fantasy-only" in _CONTROL_STATION_PROMPT
        assert "cross_surface_hint.paths" in _CONTROL_STATION_PROMPT

    def test_prompt_pivot_mentions_list_branches(self):
        """Pivot rule directs chatbots to extensions action=list_branches."""
        assert "extensions action=list_branches" in _CONTROL_STATION_PROMPT
