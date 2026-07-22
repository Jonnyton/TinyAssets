"""Per-universe engine resolution via an EXPLICIT ``universe_context`` argument.

This is the router/provider/vault-layer proof for option (b): a single daemon
process serving interleaved calls for two different universes must resolve each
call's engine preference/ceiling AND credential-vault API key from the
``universe_context`` threaded
on the call stack — NOT from the process-global ``runtime.universe_config`` /
``TINYASSETS_UNIVERSE``.

The globals are deliberately pinned to a third, wrong universe for the whole test. Before the
change the router has no ``universe_context`` parameter and every call bleeds to
that global. Explicit A/B calls must be served by their own singleton provider
and BYO key, even while the globals point elsewhere and the sync wrappers hop through a
ThreadPoolExecutor (the context must survive the pool hop via explicit
capture, never a ContextVar).
"""

from __future__ import annotations

import base64
import concurrent.futures
import threading
from pathlib import Path

import pytest

from tinyassets import runtime_singletons as runtime
from tinyassets.config import load_universe_config, write_universe_config_fields
from tinyassets.credential_vault import write_credential_vault
from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
    subprocess_env_for_provider,
)
from tinyassets.providers.router import ProviderRouter


class _RecordingProvider(BaseProvider):
    """Fake provider that resolves auth via the REAL vault-backed env helper.

    ``complete`` calls the real ``subprocess_env_for_provider(self.name,
    universe_dir=universe_dir)`` and packs what it observed into the response so
    each call can be correlated with the universe it was routed for:

    - ``text``   = the ``universe_dir`` it saw (or ``None``)
    - ``model``  = the resolved API key the vault produced for that universe
    """

    def __init__(
        self,
        name: str,
        family: str,
        auth_env_key: str,
        *,
        overlap_barrier: threading.Barrier | None = None,
        unavailable: bool = False,
    ) -> None:
        self.name = name
        self.family = family
        self._auth_env_key = auth_env_key
        self._overlap_barrier = overlap_barrier
        self._unavailable = unavailable
        self.observed_envs: list[dict[str, str]] = []

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        if self._overlap_barrier is not None:
            self._overlap_barrier.wait(timeout=5)
        env = subprocess_env_for_provider(self.name, universe_dir=universe_dir)
        self.observed_envs.append(dict(env))
        if self._unavailable:
            raise ProviderUnavailableError(f"injected {self.name} failure")
        return ProviderResponse(
            text=str(universe_dir),
            provider=self.name,
            model=env.get(self._auth_env_key, ""),
            family=self.family,
            latency_ms=1.0,
        )


def _write_codex_universe(root: Path) -> tuple[Path, str]:
    """Universe A: singleton Codex ceiling + its own OpenAI API key."""
    root.mkdir(parents=True, exist_ok=True)
    write_universe_config_fields(
        root,
        preferred_writer="codex",
        allowed_providers=["codex"],
        engine_assignment_state="ready",
    )
    api_key = "sk-openai-universe-a"
    write_credential_vault(
        root,
        [
            {
                "credential_type": "llm_api_key",
                "service": "openai",
                "secret_b64": base64.b64encode(api_key.encode()).decode(),
            }
        ],
    )
    return root, api_key


def _write_claude_universe(root: Path) -> tuple[Path, str]:
    """Universe B: singleton Claude ceiling + its own Anthropic API key."""
    root.mkdir(parents=True, exist_ok=True)
    write_universe_config_fields(
        root,
        preferred_writer="claude-code",
        allowed_providers=["claude-code"],
        engine_assignment_state="ready",
    )
    api_key = "sk-anthropic-universe-b"
    write_credential_vault(
        root,
        [
            {
                "credential_type": "llm_api_key",
                "service": "anthropic",
                "secret_b64": base64.b64encode(api_key.encode()).decode(),
            }
        ],
    )
    return root, api_key


def _write_wrong_global_universe(root: Path) -> Path:
    """Third universe: deliberately ineligible route and unrelated keys."""
    root.mkdir(parents=True, exist_ok=True)
    write_universe_config_fields(
        root,
        preferred_writer="ollama-local",
        allowed_providers=["ollama-local"],
        engine_assignment_state="ready",
    )
    write_credential_vault(
        root,
        [
            {
                "credential_type": "llm_api_key",
                "service": "openai",
                "secret_b64": base64.b64encode(b"wrong-global-openai").decode(),
            },
            {
                "credential_type": "llm_api_key",
                "service": "anthropic",
                "secret_b64": base64.b64encode(b"wrong-global-anthropic").decode(),
            },
        ],
    )
    return root


