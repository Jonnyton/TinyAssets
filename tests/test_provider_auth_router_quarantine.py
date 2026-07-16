"""Router-level auth-health quarantine (2026-06-25 loop-wedge, Slice 2).

Slice 1 quarantined a dead-auth *worker* (the supervisor gate, see
``test_provider_auth_quarantine.py``). This slice gates the *router*: a
subscription provider whose login is definitively ``not_logged_in`` is skipped
in fallback chains — routing goes straight to a healthy provider instead of
burning a failed attempt + a misleading cooldown — and a pinned writer with
dead auth fails loud (hard rule #8) rather than silently routing elsewhere.

The probe is *injected* (``auth_health=``), so the default router (no probe)
is completely unaffected; that keeps every existing fake-provider test green.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from tinyassets import runtime_singletons as runtime
from tinyassets.config import UniverseConfig
from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
from tinyassets.providers.quota import QuotaTracker
from tinyassets.providers.router import ProviderRouter


class _FakeProvider(BaseProvider):
    def __init__(self, name: str, text: str = "content") -> None:
        self.name = name
        self.family = "fake"
        self._text = text
        self.call_count = 0

    async def complete(
        self, prompt: str, system: str, config: ModelConfig, *, universe_dir=None,
    ) -> ProviderResponse:
        self.call_count += 1
        return ProviderResponse(
            text=self._text,
            provider=self.name,
            model="fake",
            family="fake",
            latency_ms=0.0,
        )


def _run(coro):
    return asyncio.run(coro)


def _auth_probe(dead: set[str]):
    """Probe: codex/claude-code report 'ok' unless in *dead*; others 'unknown'.

    Matches ``subscription_auth_health`` semantics — only the subscription
    writers are assessable; api-key/local providers return 'unknown'.
    """

    def probe(provider_name: str) -> dict[str, str]:
        if provider_name in dead:
            return {
                "provider": provider_name,
                "status": "not_logged_in",
                "detail": "test",
            }
        if provider_name in ("codex", "claude-code"):
            return {"provider": provider_name, "status": "ok", "detail": "test"}
        return {"provider": provider_name, "status": "unknown", "detail": "test"}

    return probe


@pytest.fixture
def isolated_universe_config():
    """Snapshot + restore runtime config and routing-relevant env per test.

    Clears ``TINYASSETS_PIN_WRITER`` and ``TINYASSETS_ALLOW_API_KEY_PROVIDERS`` so
    tests are hermetic regardless of the host env: with api-key providers
    enabled, ``test_all_subscription_dead_falls_to_local`` would correctly pick
    ``gemini-free`` before ``ollama-local`` and break the assertion.
    """
    _NEUTRALIZE = (
        "TINYASSETS_PIN_WRITER",
        "TINYASSETS_ALLOW_API_KEY_PROVIDERS",
        # Neutralize the process-global universe so the auth-health gate's
        # per-universe-vault awareness (S5 round 5) can't pick up a host-env
        # universe and alter the no-vault tests. Tests that want per-universe
        # auth pass an explicit universe_context.
        "TINYASSETS_UNIVERSE",
        # The BYO bypass is DARK unless the vault-encryption gate is on (F3);
        # tests that exercise the bypass set it explicitly.
        "TINYASSETS_BYO_VAULT_ENCRYPTED",
    )
    saved_config = runtime.universe_config
    saved_env = {k: os.environ.get(k) for k in _NEUTRALIZE}
    runtime.universe_config = UniverseConfig()
    for k in _NEUTRALIZE:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        runtime.universe_config = saved_config
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def _router(dead: set[str]) -> tuple[ProviderRouter, dict[str, _FakeProvider]]:
    names = [
        "claude-code", "codex", "gemini-free", "groq-free",
        "grok-free", "ollama-local",
    ]
    providers = {n: _FakeProvider(n) for n in names}
    router = ProviderRouter(
        providers=providers,
        quota=QuotaTracker(),
        auth_health=_auth_probe(dead),
    )
    return router, providers


# ---------------------------------------------------------------------------
# Fallback chain: dead-auth providers are skipped, not tried
# ---------------------------------------------------------------------------


def test_dead_auth_writer_skipped_routes_to_next(isolated_universe_config):
    """claude-code dead -> route straight to codex; claude-code never called."""
    router, providers = _router(dead={"claude-code"})

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "codex"
    assert providers["claude-code"].call_count == 0
    assert providers["codex"].call_count == 1


def test_healthy_writer_not_skipped(isolated_universe_config):
    """No spurious skipping: a healthy claude-code still wins the chain."""
    router, providers = _router(dead=set())

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "claude-code"
    assert providers["claude-code"].call_count == 1


def test_all_subscription_dead_falls_to_local(isolated_universe_config):
    """Both subscription writers dead -> fall through to local (unknown kept)."""
    router, providers = _router(dead={"claude-code", "codex"})

    resp = _run(router.call("writer", "p", "s"))

    # gemini/groq/grok are api-key (dropped by default); ollama-local probes
    # 'unknown' and must never be stranded by the auth gate.
    assert resp.provider == "ollama-local"
    assert providers["claude-code"].call_count == 0
    assert providers["codex"].call_count == 0
    assert providers["ollama-local"].call_count == 1


def test_no_probe_means_no_gating(isolated_universe_config):
    """Default router (no injected probe) is unaffected — zero blast radius."""
    names = ["claude-code", "codex", "ollama-local"]
    providers = {n: _FakeProvider(n) for n in names}
    router = ProviderRouter(providers=providers, quota=QuotaTracker())

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "claude-code"
    assert providers["claude-code"].call_count == 1


def test_dead_auth_recorded_as_auth_invalid_in_attempts(isolated_universe_config):
    """Exhaustion diagnostics carry skip_class=auth_invalid for dead providers."""
    # Allowlist down to the two subscription writers so the dead-auth filter
    # empties the chain and the structured exhaustion error surfaces.
    runtime.universe_config = UniverseConfig(
        allowed_providers=["claude-code", "codex"],
    )
    router, providers = _router(dead={"claude-code", "codex"})

    with pytest.raises(AllProvidersExhaustedError) as exc:
        _run(router.call("writer", "p", "s"))

    attempts = exc.value.attempts or []
    auth_skips = {a.provider for a in attempts if a.skip_class == "auth_invalid"}
    assert auth_skips == {"claude-code", "codex"}
    for p in providers.values():
        assert p.call_count == 0


# ---------------------------------------------------------------------------
# Pinned writer: dead auth must fail loud (hard rule #8), never silent fallback
# ---------------------------------------------------------------------------


def test_pinned_dead_auth_writer_hard_fails(isolated_universe_config):
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})

    with pytest.raises(AllProvidersExhaustedError) as exc:
        _run(router.call("writer", "p", "s"))

    msg = str(exc.value)
    assert "claude-code" in msg
    assert "not_logged_in" in msg or "subscription login" in msg
    # No silent fallback to codex/local.
    for p in providers.values():
        assert p.call_count == 0


def test_pinned_healthy_writer_runs(isolated_universe_config):
    os.environ["TINYASSETS_PIN_WRITER"] = "codex"
    router, providers = _router(dead={"claude-code"})

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "codex"
    assert providers["codex"].call_count == 1
    assert providers["claude-code"].call_count == 0


# ---------------------------------------------------------------------------
# S5 round 5: a globally-dead subscription is NOT dead when the call's universe
# vault supplies per-universe auth — the router must reach provider.complete()
# with the vault env instead of starving bound BYO-key capacity.
# ---------------------------------------------------------------------------


def _byo_openai_universe(tmp_path):
    import base64

    from tinyassets.credential_vault import write_credential_vault

    udir = tmp_path / "u-byo-codex"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": base64.b64encode(b"sk-openai-test").decode("ascii"),
    }])
    return udir


def test_pinned_dead_auth_writer_runs_on_universe_vault_auth(
    isolated_universe_config, tmp_path,
):
    """The Codex repro: pinned codex + global not_logged_in + a per-universe BYO
    OpenAI key in the vault → provider.complete() IS reached (the vault env is
    applied at call time), instead of AllProvidersExhaustedError."""
    from tinyassets.providers.base import UniverseContext

    os.environ["TINYASSETS_BYO_VAULT_ENCRYPTED"] = "1"  # bypass is gated (F3)
    udir = _byo_openai_universe(tmp_path)
    os.environ["TINYASSETS_PIN_WRITER"] = "codex"
    router, providers = _router(dead={"codex"})

    resp = _run(router.call(
        "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
    ))
    assert resp.provider == "codex"
    assert providers["codex"].call_count == 1


def test_pinned_dead_auth_writer_without_vault_still_hard_fails(
    isolated_universe_config, tmp_path,
):
    """Inverse: no per-universe auth + global not_logged_in → still dropped and
    the pinned writer hard-fails (the gate is only bypassed for vault-backed
    providers)."""
    from tinyassets.providers.base import UniverseContext

    udir = tmp_path / "u-novault"
    udir.mkdir()
    os.environ["TINYASSETS_PIN_WRITER"] = "codex"
    router, providers = _router(dead={"codex"})

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    for p in providers.values():
        assert p.call_count == 0


def test_fallback_keeps_dead_auth_provider_with_universe_vault(
    isolated_universe_config, tmp_path,
):
    """Not pinned: codex is globally dead but the universe vault authenticates it
    → codex stays in the fallback chain and wins (not skipped). claude-code (dead,
    no vault) is still dropped."""
    from tinyassets.providers.base import UniverseContext

    os.environ["TINYASSETS_BYO_VAULT_ENCRYPTED"] = "1"  # bypass is gated (F3)
    udir = _byo_openai_universe(tmp_path)
    router, providers = _router(dead={"claude-code", "codex"})

    resp = _run(router.call(
        "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
    ))
    assert resp.provider == "codex"
    assert providers["codex"].call_count == 1
    assert providers["claude-code"].call_count == 0


def test_no_vault_behavior_unchanged_for_default_router(isolated_universe_config):
    """Flag-OFF / no-vault no-op: with no universe context and no global
    TINYASSETS_UNIVERSE, the auth-health gate behaves exactly as before —
    a dead pinned writer hard-fails."""
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call("writer", "p", "s"))
    for p in providers.values():
        assert p.call_count == 0


def test_legacy_subscription_only_universe_is_still_dropped(
    isolated_universe_config, tmp_path,
):
    """Codex F3 / Fable F1: a universe with ONLY a legacy llm_subscription row
    (the blocked custody lane) must NOT bypass the health gate — the bypass is
    BYO-API-key-only. Consistent with resolve_engine_binding=False."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.providers.base import UniverseContext

    udir = tmp_path / "u-legacy-sub"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription",
        "service": "codex",
        "oauth_token": "legacy-oauth",
    }])
    os.environ["TINYASSETS_PIN_WRITER"] = "codex"
    router, providers = _router(dead={"codex"})

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    for p in providers.values():
        assert p.call_count == 0


