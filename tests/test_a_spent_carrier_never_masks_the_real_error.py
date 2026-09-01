"""A retry must not overwrite the error it was retrying.

Live, 2026-09-01: the founder's universe stopped answering. Three automation
runs failed with

    provider invocation carrier is already consumed

and that is not why anything failed. `_call_router_with_retry` retries
`AllProvidersExhaustedError` three times, closing over the SAME
`universe_context`. Attempt 1 spends the single-use `ProviderInvocationCarrier`;
attempt 2 re-enters with the spent one and dies on "already consumed"; Tenacity
reraises the LAST error. Attempt 1's real cause never survived.

That masking is the expensive half. The failure was diagnosed as a quota problem
(the founder went and checked his usage — it was fine) and then as missing
ANTHROPIC/GROQ/GEMINI keys on a universe configured to ignore them. Both stories
were downstream of an error that had already been thrown away.

The carrier is single-use deliberately: one invocation, budgeted and settled
once. Re-minting per attempt would hide the symptom and destroy the property.
So a carrier-armed call is simply not retryable.
"""
from __future__ import annotations

import pytest

from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.providers.call import _call_router_with_retry


class _Ctx:
    """A universe context, with or without an armed invocation carrier."""

    def __init__(self, carrier: object | None):
        self.provider_invocation = carrier


class _Router:
    """Fails the way the live one did: real error first, then the spent-carrier
    error every time after."""

    def __init__(self, first: Exception):
        self.calls = 0
        self._first = first

    def call_sync(self, *a, **kw):
        self.calls += 1
        if self.calls == 1:
            raise self._first
        raise AllProvidersExhaustedError(
            "provider invocation carrier is already consumed"
        )


@pytest.fixture
def router(monkeypatch):
    def _install(first: Exception) -> _Router:
        r = _Router(first)
        import tinyassets.providers.call as mod

        monkeypatch.setattr(mod, "_real_router", r)
        monkeypatch.setattr(mod, "_register_open_providers_for", lambda _ctx: None)
        return r

    return _install


_REAL = AllProvidersExhaustedError(
    "codex refused the launch credential", failure_class="auth_invalid"
)


def test_an_armed_carrier_is_called_once_and_keeps_its_own_error(router):
    """The regression. Two things are asserted because both went wrong: the
    carrier is spent once, AND the error the owner sees is the real one."""
    r = router(_REAL)

    with pytest.raises(AllProvidersExhaustedError) as caught:
        _call_router_with_retry(
            "writer", "p", "s", universe_context=_Ctx(carrier=object()),
        )

    assert r.calls == 1, f"the spent carrier was re-entered {r.calls} times"
    assert "refused the launch credential" in str(caught.value)
    assert "already consumed" not in str(caught.value), (
        "the retry overwrote the real cause with its own artefact"
    )
    assert caught.value.failure_class == "auth_invalid", (
        "the failure class was lost, so every layer above must guess"
    )


def test_a_context_with_no_carrier_still_retries(router):
    """The fix must not disable retry generally. Rate-limit cooldowns expiring
    between attempts is the reason this bridge retries at all."""
    r = router(_REAL)

    with pytest.raises(AllProvidersExhaustedError):
        _call_router_with_retry(
            "writer", "p", "s", universe_context=_Ctx(carrier=None),
        )

    assert r.calls == 3, f"retry stopped working: {r.calls} attempt(s)"


def test_an_explicit_no_retry_caller_is_unaffected(router):
    """The interactive served path passes retry_on_exhaustion=False so it never
    sleeps holding a turn slot. Unchanged."""
    r = router(_REAL)

    with pytest.raises(AllProvidersExhaustedError):
        _call_router_with_retry(
            "writer", "p", "s",
            universe_context=_Ctx(carrier=None),
            retry_on_exhaustion=False,
        )

    assert r.calls == 1


def test_no_universe_context_at_all_still_retries(router):
    """`getattr(None, "provider_invocation", None)` must not read as armed."""
    r = router(_REAL)

    with pytest.raises(AllProvidersExhaustedError):
        _call_router_with_retry("writer", "p", "s", universe_context=None)

    assert r.calls == 3
