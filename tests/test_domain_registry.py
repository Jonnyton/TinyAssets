from __future__ import annotations

import pytest

from tinyassets.domain_registry import (
    clear_registry,
    register_domain_branch_slug,
    register_episodic_coordinate_shape,
    registered_domain_branch_slugs,
    resolve_episodic_coordinate_shape,
)


@pytest.fixture(autouse=True)
def _clean_domain_registry():
    clear_registry()
    yield
    clear_registry()


def test_domain_branch_slugs_are_trimmed_deduplicated_and_sorted():
    register_domain_branch_slug(" fantasy ", " zeta ")
    register_domain_branch_slug("fantasy", "alpha")
    register_domain_branch_slug("fantasy", "alpha")
    register_domain_branch_slug("science", "model")
    register_domain_branch_slug("", "ignored")
    register_domain_branch_slug("fantasy", "  ")

    assert registered_domain_branch_slugs("fantasy") == ("alpha", "zeta")
    assert registered_domain_branch_slugs() == ("alpha", "model", "zeta")


def test_episodic_coordinate_shape_round_trips_and_replaces_by_domain():
    register_episodic_coordinate_shape(
        "fiction",
        ["chapter", "scene"],
        sequence_field="scene",
    )

    first = resolve_episodic_coordinate_shape("fiction")
    assert first is not None
    assert first.domain_id == "fiction"
    assert first.coordinate_fields == ("chapter", "scene")
    assert first.sequence_field == "scene"

    register_episodic_coordinate_shape("fiction", ("beat",))

    second = resolve_episodic_coordinate_shape("fiction")
    assert second is not None
    assert second.coordinate_fields == ("beat",)
    assert second.sequence_field is None


def test_unknown_domain_has_no_episodic_coordinate_shape():
    assert resolve_episodic_coordinate_shape("unknown") is None