def test_health_bypass_probe_is_side_effect_free(isolated_universe_config, tmp_path):
    """Fable Finding C: the health probe must NOT materialize credential artifacts
    (auth.json / config.toml). resolve_llm_api_key is pure — assert no
    .credentials dir is created by the probe path."""
    from tinyassets.providers.router import _universe_provides_provider_auth

    os.environ["TINYASSETS_BYO_VAULT_ENCRYPTED"] = "1"  # bypass is gated (F3)
    udir = _byo_openai_universe(tmp_path)
    assert _universe_provides_provider_auth("codex", udir) is True
    # No credential-materialization side effect on a read/health path.
    assert not (udir / ".credentials").exists()


def test_byo_bypass_is_dark_when_encryption_gate_off(
    isolated_universe_config, tmp_path,
):
    """F3: direct BYO routing is DARK until the vault-encryption gate opens — with
    it OFF (default), even a BYO-keyed universe's dead-login provider is dropped
    (no bypass), so a pinned dead provider hard-fails."""
    from tinyassets.providers.base import UniverseContext
    from tinyassets.providers.router import _universe_provides_provider_auth

    os.environ.pop("TINYASSETS_BYO_VAULT_ENCRYPTED", None)  # encryption gate OFF
    udir = _byo_openai_universe(tmp_path)
    assert _universe_provides_provider_auth("codex", udir) is False

    os.environ["TINYASSETS_PIN_WRITER"] = "codex"
    router, providers = _router(dead={"codex"})
    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    for p in providers.values():
        assert p.call_count == 0