@pytest.fixture
def _pinned_to_wrong_global(tmp_path, monkeypatch):
    """Build two target universes; pin every process global to a third one."""
    universe_a, openai_key = _write_codex_universe(tmp_path / "universe_a")
    universe_b, anthropic_key = _write_claude_universe(tmp_path / "universe_b")
    wrong_global = _write_wrong_global_universe(tmp_path / "wrong_global")

    # Explicit-universe isolation applies even when the host opts into its own
    # keys. These ambient values must not survive into either child env.
    monkeypatch.delenv("TINYASSETS_PIN_WRITER", raising=False)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-host-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-host-anthropic")
    monkeypatch.setenv("CODEX_HOME", "/ambient/host/codex")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/ambient/host/claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ambient-host-oauth")

    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(wrong_global))
    saved_config = runtime.universe_config
    runtime.universe_config = load_universe_config(wrong_global)
    try:
        yield {
            "a": universe_a,
            "b": universe_b,
            "global": wrong_global,
            "openai_key": openai_key,
            "anthropic_key": anthropic_key,
        }
    finally:
        runtime.universe_config = saved_config


def test_call_sync_resolves_engine_and_auth_per_universe_context(
    _pinned_to_wrong_global,
):
    fixt = _pinned_to_wrong_global
    universe_a = fixt["a"]
    universe_b = fixt["b"]
    openai_key = fixt["openai_key"]
    anthropic_key = fixt["anthropic_key"]

    router = ProviderRouter()
    router.register(_RecordingProvider("codex", "openai", "OPENAI_API_KEY"))
    router.register(
        _RecordingProvider("claude-code", "anthropic", "ANTHROPIC_API_KEY")
    )

    ctx_a = UniverseContext(
        universe_dir=universe_a, config=load_universe_config(universe_a)
    )
    ctx_b = UniverseContext(
        universe_dir=universe_b, config=load_universe_config(universe_b)
    )

    # 24 interleaved calls: even index -> A, odd index -> B.
    plan = [("a", ctx_a) if i % 2 == 0 else ("b", ctx_b) for i in range(24)]

    def _worker(item):
        label, ctx = item
        resp = router.call_sync(
            role="writer",
            prompt=f"prompt-{label}",
            system="system",
            universe_context=ctx,
        )
        return label, resp

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_worker, plan))

    a_count = 0
    b_count = 0
    for label, resp in results:
        if label == "a":
            a_count += 1
            assert resp.provider == "codex", (
                f"A-context call must be served by codex, got {resp.provider!r}"
            )
            assert resp.text == str(universe_a), (
                f"codex must see universe_dir==A, saw {resp.text!r}"
            )
            assert resp.model == openai_key, (
                f"codex must resolve A's OPENAI_API_KEY, got {resp.model!r}"
            )
        else:
            b_count += 1
            assert resp.provider == "claude-code", (
                f"B-context call must be served by claude-code, got {resp.provider!r}"
            )
            assert resp.text == str(universe_b), (
                f"claude-code must see universe_dir==B, saw {resp.text!r}"
            )
            assert resp.model == anthropic_key, (
                f"claude-code must resolve B's ANTHROPIC_API_KEY, got {resp.model!r}"
            )

    assert a_count == 12
    assert b_count == 12


def test_call_provider_forwards_universe_context(
    _pinned_to_wrong_global, monkeypatch,
):
    """The call.py bridge threads universe_context through to call_sync."""
    from tinyassets.providers import call as call_module

    fixt = _pinned_to_wrong_global
    ctx_b = UniverseContext(
        universe_dir=fixt["b"], config=load_universe_config(fixt["b"])
    )

    router = ProviderRouter()
    router.register(_RecordingProvider("codex", "openai", "OPENAI_API_KEY"))
    router.register(
        _RecordingProvider("claude-code", "anthropic", "ANTHROPIC_API_KEY")
    )

    # conftest force-mocks call_provider globally; disable it so the real
    # router path (which threads universe_context) runs for this test.
    saved_mock = call_module.is_force_mock()
    saved = call_module.get_provider_router()
    call_module.set_force_mock(False)
    call_module.set_provider_router(router)
    try:
        text = call_module.call_provider(
            "prompt-b",
            "system",
            role="writer",
            universe_context=ctx_b,
        )
    finally:
        call_module.set_provider_router(saved)
        call_module.set_force_mock(saved_mock)

    # B-context routed to claude-code, which saw universe_dir==B.
    assert text == str(fixt["b"])
    assert call_module.get_last_provider() == "claude-code"


