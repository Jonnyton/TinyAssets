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
# BYO-bound universe: the router must reach provider.complete() on the vault
# key (claude-code ONLY — Codex BYO is not executable) instead of starving it,
# AND never fall through to a platform-auth provider (C1). BYO execution requires
# the vault-encryption ATTESTATION (DARK by default — C4).
# ---------------------------------------------------------------------------


def _enable_byo(monkeypatch):
    """Simulate Phase-2: executable BYO on (flag + code-backed attestation)."""
    import tinyassets.engine_binding as eb

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setattr(eb, "_vault_encryption_capability_attested", lambda: True)


def _byo_claude_universe(tmp_path):
    import base64

    from tinyassets.config import write_universe_config_fields
    from tinyassets.credential_vault import write_credential_vault

    udir = tmp_path / "u-byo-claude"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(
            ("sk-ant-api03-" + "A" * 40).encode()).decode("ascii"),
    }])
    write_universe_config_fields(udir, engine_source="byo_api_key")
    return udir


def test_pinned_dead_auth_writer_runs_on_universe_vault_auth(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """Pinned claude-code + global not_logged_in + a per-universe BYO Anthropic
    key → provider.complete() IS reached (the vault key authenticates it),
    instead of AllProvidersExhaustedError."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = _byo_claude_universe(tmp_path)
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})

    resp = _run(router.call(
        "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
    ))
    assert resp.provider == "claude-code"
    assert providers["claude-code"].call_count == 1


def test_pinned_dead_auth_writer_without_vault_still_hard_fails(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """Inverse: no per-universe auth + global not_logged_in → still dropped and
    the pinned writer hard-fails (the gate is only bypassed for vault-backed
    providers)."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = tmp_path / "u-novault"
    udir.mkdir()
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    for p in providers.values():
        assert p.call_count == 0


def test_no_vault_behavior_unchanged_for_default_router(isolated_universe_config):
    """No-vault no-op: with no universe context and no global TINYASSETS_UNIVERSE,
    the auth-health gate behaves exactly as before — a dead pinned writer
    hard-fails."""
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call("writer", "p", "s"))
    for p in providers.values():
        assert p.call_count == 0


def test_legacy_subscription_only_universe_is_still_dropped(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """A universe with ONLY a legacy llm_subscription row (the blocked custody
    lane) must NOT bypass the health gate — the bypass is BYO-API-key-only."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = tmp_path / "u-legacy-sub"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription",
        "service": "claude",
        "oauth_token": "legacy-oauth",
    }])
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    for p in providers.values():
        assert p.call_count == 0


def test_codex_byo_is_not_bypassed(isolated_universe_config, tmp_path, monkeypatch):
    """C2: a Codex/OpenAI BYO key is NOT executable — the router bypass never
    keeps codex on a BYO key (only claude-code is BYO-executable)."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.providers.router import _universe_provides_provider_auth

    _enable_byo(monkeypatch)
    udir = tmp_path / "u-openai"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": __import__("base64").b64encode(b"sk-openai").decode("ascii"),
    }])
    assert _universe_provides_provider_auth("codex", udir) is False


def test_health_bypass_probe_is_side_effect_free(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """Fable Finding C: the health probe must NOT materialize credential artifacts
    (auth.json / config.toml). resolve_llm_api_key is pure — assert no
    .credentials dir is created by the probe path."""
    from tinyassets.providers.router import _universe_provides_provider_auth

    _enable_byo(monkeypatch)
    udir = _byo_claude_universe(tmp_path)
    assert _universe_provides_provider_auth("claude-code", udir) is True
    # No credential-materialization side effect on a read/health path.
    assert not (udir / ".credentials").exists()


def test_byo_bypass_is_dark_when_encryption_gate_off(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """C4: direct BYO routing is DARK until the encryption ATTESTATION passes —
    with the flag alone (no attestation), a BYO-keyed universe's dead-login
    provider is dropped (no bypass), so a pinned dead provider hard-fails."""
    from tinyassets.providers.base import UniverseContext
    from tinyassets.providers.router import _universe_provides_provider_auth

    os.environ["TINYASSETS_BYO_VAULT_ENCRYPTED"] = "1"  # flag on, attestation NOT patched
    udir = _byo_claude_universe(tmp_path)
    assert _universe_provides_provider_auth("claude-code", udir) is False

    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})
    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    for p in providers.values():
        assert p.call_count == 0


def test_byo_bypass_not_gated_on_non_ambient_flag(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """Within the encryption gate, the bypass is NOT further gated on the
    non-ambient flag: BYO on + non-ambient OFF → the BYO-keyed universe's
    dead-login provider is KEPT (latent-bug fix)."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    os.environ.pop("TINYASSETS_NON_AMBIENT_WORK", None)  # non-ambient OFF
    udir = _byo_claude_universe(tmp_path)
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})

    resp = _run(router.call(
        "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
    ))
    assert resp.provider == "claude-code"
    assert providers["claude-code"].call_count == 1


# ---------------------------------------------------------------------------
# C1: a BYO-bound universe's WRITER never falls through to a platform provider —
# covered on EVERY writer route incl. the env-only (untedhread) identity path.
# ---------------------------------------------------------------------------


def test_f1_byo_bound_universe_rejects_non_eligible_pinned_writer(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """C1: a BYO-bound (Anthropic → claude-code) universe pinned to codex
    hard-fails — a bound universe never borrows the platform's Codex auth, even
    when codex is globally healthy."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = _byo_claude_universe(tmp_path)
    os.environ["TINYASSETS_PIN_WRITER"] = "codex"
    router, providers = _router(dead=set())  # codex is globally healthy

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    assert providers["codex"].call_count == 0


def test_f1_env_only_universe_writer_does_not_reach_codex(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """C1 (Fable repro): the constraint covers the UNTHREADED identity path — a
    cloud-worker child with only TINYASSETS_UNIVERSE set (no universe_context) and
    a claude-only BYO binding must NOT let a claude cooldown/fallback reach codex."""
    _enable_byo(monkeypatch)
    udir = _byo_claude_universe(tmp_path)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(udir))  # env-only identity
    router, providers = _router(dead=set())  # not pinned; codex globally healthy

    # No universe_context threaded — the constraint must resolve via env.
    resp = _run(router.call("writer", "p", "s"))
    assert resp.provider == "claude-code"
    assert providers["codex"].call_count == 0
    assert providers["ollama-local"].call_count == 0


def test_f1_policy_naming_codex_in_byo_bound_universe_is_refused(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """C1: the SAME constraint covers call_with_policy — a policy naming codex in a
    claude-only BYO-bound universe is REFUSED, never routed to platform codex."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = _byo_claude_universe(tmp_path)
    router, providers = _router(dead=set())
    policy = {
        "preferred": {"provider": "codex"},
        "fallback_chain": [{"provider": "ollama-local"}],
    }
    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call_with_policy(
            "writer", "p", "s", policy,
            universe_context=UniverseContext(universe_dir=udir),
        ))
    assert providers["codex"].call_count == 0


def test_f1_byo_bound_universe_runs_only_eligible_provider(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """C1: a BYO-bound universe runs its eligible provider (claude-code) and does
    NOT fall through to any other provider even if claude-code's global login is
    dead (the BYO key authenticates it)."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = _byo_claude_universe(tmp_path)
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
