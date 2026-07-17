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
    monkeypatch.setattr(eb, "_vault_encryption_capability_attested", lambda *a, **k: True)
    monkeypatch.setattr(eb, "_sandbox_execution_attested", lambda: True)


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


def test_f1a_unknown_role_is_enforced_as_writer_route(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """F1a: an UNKNOWN role (a free-form model_hint that reached the router) aliases
    to the writer fallback chain, so it MUST be enforced too — a claude-only
    BYO-bound universe must NOT let a 'novelist' role reach platform codex."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = _byo_claude_universe(tmp_path)
    router, providers = _router(dead=set())  # codex globally healthy

    # role="novelist" is not in FALLBACK_CHAINS → gets the writer chain.
    resp = _run(router.call(
        "novelist", "p", "s", universe_context=UniverseContext(universe_dir=udir),
    ))
    assert resp.provider == "claude-code"
    assert providers["codex"].call_count == 0


def test_f1a_unknown_role_policy_naming_codex_is_refused(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """F1a + C1: an unknown role + a policy naming codex in a BYO-bound universe is
    REFUSED, never routed to platform codex."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = _byo_claude_universe(tmp_path)
    router, providers = _router(dead=set())
    policy = {"preferred": {"provider": "codex"},
              "fallback_chain": [{"provider": "ollama-local"}]}
    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call_with_policy(
            "novelist", "p", "s", policy,
            universe_context=UniverseContext(universe_dir=udir),
        ))
    assert providers["codex"].call_count == 0


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


# ---------------------------------------------------------------------------
# Round-12 review regressions (Codex r12)
# ---------------------------------------------------------------------------


def _byo_broken_claude_universe(tmp_path):
    """A DECLARED byo_api_key universe whose Anthropic key is malformed (nonempty
    but not a well-formed sk-ant- key)."""
    import base64

    from tinyassets.config import write_universe_config_fields
    from tinyassets.credential_vault import write_credential_vault

    udir = tmp_path / "u-byo-broken"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key", "service": "anthropic",
        "secret_b64": base64.b64encode(b"not-a-real-anthropic-key").decode("ascii"),
    }])
    write_universe_config_fields(udir, engine_source="byo_api_key")
    return udir


def test_r12_2_every_higher_precedence_auth_selector_scrubbed_from_byo_child(
    tmp_path, monkeypatch,
):
    """Round-12 #2: a BYO claude-code child is a POSITIVE auth allowlist — EVERY
    documented higher-precedence selector (Bedrock/Vertex flags, AWS/GCP creds,
    OAuth/auth tokens, config dir) is stripped; only the BYO key remains, and
    CLAUDE_CONFIG_DIR is an isolated empty dir (bare mode)."""
    from tinyassets.providers.base import subprocess_env_for_provider

    _enable_byo(monkeypatch)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    higher_precedence = {
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "CLAUDE_CODE_USE_VERTEX": "1",
        "AWS_ACCESS_KEY_ID": "AKIA",
        "AWS_SECRET_ACCESS_KEY": "s",
        "AWS_SESSION_TOKEN": "t",
        "AWS_PROFILE": "p",
        "AWS_BEARER_TOKEN_BEDROCK": "b",
        "ANTHROPIC_AUTH_TOKEN": "tok",
        "ANTHROPIC_BASE_URL": "http://x",
        "CLAUDE_CODE_OAUTH_TOKEN": "oauth",
        "GOOGLE_APPLICATION_CREDENTIALS": "/g.json",
        "GOOGLE_CLOUD_PROJECT": "proj",
        "CLOUD_ML_REGION": "us",
        "VERTEX_REGION": "us",
    }
    for k, v in higher_precedence.items():
        monkeypatch.setenv(k, v)
    udir = _byo_claude_universe(tmp_path)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(udir))

    env = subprocess_env_for_provider("claude-code", universe_dir=udir)

    survivors = [k for k in higher_precedence if k in env]
    assert not survivors, f"higher-precedence auth selectors survived: {survivors}"
    assert env["ANTHROPIC_API_KEY"].startswith("sk-ant-")  # only the BYO key
    assert "claude-byo-isolated" in env.get("CLAUDE_CONFIG_DIR", "")


