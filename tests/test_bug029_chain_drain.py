"""Tests for BUG-029 Part A — chain-drain detection + observability.

Covers:
- QuotaTracker.all_api_providers_in_cooldown(): True when all API providers
  cooled, False when at least one API provider is available.
- QuotaTracker.cooldown_remaining_dict(): returns per-provider remaining seconds.
- get_status exposes per_provider_cooldown_remaining as a dict.
- CHAIN_DRAINED warning is emitted when chain drains to local-only.
"""

from __future__ import annotations

import json
import logging

import pytest


class TestAllApiProvidersInCooldown:
    def _tracker(self):
        from workflow.providers.quota import QuotaTracker
        return QuotaTracker()

    def test_returns_false_when_no_providers_cooled(self):
        qt = self._tracker()
        chain = ["claude-code", "codex", "ollama-local"]
        assert qt.all_api_providers_in_cooldown(chain) is False

    def test_returns_true_when_all_api_providers_cooled(self):
        qt = self._tracker()
        qt.cooldown("claude-code", 120)
        qt.cooldown("codex", 120)
        chain = ["claude-code", "codex", "ollama-local"]
        assert qt.all_api_providers_in_cooldown(chain) is True

    def test_returns_false_when_one_api_provider_available(self):
        qt = self._tracker()
        qt.cooldown("claude-code", 120)
        chain = ["claude-code", "codex", "ollama-local"]
        assert qt.all_api_providers_in_cooldown(chain) is False

    def test_returns_false_when_chain_is_only_local(self):
        qt = self._tracker()
        chain = ["ollama-local"]
        assert qt.all_api_providers_in_cooldown(chain) is False

    def test_custom_local_providers_set(self):
        qt = self._tracker()
        qt.cooldown("claude-code", 120)
        qt.cooldown("codex", 120)
        chain = ["claude-code", "codex", "my-local"]
        # When my-local is declared local, all API providers (claude-code, codex) are cooled.
        assert qt.all_api_providers_in_cooldown(chain, local_providers={"my-local"}) is True

    def test_returns_false_when_chain_is_empty(self):
        qt = self._tracker()
        assert qt.all_api_providers_in_cooldown([]) is False


class TestCooldownRemainingDict:
    def _tracker(self):
        from workflow.providers.quota import QuotaTracker
        return QuotaTracker()

    def test_returns_zero_for_uncooled_providers(self):
        qt = self._tracker()
        result = qt.cooldown_remaining_dict(["claude-code", "ollama-local"])
        assert result["claude-code"] == 0
        assert result["ollama-local"] == 0

    def test_returns_positive_for_cooled_providers(self):
        qt = self._tracker()
        qt.cooldown("claude-code", 120)
        result = qt.cooldown_remaining_dict(["claude-code", "codex"])
        assert result["claude-code"] > 0
        assert result["codex"] == 0

    def test_all_providers_covered(self):
        qt = self._tracker()
        providers = ["claude-code", "codex", "gemini-free", "groq-free"]
        result = qt.cooldown_remaining_dict(providers)
        assert set(result.keys()) == set(providers)


