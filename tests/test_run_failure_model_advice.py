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


def _retained_order(*exhausted):
    """A real candidate order after this run retained `exhausted`; no plan needed."""
    import threading

    from tinyassets.providers.work_candidate_data import WorkCandidateData

    data = WorkCandidateData.__new__(WorkCandidateData)
    data._lock = threading.RLock()
    data._exhaustion = tuple(exhausted)
    return data


def test_the_exhausted_error_carries_classified_evidence_and_never_the_response_body():
    """Both raise sites build from the retained order: refs and scopes always,
    the classified failure class and retry-after only for a boundary the caller
    validated itself. The provider's body is not in the message."""
    from tinyassets.api.runs import _classify_run_outcome_error
    from tinyassets.providers.agent_capacity_boundary import CapacityBoundary
    from tinyassets.providers.model_policy import Exhaustion, ModelRef

    first = Exhaustion("model", ModelRef("conn_a", "model-one"))
    second = Exhaustion("account", ModelRef("conn_a", "model-two"))
    data = _retained_order(first, second)
    boundary = CapacityBoundary(second, True, "provider_rate_limited", 30.0)

    exc = data.exhausted_error((boundary,))

    assert isinstance(exc, WorkModelExhaustedError)
    assert str(exc) == (
        "no eligible work model remains: model-one on conn_a (model scope); "
        "model-two on conn_a (account scope, provider_rate_limited, retry after 30s)"
    )
    assert str(data.exhausted_error()) == (
        "no eligible work model remains: model-one on conn_a (model scope); "
        "model-two on conn_a (account scope)"
    )
    assert _classify_run_error(exc, "branch_x")["failure_class"] == "work_model_exhausted"
    # The stored string carries "rate_limited": the exhaustion rule must win over
    # the quota/overload substring nets, in both string classifiers.
    stored = f"Provider call failed in node 'n1': {exc}"
    assert _classify_run_outcome_error(stored) == (
        "work_model_exhausted", _WORK_MODEL_EXHAUSTED_ACTION,
    )
    from tinyassets.runs import _classify_failure

    assert _classify_failure({"status": "failed", "error": stored}) == "work_model_exhausted"


def test_a_generic_exhausted_or_overloaded_error_is_not_read_as_order_exhaustion():
    """Only the typed message means "your order ran out"; the router's own
    exhausted text and a bare overload keep their existing classes.

    The classes asserted are the ones the classifier returned at a81fce5d
    (before the typed rule existed): the router text has no "providers
    exhausted" plural and falls through to the bare "provider" net."""
    from tinyassets.api.runs import _classify_run_outcome_error

    router_text = "Armed provider 'conn_a' exhausted; provider authority forbids fallback widening."
    assert _classify_run_outcome_error(router_text)[0] == "provider_unavailable"
    assert _classify_run_outcome_error("synthetic overload 503")[0] == "provider_overloaded"


def test_a_model_id_containing_timeout_is_still_order_exhaustion():
    """The evidence suffix carries the owner's own model ids. One that happens
    to contain "timeout" must not turn exhaustion into a timed-out run in
    either string classifier: the narrow typed prefix wins over the nets."""
    from tinyassets.api.runs import _classify_run_outcome_error
    from tinyassets.providers.model_policy import Exhaustion, ModelRef
    from tinyassets.runs import _classify_failure

    only = Exhaustion("model", ModelRef("conn_a", "fast-timeout-v2"))
    stored = f"Provider call failed in node 'n1': {_retained_order(only).exhausted_error()}"

    assert "timeout" in stored
    assert _classify_failure({"status": "failed", "error": stored}) == "work_model_exhausted"
    assert _classify_run_outcome_error(stored)[0] == "work_model_exhausted"


def test_the_host_endpoint_hint_is_documented_as_host_evidence():
    """`active_host.llm_endpoint_bound` is NOT the universe's selected model."""
    from tinyassets.api.status import _active_host_snapshot

    doc = (_active_host_snapshot.__doc__ or "").lower()
    assert "not" in doc and "selected" in doc
    assert "model_options" in doc