def test_byo_bypass_not_gated_on_non_ambient_flag(
    isolated_universe_config, tmp_path,
):
    """Within the encryption gate, the bypass is NOT further gated on the
    non-ambient flag: BYO gate ON + non-ambient OFF → the BYO-keyed universe's
    dead-login provider is KEPT (latent-bug fix)."""
    from tinyassets.providers.base import UniverseContext

    os.environ["TINYASSETS_BYO_VAULT_ENCRYPTED"] = "1"
    os.environ.pop("TINYASSETS_NON_AMBIENT_WORK", None)  # non-ambient OFF
    udir = _byo_openai_universe(tmp_path)
    router, providers = _router(dead={"claude-code", "codex"})

    resp = _run(router.call(
        "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
    ))
    assert resp.provider == "codex"
    assert providers["codex"].call_count == 1


# ---------------------------------------------------------------------------
# F1: a BYO-bound universe's WRITER never falls through to a platform provider
# ---------------------------------------------------------------------------


def _claude_bound_universe(tmp_path):
    import base64

    from tinyassets.config import write_universe_config_fields
    from tinyassets.credential_vault import write_credential_vault

    udir = tmp_path / "u-claude-bound"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(
            ("sk-ant-api03-" + "A" * 40).encode()).decode("ascii"),
    }])
    write_universe_config_fields(udir, engine_source="byo_api_key")
    return udir