class TestChainDrainWarning:
    def test_chain_drain_emits_warning(self, caplog):
        """When all API providers are cooled and chain falls through,
        CHAIN_DRAINED warning must appear in the log."""
        import asyncio
        from unittest.mock import AsyncMock

        from workflow.providers.base import ProviderResponse
        from workflow.providers.quota import QuotaTracker
        from workflow.providers.router import FALLBACK_CHAINS, ProviderRouter

        qt = QuotaTracker()
        providers: dict = {}
        # Register + cool every API provider in the writer chain. A cooled
        # provider stays registered, so it survives effective_chain (FEAT-006)
        # narrowing and reaches the BUG-029 Part A drain check. Registering
        # only ollama-local while cooling unregistered API names made the drain
        # check see a local-only chain and never fire (BUG-029 regression).
        for p in FALLBACK_CHAINS["writer"]:
            if p != "ollama-local":
                cooled = AsyncMock()
                cooled.name = p
                cooled.complete.return_value = ProviderResponse(
                    text="api", provider=p, model="m", family="f", latency_ms=0.0,
                )
                providers[p] = cooled
                qt.cooldown(p, 120)

        # Make ollama-local fail too so the chain exhausts (no providers succeed).
        mock_local = AsyncMock()
        mock_local.name = "ollama-local"
        mock_local.complete.side_effect = Exception("local failed")
        providers["ollama-local"] = mock_local

        router = ProviderRouter(providers=providers, quota=qt)

        from workflow.exceptions import AllProvidersExhaustedError
        with caplog.at_level(logging.WARNING, logger="workflow.providers.router"):
            with pytest.raises(AllProvidersExhaustedError):
                asyncio.run(router.call("writer", "prompt", "system"))

        assert any(
            "CHAIN_DRAINED" in record.message
            for record in caplog.records
        ), "CHAIN_DRAINED warning not emitted when all API providers in cooldown"

    def test_chain_drain_warning_with_unregistered_api_provider(self, caplog):
        """Part A warning fires on a claude-only cloud host too (Codex review).

        Mirrors the Part B guard in test_provider_router_bug029: claude-code is
        registered + cooled while codex is unregistered (absent binary). The
        absent codex must not veto the CHAIN_DRAINED warning — guards against a
        pre-effective_chain drain check, which would put never-cooled codex into
        the drain set and suppress the warning on this exact config.
        """
        import asyncio
        from unittest.mock import AsyncMock

        from workflow.exceptions import AllProvidersExhaustedError
        from workflow.providers.base import ProviderResponse
        from workflow.providers.quota import QuotaTracker
        from workflow.providers.router import ProviderRouter

        qt = QuotaTracker()
        qt.cooldown("claude-code", 120)

        claude = AsyncMock()
        claude.name = "claude-code"
        claude.complete.return_value = ProviderResponse(
            text="api", provider="claude-code", model="m", family="f", latency_ms=0.0,
        )
        # ollama-local fails so the chain exhausts and reaches Part A.
        local = AsyncMock()
        local.name = "ollama-local"
        local.complete.side_effect = Exception("local failed")
        # codex intentionally NOT registered (absent binary on a claude-only host).
        router = ProviderRouter(
            providers={"claude-code": claude, "ollama-local": local}, quota=qt,
        )

        with caplog.at_level(logging.WARNING, logger="workflow.providers.router"):
            with pytest.raises(AllProvidersExhaustedError):
                asyncio.run(router.call("writer", "prompt", "system"))

        assert any(
            "CHAIN_DRAINED" in record.message for record in caplog.records
        ), "CHAIN_DRAINED warning not emitted on claude-only host with codex absent"


class TestGetStatusCooldownField:
    def test_get_status_has_per_provider_cooldown_remaining(self):
        """get_status must include per_provider_cooldown_remaining dict."""
        from workflow.universe_server import get_status
        payload = json.loads(get_status())
        assert "per_provider_cooldown_remaining" in payload
        assert isinstance(payload["per_provider_cooldown_remaining"], dict)

    def test_per_provider_cooldown_remaining_values_are_ints(self):
        """All values in per_provider_cooldown_remaining must be non-negative ints."""
        from workflow.universe_server import get_status
        remaining = json.loads(get_status())["per_provider_cooldown_remaining"]
        for provider, seconds in remaining.items():
            assert isinstance(seconds, int), f"{provider}: expected int, got {type(seconds)}"
            assert seconds >= 0, f"{provider}: negative cooldown seconds"

    def test_schema_contract_includes_per_provider_field(self):
        """Contract test: schema_version=1 contract must include the new field."""
        from workflow.universe_server import get_status
        payload = json.loads(get_status())
        assert "per_provider_cooldown_remaining" in payload, (
            "per_provider_cooldown_remaining not in get_status schema_version=1 response"
        )


# ---- BUG-029 Part B — failure-taxonomy completeness matrix ---------------
#
# The chatbot UX surface depends on (failure_class, actionable_by,
# suggested_action) being uniformly populated for every recognised
# failure mode. A latent gap — a failure_class with empty actionable_by
# or empty suggested_action — would render as "Run failed" with no
# recovery hint, defeating the BUG-029 fix.
#
# These tests lock in the taxonomy contract:
#   1. Every key in `ACTIONABLE_BY` resolves to one of {host, chatbot,
#      user, none} via the canonical `_actionable_by` helper.
#   2. Every classifier branch in `_classify_run_outcome_error` returns
#      a non-empty `suggested_action` AND that the returned class is in
#      `ACTIONABLE_BY` (so chatbot can always look up `actionable_by`).
#
# Source of truth: `workflow.runs.ACTIONABLE_BY` (canonical map).
# Helpers under test live at `workflow.api.runs`.


_VALID_ACTIONABLE_BY = frozenset({"host", "chatbot", "user", "none"})


@pytest.fixture(scope="module")
def actionable_by_table() -> dict[str, str]:
    from workflow.runs import ACTIONABLE_BY
    return ACTIONABLE_BY


@pytest.fixture(scope="module")
def actionable_by_helper():
    from workflow.api.runs import _actionable_by
    return _actionable_by


