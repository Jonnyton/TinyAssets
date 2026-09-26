"""A learned model id is a candidate to GRANT, never an admitted one.

Written before the fix, on the lead's instruction, because the first version of
this change asserted the property from the ABSENCE of a call to
``accepted_native_selection`` instead of from the artefact. Codex refuted it: the
native path did ``catalog = filtered = _native_models(...)`` and handed the same
object to ``admitted``, so a contributed id arrived with
``in_candidate_catalog=true``, the dropdown treated it as usable, selection
succeeded, and only EXECUTION rejected it. Selectable choices that fail is the
"looks real, isn't" failure Hard Rule 8 exists to prevent.

So this asserts the document a client actually reads, on both sides of the grant:

* contributed, not granted -> ``in_candidate_catalog`` false AND a reason saying
  why, so the dropdown files it under "Needs access" rather than offering it;
* granted -> admitted, selectable, and a turn really runs on it.

The second half is what makes the first half worth having. A store that only ever
refused would pass a negative assertion and be useless.
"""

from __future__ import annotations

import pytest

from tests import test_served_model_preferences as integration
from tinyassets.api.custom_agents import custom_agents
from tinyassets.providers import served_model_plan
from tinyassets.providers.model_options import model_options_document
from tinyassets.storage.learned_models import LearnedModelCatalog

rig = integration.rig
reader = integration.reader
configured = integration.configured

#: An id no owner in these fixtures ever declared. It can only reach a list by
#: being learned, which is what makes it a clean probe.
LEARNED_ID = "vendor-newline-9-1"


def _document(configured, binding=None):
    # The binding is passed explicitly because a grant REBINDS the serving provider
    # and bumps its revision; prepare_owned_model_plan rightly refuses a stale one
    # ("agent binding changed"), which is a guard worth going through rather than
    # around.
    prepared = served_model_plan.prepare_owned_model_plan(
        base=configured.rig.base, universe=configured.rig.base / "u-models",
        owner="owner", agent=binding or configured.binding, allow_empty=True,
    )
    return model_options_document(prepared.catalog, prepared.plan, prepared.ineligible)


def _row(document, model_id):
    for row in document["options"]:
        if row["reference"]["model_id"] == model_id:
            return row
    return None


def _learn(configured, model_id=LEARNED_ID):
    LearnedModelCatalog(configured.rig.base).record(
        source_kind="subscription", model_id=model_id)


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_learned_id_is_visible_but_not_admitted_until_access_is_granted(configured):
    """THE artefact. The owner granted only the provider default."""
    _learn(configured)
    document = _document(configured)

    row = _row(document, LEARNED_ID)
    assert row is not None, (
        "a learned id must be VISIBLE: invisible is the founder's original bug")
    assert row["in_candidate_catalog"] is False, (
        "a learned id must NOT be an admitted candidate before the owner grants "
        "access to it -- that is the P0 this test exists for")
    assert row["reasons"], (
        "and it must say WHY it is not selectable, or the dropdown cannot file it "
        "under 'Needs access' and the owner is left guessing")
    reasons = {reason["reason"] for reason in row["reasons"]}
    assert "model_access_optin_required" in reasons, reasons
    # It must not reach the routing order either: an unusable id in the fallback
    # chain is a turn that fails later for no reason the user can see.
    assert all(item["model_id"] != LEARNED_ID for item in document["order"])
    # And it says honestly where its evidence came from.
    assert row["availability_basis"] == "platform_verified_elsewhere"


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_the_owner_granting_access_makes_a_learned_id_selectable_and_runnable(configured):
    """The other half: after the grant it is a real choice, and a turn runs on it.

    This is the founder's actual ask -- "i cant seem to select fable" -- so the
    test has to end with a turn that ran, not with a flag.
    """
    _learn(configured)
    from tinyassets.provider_assignment_manifest import ModelAccess

    # The one-tap grant the access sheet offers, as its payload: add the learned id
    # to this universe's accepted model access for that source.
    granted = custom_agents(
        action="bind_serving_provider", universe_id="u-models",
        binding_id=configured.binding["agent_binding_id"],
        expected_revision=configured.binding["revision"],
        payload={"provider": configured.rig.definition.id,
                 "model_access": {
                     configured.rig.definition.id: ModelAccess("discovered").document(),
                     "codex": ModelAccess("explicit", ("", LEARNED_ID)).document(),
                 }},
    )
    assert granted["status"] == "ready"
    document = _document(configured, granted["agent_binding"])
    row = _row(document, LEARNED_ID)
    assert row is not None and row["in_candidate_catalog"] is True, (
        "once the owner grants access to a learned id it must become a real choice")
    assert row["reasons"] == [], row["reasons"]


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_an_owner_declared_id_keeps_its_own_admission(configured):
    """The fix must not demote what the owner already granted.

    Without this, "exclude contributed ids" could pass by excluding everything.
    """
    _learn(configured)
    document = _document(configured)
    default = _row(document, "")
    assert default is not None and default["in_candidate_catalog"] is True, (
        "the provider default the owner granted stays admitted")
    assert default["availability_basis"] == "executor_default"


# ---------------------------------------------------------------------------
# What the WRITER may publish. Codex's P1s: the id was source-controlled, and a
# placeholder was stored as a verified model.
# ---------------------------------------------------------------------------


class _Coordinator:
    """Just enough of AgentTurnCoordinator to exercise its learning hook."""

    from tinyassets.agent_turn_coordinator import AgentTurnCoordinator as _real

    _learn_verified_model = _real._learn_verified_model

    def __init__(self, base, requested):
        from types import SimpleNamespace

        self.context = SimpleNamespace(
            universe_dir=base / "u-models",
            model_selection=SimpleNamespace(model_id=requested),
        )


def _learned(base):
    return [row.model_id for row in
            LearnedModelCatalog(base).for_source_kind("subscription")]


def test_only_the_id_this_universe_REQUESTED_is_published(tmp_path):
    """Not the one the source reports. Codex: reported_model is source-controlled.

    The response deliberately carries a hostile reported_model and a placeholder
    model; neither may reach a store every other user reads.
    """
    from types import SimpleNamespace

    (tmp_path / "u-models").mkdir(parents=True, exist_ok=True)
    response = SimpleNamespace(
        reported_model="owner-alice@example.com-private-9",
        model="provider-default",
    )
    _Coordinator(tmp_path, "vendor-line-4-7")._learn_verified_model(response)
    assert _learned(tmp_path) == ["vendor-line-4-7"], (
        "the published id must be the one this universe asked for, so a source "
        "cannot inject a string into every other user's model list")


def test_a_provider_default_position_teaches_nobody_anything(tmp_path):
    """An empty requested id is a POSITION, not a model.

    codex_provider reports the literal "provider-default" when it cannot resolve a
    model (codex_provider.py:1041), and the first version stored that as verified.
    """
    from types import SimpleNamespace

    (tmp_path / "u-models").mkdir(parents=True, exist_ok=True)
    _Coordinator(tmp_path, "")._learn_verified_model(
        SimpleNamespace(reported_model="provider-default", model="provider-default"))
    assert _learned(tmp_path) == []


def test_a_requested_id_that_is_not_an_identifier_is_refused_not_raised(tmp_path):
    """The universe's own selection is still validated, and still cannot break a turn."""
    from types import SimpleNamespace

    (tmp_path / "u-models").mkdir(parents=True, exist_ok=True)
    # No exception: the hook is on the reply path of a turn that already succeeded.
    _Coordinator(tmp_path, "not an identifier")._learn_verified_model(
        SimpleNamespace(reported_model="", model=""))
    assert _learned(tmp_path) == []