def test_f1_byo_bound_universe_rejects_non_eligible_pinned_writer(
    isolated_universe_config, tmp_path,
):
    """F1: a BYO-bound (Anthropic → claude-code) universe pinned to codex
    hard-fails — a bound universe never borrows the platform's Codex auth, even
    when codex is globally healthy."""
    from tinyassets.providers.base import UniverseContext

    os.environ["TINYASSETS_BYO_VAULT_ENCRYPTED"] = "1"
    udir = _claude_bound_universe(tmp_path)
    os.environ["TINYASSETS_PIN_WRITER"] = "codex"
    router, providers = _router(dead=set())  # codex is globally healthy

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    assert providers["codex"].call_count == 0


def test_f1_byo_bound_universe_runs_only_eligible_provider(
    isolated_universe_config, tmp_path,
):
    """F1: a BYO-bound universe runs its eligible provider (claude-code) and does
    NOT fall through to any other provider even if claude-code's global login is
    dead (the BYO key authenticates it)."""
    from tinyassets.providers.base import UniverseContext

    os.environ["TINYASSETS_BYO_VAULT_ENCRYPTED"] = "1"
    udir = _claude_bound_universe(tmp_path)
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})  # global login dead

    resp = _run(router.call(
        "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
    ))
    assert resp.provider == "claude-code"
    assert providers["codex"].call_count == 0
    assert providers["ollama-local"].call_count == 0


# ---------------------------------------------------------------------------
# Policy routing + judge ensemble honour the same gate
# ---------------------------------------------------------------------------


def test_call_with_policy_skips_dead_auth(isolated_universe_config):
    router, providers = _router(dead={"claude-code"})
    policy = {
        "preferred": {"provider": "claude-code"},
        "fallback_chain": [{"provider": "codex"}],
    }

    _text, provider, _meta = _run(
        router.call_with_policy("writer", "p", "s", policy)
    )

    assert provider == "codex"
    assert providers["claude-code"].call_count == 0
    assert providers["codex"].call_count == 1


def test_judge_ensemble_skips_dead_auth_codex(isolated_universe_config):
    router, providers = _router(dead={"codex"})

    results = _run(router.call_judge_ensemble("p", "s"))

    used = {r.provider for r in results}
    assert "codex" not in used
    assert "ollama-local" in used  # 'unknown' -> kept
    assert providers["codex"].call_count == 0