def test_r12_3_router_pins_one_byo_snapshot_across_spawn(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """Round-12 #3: the router pins ONE byo_execution_enabled() snapshot for the
    whole call. A mid-call attestation flip (True→False) cannot let route
    selection constrain to the BYO writer while the spawn sees byo OFF (which
    would restore platform auth). The provider observes the pinned value at spawn."""
    import tinyassets.engine_binding as eb
    from tinyassets.providers.base import UniverseContext

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setattr(eb, "_sandbox_execution_attested", lambda: True)
    # Per-record attestation is True only on the FIRST read; every later read flips
    # False (the TOCTOU race the pin must neutralize).
    calls = {"n": 0}

    def _flip(*a, **k):
        calls["n"] += 1
        return calls["n"] <= 1

    monkeypatch.setattr(eb, "_vault_encryption_capability_attested", _flip)
    udir = _byo_claude_universe(tmp_path)

    observed: dict[str, bool] = {}

    class _ObservingClaude(BaseProvider):
        name = "claude-code"
        family = "anthropic"

        async def complete(self, prompt, system, config, *, universe_dir=None):
            observed["byo_at_spawn"] = eb.byo_execution_enabled()
            return ProviderResponse(
                text="ok", provider="claude-code", model="m",
                family="anthropic", latency_ms=0.0,
            )

    providers = {
        "claude-code": _ObservingClaude(),
        "codex": _FakeProvider("codex"),
        "ollama-local": _FakeProvider("ollama-local"),
    }
    router = ProviderRouter(providers=providers, quota=QuotaTracker())
    resp = _run(router.call(
        "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
    ))
    assert resp.provider == "claude-code"
    # The spawn saw the PINNED route-time snapshot (True), not the flipped-False
    # live value — no TOCTOU restore of platform auth.
    assert observed["byo_at_spawn"] is True


def test_r12_4_declared_byo_lane_with_broken_key_fails_closed(
    isolated_universe_config, tmp_path, monkeypatch,
):
    """Round-12 #4: a DECLARED byo_api_key lane whose key is malformed is
    MISCONFIGURED, not unbound — the writer route FAILS CLOSED (never leaves the
    full platform fallback chain / borrows platform capacity)."""
    from tinyassets.providers.base import UniverseContext

    _enable_byo(monkeypatch)
    udir = _byo_broken_claude_universe(tmp_path)
    router, providers = _router(dead=set())  # every platform provider healthy

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call(
            "writer", "p", "s", universe_context=UniverseContext(universe_dir=udir),
        ))
    # No platform provider was borrowed.
    for name, provider in providers.items():
        assert provider.call_count == 0, f"{name} should not have been called"


# ---------------------------------------------------------------------------
# Round-13 review regressions (Codex r13)
# ---------------------------------------------------------------------------


def test_r13_1_byo_child_scrubs_full_oauth_family_and_sets_subprocess_scrub(
    tmp_path, monkeypatch,
):
    """Round-13 #1 (env layer): a BYO claude child scrubs the WHOLE
    CLAUDE_CODE_OAUTH_* family (not just the exact _TOKEN name — the r12 gap that
    let CLAUDE_CODE_OAUTH_REFRESH_TOKEN survive) and sets CLAUDE_CODE_SUBPROCESS_ENV_SCRUB
    so the key never reaches the CLI's own tool subprocesses."""
    from tinyassets.providers.base import subprocess_env_for_provider

    _enable_byo(monkeypatch)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    for var in (
        "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
        "CLAUDE_CODE_OAUTH_ACCESS_TOKEN",
    ):
        monkeypatch.setenv(var, "host-" + var)
    udir = _byo_claude_universe(tmp_path)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(udir))

    env = subprocess_env_for_provider("claude-code", universe_dir=udir)

    survivors = [k for k in env if k.startswith("CLAUDE_CODE_OAUTH_")]
    assert not survivors, f"OAuth family survived: {survivors}"
    assert env.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") == "1"
    assert env["ANTHROPIC_API_KEY"].startswith("sk-ant-")