class TestActionableByCompleteness:
    """Every failure_class in the canonical map must resolve to a known bucket."""

    def test_every_class_resolves_to_known_bucket(
        self, actionable_by_table, actionable_by_helper,
    ):
        for failure_class, expected_bucket in actionable_by_table.items():
            actual = actionable_by_helper(failure_class)
            assert actual == expected_bucket, (
                f"{failure_class}: helper returned {actual!r}, "
                f"map declares {expected_bucket!r}"
            )
            assert actual in _VALID_ACTIONABLE_BY, (
                f"{failure_class}: bucket {actual!r} is not one of "
                f"{sorted(_VALID_ACTIONABLE_BY)}"
            )

    def test_unknown_class_falls_back_to_user(self, actionable_by_helper):
        """Conservative-default: unmapped classes escalate to 'user', never silently drop."""
        assert actionable_by_helper("definitely_not_a_real_class") == "user"
        assert actionable_by_helper("") == "user"

    def test_taxonomy_covers_all_four_buckets(self, actionable_by_table):
        """Sanity-check: the canonical map exercises every bucket. If a future
        edit collapses the taxonomy to 3 buckets, this catches the regression."""
        buckets = set(actionable_by_table.values())
        assert buckets == _VALID_ACTIONABLE_BY, (
            f"ACTIONABLE_BY no longer covers all 4 buckets — got {sorted(buckets)}"
        )


# Strings keyed by the failure_class each classifier branch should emit.
# One representative string per regex/branch in `_classify_run_outcome_error`.
# When a new branch is added, this table MUST grow to match — otherwise the
# new branch will silently emit an unmapped failure_class.
_OUTCOME_ERROR_FIXTURES: tuple[tuple[str, str], ...] = (
    ("Empty LLM response from provider", "empty_llm_response"),
    ("Run timed out after 60s", "timeout"),
    ("Quota exhausted on Anthropic API", "quota_exhausted"),
    ("Provider overloaded — 503 service unavailable", "provider_overloaded"),
    ("Maximum context length exceeded for model", "context_length_exceeded"),
    ("Auth expired: token refresh required", "permission_denied:auth_expired"),
    ("Approval required for source_code node", "node_not_approved"),
    ("Permission denied", "permission_denied:approval_required"),
    ("Subprocess failure: exit code 127", "provider_subprocess_failed"),
    ("Concurrent modification conflict", "state_mutation_conflict"),
    ("Provider unavailable: no API key", "provider_unavailable"),
    ("Groq call failed: HTTP 502", "provider_error"),
)


@pytest.fixture(scope="module")
def classify_outcome():
    from workflow.api.runs import _classify_run_outcome_error
    return _classify_run_outcome_error


@pytest.mark.parametrize("error_string,expected_class", _OUTCOME_ERROR_FIXTURES)
class TestClassifyOutcomeErrorCompleteness:
    """For every classifier branch, the (failure_class, suggested_action) pair
    must be non-empty AND the failure_class must be in ACTIONABLE_BY (so the
    chatbot can always look up `actionable_by` for the same class)."""

    def test_classifier_returns_expected_class(
        self, classify_outcome, error_string, expected_class,
    ):
        result = classify_outcome(error_string)
        assert result is not None, (
            f"{error_string!r} → None (expected ({expected_class!r}, ...))"
        )
        actual_class, _ = result
        assert actual_class == expected_class, (
            f"{error_string!r} → {actual_class!r} (expected {expected_class!r})"
        )

    def test_classifier_returns_non_empty_suggested_action(
        self, classify_outcome, error_string, expected_class,
    ):
        result = classify_outcome(error_string)
        _, suggested_action = result
        assert suggested_action, (
            f"{error_string!r} ({expected_class!r}): empty suggested_action"
        )
        assert len(suggested_action) >= 20, (
            f"{error_string!r} ({expected_class!r}): suggested_action too "
            f"terse to be actionable: {suggested_action!r}"
        )

    def test_classified_class_resolves_to_known_actionable_by(
        self, classify_outcome, actionable_by_table, error_string, expected_class,
    ):
        """The class emitted by the classifier MUST appear in ACTIONABLE_BY.
        Otherwise the chatbot's `_actionable_by(failure_class)` lookup
        falls back to 'user' (safe default), masking the real recovery
        path the host/chatbot could have taken."""
        result = classify_outcome(error_string)
        actual_class, _ = result
        assert actual_class in actionable_by_table, (
            f"{error_string!r} → {actual_class!r}, but {actual_class!r} is "
            f"NOT in workflow.runs.ACTIONABLE_BY. Add it to the canonical "
            f"map so chatbot can render a non-default actionable_by."
        )
