"""Finite run-session advisory choices, never an invocation authority carrier."""

import json
import threading

from tinyassets.providers.model_policy import ModelPolicy, ModelRef, order_models


def fit_orders(groups, *, ceiling):
    """Fit only Automatic discovered prefixes into already accepted authority.

    Each group is (ordered refs, aggregate compiler retry weight, pure Automatic).
    Explicit choices remain complete and ordered or the graph refuses.
    """
    if type(ceiling) is not int or ceiling < 1 or not groups:
        raise PermissionError("workflow exceeds the shared invocation allowance")
    fitted, minimum = {}, 0
    for key in sorted(groups):
        order, weight, automatic = groups[key]
        if (type(order) is not tuple or not order or len(set(order)) != len(order)
                or any(type(ref) is not ModelRef for ref in order)
                or type(weight) is not int or weight < 1 or type(automatic) is not bool):
            raise ValueError("invalid finite work model order")
        fitted[key] = order[:1] if automatic else order
        minimum += weight * len(fitted[key])
    if minimum > ceiling:
        raise PermissionError("workflow exceeds the shared invocation allowance")
    while True:
        advanced = False
        for key in sorted(groups):
            order, weight, automatic = groups[key]
            size = len(fitted[key])
            if automatic and size < len(order) and minimum + weight <= ceiling:
                fitted[key] = order[:size + 1]
                minimum += weight
                advanced = True
        if not advanced:
            return fitted, minimum


def policy_key(policy):
    return json.dumps(policy or {}, sort_keys=True, separators=(",", ":"), allow_nan=False)


def prepare_captured_choices(base, *, owner, universe, document):
    """Discover current owned facts using original preference DATA, outside SQL."""
    from pathlib import Path

    from tinyassets.provider_serving_binding import resolve_serving_agent_binding
    from tinyassets.providers.model_preferences import ModelPreferences, capture_preference_policy
    from tinyassets.providers.served_model_plan import prepare_owned_model_plan
    from tinyassets.storage.model_preferences import PreferenceSnapshot

    if (not isinstance(document, dict)
            or set(document) != {"version", "saved", "observed_generation", "current"}
            or type(document["version"]) is not int or document["version"] != 1):
        raise ValueError("invalid captured work preference document")
    saved = None if document["saved"] is None else ModelPreferences.from_document(document["saved"])
    current = (None if document["current"] is None else
               ModelPreferences.from_document(document["current"]))
    generation = document["observed_generation"]
    capture_preference_policy(saved=saved, observed_generation=generation, current=current)
    agent = resolve_serving_agent_binding(base, universe_id=universe, owner_user_id=owner)
    prepared = prepare_owned_model_plan(
        base=base, universe=Path(base) / universe, owner=owner, agent=agent, current=current,
        preference_snapshot=PreferenceSnapshot(generation, saved),
    )
    return None if prepared is None else WorkCandidateData(prepared.plan)


def _matches(ref, pin):
    if not isinstance(pin, dict):
        raise PermissionError("invalid graph model constraint")
    provider = pin.get("provider")
    model = pin.get("model_id", pin.get("model"))
    return (not provider or ref.connection_id == provider) and (not model or ref.model_id == model)


class WorkCandidateData:
    """One run's captured advisory order/capacity facts; no model-call methods.

    Keep the original catalogue facts to interpret exhaustion if a subsequent
    discovery loses that source. Fresh _authorize_attempt still decides every
    invocation. Never attach this object to a served context or progress journal.
    """

    def __init__(self, plan):
        self.owner, self.universe = plan.catalog.owner_id, plan.catalog.universe_id
        self.catalog, self.interaction = plan.catalog, plan.interaction
        self.source_policies = plan.source_policies
        self.automatic = (plan.policy.mode == "automatic"
                          and plan.policy.current_selection is None
                          and plan.policy.saved_default is None)
        # Includes the existing Automatic-only source-health demotion.
        self.order = tuple(item.ref for item in plan.order(self.owner, self.universe).candidates)
        explicit = plan.policy.current_selection or plan.policy.saved_default
        if explicit is not None:
            requested = (explicit, *plan.policy.fallbacks)
            if len(self.order) != len(requested) or any(
                actual.connection_id != expected.connection_id
                or (expected.model_id and actual.model_id != expected.model_id)
                for actual, expected in zip(self.order, requested)
            ):
                raise PermissionError("explicit work model order is not fully eligible")
        if not self.order:
            raise PermissionError("no eligible work model remains")
        self._fitted = None
        self._exhaustion = ()
        self._lock = threading.RLock()

    def _constrained(self, policy):
        if not policy:
            return self.order
        if policy.get("difficulty_override"):
            raise PermissionError("dynamic graph model overrides conflict with captured selection")
        matching = tuple(ref for ref in self.order if _matches(ref, policy.get("preferred", {})))
        if not matching or (not self.automatic and matching[0] != self.order[0]):
            raise PermissionError("graph model constraint conflicts with captured primary")
        primary = matching[0]
        tail = tuple(ref for ref in self.order if ref != primary)
        if "fallback_chain" in policy:
            permitted = policy["fallback_chain"]
            narrowed = tuple(ref for ref in tail if any(_matches(ref, pin) for pin in permitted))
            if not self.automatic and narrowed != tail:
                raise PermissionError("graph model constraint conflicts with explicit fallbacks")
            tail = narrowed
        return (primary, *tail)

    def fit(self, snapshot, *, ceiling, retry_multiplier):
        groups = {}
        for node in snapshot["node_defs"]:
            if not str(node.get("prompt_template") or "").strip():
                continue
            policy = node.get("llm_policy") or snapshot.get("default_llm_policy")
            key = policy_key(policy)
            prior = groups.get(key, (self._constrained(policy), 0, self.automatic))
            groups[key] = (prior[0], prior[1] + (retry_multiplier if policy else 1), prior[2])
        fitted, minimum = fit_orders(groups, ceiling=ceiling)
        with self._lock:
            if self._fitted is not None and self._fitted != fitted:
                raise PermissionError("admitted work model order changed")
            self._fitted = fitted
        return minimum

    def next_candidate(self, policy, exhaustion=()):
        with self._lock:
            if self._fitted is None or policy_key(policy) not in self._fitted:
                raise PermissionError("work model order was not admitted")
            for item in exhaustion:
                if item not in self._exhaustion:
                    self._exhaustion += (item,)
            refs = self._fitted[policy_key(policy)]
            # This is a DATA filter over retained capacity identity, not discovery
            # or fresh authority. It cannot throw for a now-absent old source.
            ordered = order_models(
                self.catalog, ModelPolicy(0, "explicit", refs[1:], saved_default=refs[0]),
                self.interaction, owner_id=self.owner, universe_id=self.universe,
                exhaustion=self._exhaustion, source_policies=self.source_policies,
            )
            return ordered.candidates[0].ref if ordered.candidates else None