def test_r13_1_byo_claude_cli_is_credential_isolated(tmp_path, monkeypatch):
    """Round-13 #1 (real CLI harness): spawn the hardened `claude -p` through a
    STUB claude that records its argv + env. Prove the launch is `--bare` with a
    shell-escape tool floor, the subprocess-env scrub is on, and NEITHER host OAuth
    NOR host cloud creds reach the child (so Bash/hooks/MCP started by the CLI can
    read neither the founder key nor host credentials)."""
    import asyncio as _asyncio
    import json as _json
    import sys as _sys
    import textwrap as _textwrap
    from pathlib import Path

    from tinyassets.providers import claude_provider as cp
    from tinyassets.providers.base import ModelConfig

    dump = tmp_path / "claude_invocation.json"
    stub = tmp_path / "claude_stub.py"
    stub.write_text(_textwrap.dedent(f"""
        import sys, os, json
        sys.stdin.buffer.read()  # drain the piped prompt
        json.dump({{"argv": sys.argv[1:], "env": dict(os.environ),
                    "cwd": os.getcwd()}},
                  open(r"{dump}", "w", encoding="utf-8"))
        sys.stdout.write("ok")
    """), encoding="utf-8")
    # Route the provider at our stub instead of the real claude binary.
    monkeypatch.setattr(
        cp, "_resolve_claude_cmd", lambda: ([_sys.executable, str(stub)], False),
    )
    _enable_byo(monkeypatch)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    # Host credentials in the parent env that must NOT reach the BYO child.
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "host-oauth")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "host-refresh")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "host-aws")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "host-auth-token")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "host-claude"))
    udir = _byo_claude_universe(tmp_path)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(udir))

    _asyncio.run(cp.ClaudeProvider().complete(
        "hello", "", ModelConfig(timeout=30), universe_dir=udir,
    ))
    data = _json.loads(dump.read_text(encoding="utf-8"))
    argv, child_env, child_cwd = data["argv"], data["env"], data["cwd"]

    # Clean bare context.
    assert "--bare" in argv
    # DEFAULT-DENY tool floor (round-14 #2): not just Bash — file Read/Edit/Write
    # are denied too (--bare alone still permits them).
    assert "--disallowedTools" in argv
    for denied in ("Bash", "Read", "Edit", "Write", "WebFetch"):
        assert denied in argv, f"{denied} not in the default-deny tool floor"
    # cwd is pinned to an isolated scratch dir (round-14 #2), NOT the daemon cwd.
    assert "claude-byo-scratch" in child_cwd
    assert Path(child_cwd).resolve() != Path.cwd().resolve()
    # The CLI keeps the key out of its OWN tool subprocesses.
    assert child_env.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") == "1"
    # Neither host OAuth nor host cloud creds reached the child.
    for host_cred in (
        "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
        "AWS_SECRET_ACCESS_KEY", "ANTHROPIC_AUTH_TOKEN",
    ):
        assert host_cred not in child_env, f"{host_cred} leaked into the BYO child"
    # The child's ONLY Anthropic credential is the founder's BYO key + isolated cfg.
    assert child_env.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-")
    assert "claude-byo-isolated" in child_env.get("CLAUDE_CONFIG_DIR", "")


@pytest.mark.skip(reason=(
    "ROLLOUT GATE (round-14 #2): a hostile real-CLI filesystem test — spawn the "
    "REAL `claude -p` hardened for BYO and assert Read/Edit of a host file FAILS — "
    "requires the actual claude binary (absent in this env) AND the per-job runner's "
    "OS sandbox. BYO execution stays dark (sandbox attestation False) until both "
    "land; enable + implement this at Phase-2 rollout. The stub test above proves "
    "our CODE emits --bare + default-deny + cwd-pin; it cannot prove the binary's "
    "real filesystem enforcement."
))
def test_r14_2_byo_hostile_real_cli_filesystem_isolation():  # pragma: no cover
    raise NotImplementedError("Phase-2 rollout gate — see skip reason.")


@pytest.mark.parametrize("lane", ["market_rented", "host_daemon", "self_hosted_endpoint"])
def test_r13_2_switch_away_from_byo_stops_key_injection(tmp_path, monkeypatch, lane):
    """Round-13 #2: after switching AWAY from BYO to a runtime-backed lane, the
    retained vault key is NOT injected at spawn (the field-clear alone was not
    enough — injection re-reads the key independently of engine_source). No BYO key
    and no byo-hardening signal reach the child."""
    import base64

    from tinyassets.credential_vault import provider_auth_env_overrides
    from tinyassets.providers.base import subprocess_env_for_provider

    _enable_byo(monkeypatch)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    udir = tmp_path / f"u-switch-{lane}"
    udir.mkdir()
    (udir / "config.yaml").write_text(f"engine_source: {lane}\n", encoding="utf-8")
    from tinyassets.credential_vault import write_credential_vault
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key", "service": "anthropic",
        "secret_b64": base64.b64encode(
            ("sk-ant-api03-" + "A" * 40).encode()).decode("ascii"),
    }])
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(udir))

    assert "ANTHROPIC_API_KEY" not in provider_auth_env_overrides(udir, "claude-code")
    env = subprocess_env_for_provider("claude-code", universe_dir=udir)
    assert "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB" not in env  # not byo-bound → not hardened


def test_r13_2_byo_lane_still_injects_after_the_guard(tmp_path, monkeypatch):
    """Guard the guard: an actual byo_api_key lane STILL injects the key (the
    lane-aware check must not over-block the sanctioned lane)."""
    from tinyassets.credential_vault import provider_auth_env_overrides

    _enable_byo(monkeypatch)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    udir = _byo_claude_universe(tmp_path)  # engine_source=byo_api_key + valid key
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(udir))
    assert "ANTHROPIC_API_KEY" in provider_auth_env_overrides(udir, "claude-code")
