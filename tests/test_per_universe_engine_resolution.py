"""Per-universe engine resolution via an EXPLICIT ``universe_context`` argument.

This is the router/provider/vault-layer proof for option (b): a single daemon
process serving interleaved calls for two different universes must resolve each
call's engine preference (``preferred_writer``) AND credential-vault auth
(``CODEX_HOME`` / ``CLAUDE_CODE_OAUTH_TOKEN``) from the ``universe_context``
threaded
on the call stack — NOT from the process-global ``runtime.universe_config`` /
``TINYASSETS_UNIVERSE``.

The globals are deliberately pinned to universe A for the whole test. Before the
change the router has no ``universe_context`` parameter and every call bleeds to
A's global (A's preferred writer + A's vault auth). After the change, B-context
calls must be served by B's preferred writer with B's vault auth, even while the
globals still point at A and even though the sync wrappers hop through a
ThreadPoolExecutor (the context must survive the pool hop via explicit
capture, never a ContextVar).
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest

from tinyassets import runtime_singletons as runtime
from tinyassets.config import load_universe_config
from tinyassets.credential_broker import deposit_credential
from tinyassets.credentials import SecretKind
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
    - ``model``  = the resolved auth env var (``CODEX_HOME`` /
      ``CLAUDE_CONFIG_DIR``) the vault produced for that universe_dir
    """

    def __init__(self, name: str, family: str, auth_env_key: str) -> None:
        self.name = name
        self.family = family
        self._auth_env_key = auth_env_key

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        env = subprocess_env_for_provider(self.name, universe_dir=universe_dir)
        return ProviderResponse(
            text=str(universe_dir),
            provider=self.name,
            model=env.get(self._auth_env_key, ""),
            family=self.family,
            latency_ms=1.0,
        )


def _write_codex_universe(root: Path) -> tuple[Path, str]:
    """Universe A: preferred_writer=codex + a vaulted codex auth bundle.

    The broker materializes the bundle to ``<universe>/.engine-auth/codex``
    at env-overlay time, so CODEX_HOME is per-universe by construction.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.yaml").write_text("preferred_writer: codex\n", encoding="utf-8")
    deposit_credential(
        universe_id=root.name, founder_id="founder-a", provider="codex",
        destination="cli_subprocess", purpose="engine_auth",
        kind=SecretKind.OAUTH2_GENERIC, value=b"{}",
    )
    codex_home = str(root / ".engine-auth" / "codex")
    return root, codex_home


def _write_claude_universe(root: Path) -> tuple[Path, str]:
    """Universe B: preferred_writer=claude-code + a vaulted OAuth token."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.yaml").write_text(
        "preferred_writer: claude-code\n", encoding="utf-8"
    )
    deposit_credential(
        universe_id=root.name, founder_id="founder-b", provider="claude",
        destination="cli_subprocess", purpose="engine_auth",
        kind=SecretKind.OAUTH2_GENERIC, value=b"tok-universe-b",
    )
    return root, "tok-universe-b"


@pytest.fixture
def _pinned_to_universe_a(platform_vault_env, tmp_path, monkeypatch):
    """Build two universes and pin ALL process globals to universe A."""
    universe_a, codex_home = _write_codex_universe(tmp_path / "universe_a")
    universe_b, claude_cfg = _write_claude_universe(tmp_path / "universe_b")

    # Neither a hard writer pin nor api-key opt-in should interfere.
    monkeypatch.delenv("TINYASSETS_PIN_WRITER", raising=False)
    monkeypatch.delenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", raising=False)

    # Pin the process globals to universe A — this is the whole point: the
    # per-call universe_context must override these, not read from them.
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(universe_a))
    saved_config = runtime.universe_config
    runtime.universe_config = load_universe_config(universe_a)
    try:
        yield {
            "a": universe_a,
            "b": universe_b,
            "codex_home": codex_home,
            "claude_cfg": claude_cfg,
        }
    finally:
        runtime.universe_config = saved_config


def test_call_sync_resolves_engine_and_auth_per_universe_context(
    _pinned_to_universe_a,
):
    fixt = _pinned_to_universe_a
    universe_a = fixt["a"]
    universe_b = fixt["b"]
    codex_home = fixt["codex_home"]
    claude_cfg = fixt["claude_cfg"]

    router = ProviderRouter()
    router.register(_RecordingProvider("codex", "openai", "CODEX_HOME"))
    router.register(_RecordingProvider("claude-code", "anthropic", "CLAUDE_CODE_OAUTH_TOKEN"))

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
            assert resp.model == str(codex_home), (
                f"codex must resolve A's CODEX_HOME, got {resp.model!r}"
            )
        else:
            b_count += 1
            assert resp.provider == "claude-code", (
                f"B-context call must be served by claude-code, got {resp.provider!r}"
            )
            assert resp.text == str(universe_b), (
                f"claude-code must see universe_dir==B, saw {resp.text!r}"
            )
            assert resp.model == str(claude_cfg), (
                f"claude-code must resolve B's vaulted OAuth token, got {resp.model!r}"
            )

    assert a_count == 12
    assert b_count == 12


def test_call_provider_forwards_universe_context(_pinned_to_universe_a, monkeypatch):
    """The call.py bridge threads universe_context through to call_sync."""
    from tinyassets.providers import call as call_module

    fixt = _pinned_to_universe_a
    ctx_b = UniverseContext(
        universe_dir=fixt["b"], config=load_universe_config(fixt["b"])
    )

    router = ProviderRouter()
    router.register(_RecordingProvider("codex", "openai", "CODEX_HOME"))
    router.register(_RecordingProvider("claude-code", "anthropic", "CLAUDE_CODE_OAUTH_TOKEN"))

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