def test_overlapping_explicit_contexts_use_only_their_byo_key_and_ceiling(
    _pinned_to_wrong_global,
):
    """Two truly overlapping calls ignore a third universe and ambient auth."""
    fixt = _pinned_to_wrong_global
    barrier = threading.Barrier(2)
    codex = _RecordingProvider(
        "codex", "openai", "OPENAI_API_KEY", overlap_barrier=barrier,
    )
    claude = _RecordingProvider(
        "claude-code", "anthropic", "ANTHROPIC_API_KEY",
        overlap_barrier=barrier,
    )
    router = ProviderRouter()
    router.register(codex)
    router.register(claude)

    ctx_a = UniverseContext(
        universe_dir=fixt["a"], config=load_universe_config(fixt["a"]),
    )
    ctx_b = UniverseContext(
        universe_dir=fixt["b"], config=load_universe_config(fixt["b"]),
    )

    def invoke(ctx: UniverseContext) -> ProviderResponse:
        return router.call_sync(
            "writer", "overlap", "system", universe_context=ctx,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(invoke, ctx_a)
        future_b = pool.submit(invoke, ctx_b)
        response_a = future_a.result(timeout=10)
        response_b = future_b.result(timeout=10)

    assert (response_a.provider, response_a.model) == (
        "codex", fixt["openai_key"],
    )
    assert (response_b.provider, response_b.model) == (
        "claude-code", fixt["anthropic_key"],
    )
    assert len(codex.observed_envs) == 1
    assert len(claude.observed_envs) == 1

    codex_env = codex.observed_envs[0]
    claude_env = claude.observed_envs[0]
    assert codex_env["OPENAI_API_KEY"] == fixt["openai_key"]
    assert "ANTHROPIC_API_KEY" not in codex_env
    assert "CLAUDE_CONFIG_DIR" not in codex_env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in codex_env
    assert claude_env["ANTHROPIC_API_KEY"] == fixt["anthropic_key"]
    assert "OPENAI_API_KEY" not in claude_env
    assert "CODEX_HOME" not in claude_env


def test_overlapping_selected_provider_failure_never_crosses_key_or_ceiling(
    _pinned_to_wrong_global,
):
    """One selected provider may fail without reaching the other universe."""
    fixt = _pinned_to_wrong_global
    barrier = threading.Barrier(2)
    codex = _RecordingProvider(
        "codex",
        "openai",
        "OPENAI_API_KEY",
        overlap_barrier=barrier,
        unavailable=True,
    )
    claude = _RecordingProvider(
        "claude-code",
        "anthropic",
        "ANTHROPIC_API_KEY",
        overlap_barrier=barrier,
    )
    router = ProviderRouter()
    router.register(codex)
    router.register(claude)
    ctx_a = UniverseContext(
        universe_dir=fixt["a"], config=load_universe_config(fixt["a"]),
    )
    ctx_b = UniverseContext(
        universe_dir=fixt["b"], config=load_universe_config(fixt["b"]),
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        failed_a = pool.submit(
            router.call_sync,
            "writer",
            "overlap-failure",
            "system",
            universe_context=ctx_a,
        )
        successful_b = pool.submit(
            router.call_sync,
            "writer",
            "overlap-success",
            "system",
            universe_context=ctx_b,
        )
        with pytest.raises(AllProvidersExhaustedError):
            failed_a.result(timeout=10)
        response_b = successful_b.result(timeout=10)

    assert (response_b.provider, response_b.model) == (
        "claude-code", fixt["anthropic_key"],
    )
    assert len(codex.observed_envs) == 1
    assert len(claude.observed_envs) == 1
    codex_env = codex.observed_envs[0]
    claude_env = claude.observed_envs[0]
    assert codex_env["OPENAI_API_KEY"] == fixt["openai_key"]
    assert "ANTHROPIC_API_KEY" not in codex_env
    assert "CLAUDE_CONFIG_DIR" not in codex_env
    assert claude_env["ANTHROPIC_API_KEY"] == fixt["anthropic_key"]
    assert "OPENAI_API_KEY" not in claude_env
    assert "CODEX_HOME" not in claude_env
