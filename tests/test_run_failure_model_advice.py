"""Run-failure advice for work-model trouble names keys and routes that exist.

Live 2026-09-20: the app was told a codex-pinned workflow needed the OPERATOR to
switch the universe's global serving provider. `_PROVIDER_NOT_BOUND_ACTION` said
so, using a pin key the validator rejects, and every held authority -- binding
AND capacity exhaustion -- arrived under one class.
"""

import pytest

from tinyassets.api.runs import (
    _PROVIDER_NOT_BOUND_ACTION,
    _WORK_MODEL_EXHAUSTED_ACTION,
    _classify_run_error,
)
from tinyassets.exceptions import ProviderAuthorityHeldError, WorkModelExhaustedError

ADVICE = (_PROVIDER_NOT_BOUND_ACTION, _WORK_MODEL_EXHAUSTED_ACTION)


@pytest.mark.parametrize("advice", ADVICE)
def test_advice_names_the_pin_key_the_validator_actually_accepts(advice):
    """`tinyassets/branches.py` validates `llm_policy.preferred.provider`."""
    assert "llm_policy.preferred.provider" in advice
    assert "preferred_provider" not in advice


@pytest.mark.parametrize("advice", ADVICE)
def test_advice_points_at_the_owners_own_model_routes(advice):
    assert "model_options" in advice
    assert "model_preferences" in advice


@pytest.mark.parametrize("advice", ADVICE)
def test_advice_never_asks_for_a_global_serving_switch_to_defeat_a_pin(advice):
    """No host-level switch can make a pinned-but-exhausted source pass.

    `providers/router.py` treats a writer pin as CONFLICTING with the armed
    provider rather than replacing it, so this advice sent the reader somewhere
    nothing they did could help -- and named the host while doing it.
    """
    lowered = advice.lower()
    assert "make the pinned provider serving" not in lowered
    assert "serving provider" not in lowered
    assert "host" not in lowered or "not host-actionable" in lowered


def test_a_held_binding_keeps_its_existing_class_and_raw_evidence():
    exc = ProviderAuthorityHeldError("Connect your provider before running this universe.")
    payload = _classify_run_error(exc, "branch_x")

    assert payload["failure_class"] == "permission_denied:provider_not_bound"
    assert payload["actionable_by"] == "chatbot"
    assert str(exc) in payload["error"]


def test_work_model_exhaustion_is_typed_apart_from_a_missing_binding():
    """Capacity exhaustion must not read as "connect your provider"."""
    exc = WorkModelExhaustedError("no eligible work model remains")
    payload = _classify_run_error(exc, "branch_x")

    assert payload["failure_class"] == "work_model_exhausted"
    assert payload["actionable_by"] == "chatbot"
    assert payload["suggested_action"] == _WORK_MODEL_EXHAUSTED_ACTION
    # Raw evidence survives: the class is derived, never a replacement for it.
    assert "no eligible work model remains" in payload["error"]


def test_exhaustion_stays_a_held_authority_for_every_existing_handler():
    """Subclassing keeps the generic contract: no `except` clause changes."""
    assert issubclass(WorkModelExhaustedError, ProviderAuthorityHeldError)


def test_the_taxonomy_matches_the_subclass_before_the_base_class():
    from tinyassets.api.runs import _build_failure_taxonomy

    rows = [row[0] for row in _build_failure_taxonomy()]
    assert rows.index(WorkModelExhaustedError) < rows.index(ProviderAuthorityHeldError)


def test_a_run_that_exhausts_its_captured_order_reports_exhaustion_not_binding():
    """The session raises the typed error where the order runs out."""
    import inspect

    from tinyassets import foreground_run_provider

    source = inspect.getsource(foreground_run_provider._ForegroundRunProviderSession)
    exhausted = source[source.index("if selected is None:"):]
    assert exhausted.startswith(
        "if selected is None:\n                raise WorkModelExhaustedError("
    )


def test_the_host_endpoint_hint_is_documented_as_host_evidence():
    """`active_host.llm_endpoint_bound` is NOT the universe's selected model."""
    from tinyassets.api.status import _active_host_snapshot

    doc = (_active_host_snapshot.__doc__ or "").lower()
    assert "not" in doc and "selected" in doc
    assert "model_options" in doc
