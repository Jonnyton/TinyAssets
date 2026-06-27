from __future__ import annotations

from tinyassets.api.extensions import (
    VALID_PHASES as EXTENSION_VALID_PHASES,
)
from tinyassets.api.extensions import (
    NodeRegistration,
)
from tinyassets.branches import VALID_PHASES as BRANCH_VALID_PHASES
from tinyassets.branches import NodeDefinition


def test_enrich_phase_is_canonical_and_worldbuild_alias_is_dual_accepted() -> None:
    assert "enrich" in BRANCH_VALID_PHASES
    assert "enrich" in EXTENSION_VALID_PHASES
    assert "worldbuild" in BRANCH_VALID_PHASES
    assert "worldbuild" in EXTENSION_VALID_PHASES

    assert NodeDefinition(
        node_id="source-synthesis",
        display_name="Source Synthesis",
        phase="enrich",
    ).phase == "enrich"
    assert NodeDefinition(
        node_id="legacy-source-synthesis",
        display_name="Legacy Source Synthesis",
        phase="worldbuild",
    ).phase == "enrich"
    assert NodeRegistration(
        node_id="legacy-standalone",
        display_name="Legacy Standalone",
        description="legacy phase alias",
        phase="worldbuild",
        input_keys=[],
        output_keys=[],
        source_code="def run(state): return {}",
    ).phase == "enrich"
