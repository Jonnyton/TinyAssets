"""Per-universe engine resolution via an EXPLICIT ``universe_context`` argument.

The router/provider/vault-layer proof for option (b): a single daemon process
serving interleaved calls for two different universes must resolve each call's
engine preference (``preferred_writer``) AND per-universe credential-vault auth
(a BYO ``ANTHROPIC_API_KEY``) from the ``universe_context`` threaded on the call
stack — NOT from the process-global ``runtime.universe_config`` /
``TINYASSETS_UNIVERSE``.

Round-12 note: the per-universe auth dimension is proven with the SANCTIONED BYO
``llm_api_key`` lane. The old per-universe ``llm_subscription`` custody lane
(CODEX_HOME / CLAUDE_CONFIG_DIR bundles) is RETIRED — the platform never
custodies subscription tokens; host auth is process-global (2026-07-02 custody
research §0/§4, round-12 #1). The seam itself (explicit context overriding the
globals, surviving the ThreadPoolExecutor hop) is unchanged.
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

import pytest

import tinyassets.engine_binding as eb
from tinyassets import runtime_singletons as runtime
from tinyassets.config import load_universe_config
from tinyassets.credential_vault import write_credential_vault
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
    subprocess_env_for_provider,
)
from tinyassets.providers.router import ProviderRouter

_VALID_KEY_A = "sk-ant-api03-" + "A" * 40
_VALID_KEY_B = "sk-ant-api03-" + "B" * 40


class _RecordingProvider(BaseProvider):
    """Fake provider that resolves auth via the REAL vault-backed env helper.

    ``complete`` calls the real ``subprocess_env_for_provider(self.name,
    universe_dir=universe_dir)`` and packs what it observed into the response:

    - ``text``  = the ``universe_dir`` it saw (or ``None``)
    - ``model`` = the resolved auth env var (``self._auth_env_key``) the vault
      produced for that universe_dir
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


def _write_byo_claude_universe(root: Path, api_key: str) -> Path:
    """A universe whose vault holds a BYO Anthropic key (the sanctioned lane)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.yaml").write_text(
        "preferred_writer: claude-code\nengine_source: byo_api_key\n",
        encoding="utf-8",
    )
    write_credential_vault(
        root,
        [{"credential_type": "llm_api_key", "service": "anthropic",
          "api_key": api_key}],
    )
    return root


@pytest.fixture
def _enable_byo(monkeypatch):
    """Enable the executable-BYO prerequisite (flag + attestation) for the test."""
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    monkeypatch.setattr(eb, "_vault_encryption_capability_attested", lambda *a, **k: True)
    monkeypatch.setattr(eb, "_sandbox_execution_attested", lambda: True)


def test_subprocess_env_resolves_byo_key_per_universe_context(
    tmp_path, monkeypatch, _enable_byo
):
    """The per-universe AUTH seam: an explicit ``universe_dir`` resolves that
    universe's OWN BYO key, even while the process-global ``TINYASSETS_UNIVERSE``
    is pinned to a DIFFERENT universe, and even across a ThreadPoolExecutor hop."""
    universe_a = _write_byo_claude_universe(tmp_path / "universe_a", _VALID_KEY_A)
    universe_b = _write_byo_claude_universe(tmp_path / "universe_b", _VALID_KEY_B)
    # Pin the process global to A — the explicit context must override it.
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(universe_a))

    plan = [universe_a if i % 2 == 0 else universe_b for i in range(24)]

    def _worker(udir):
        env = subprocess_env_for_provider("claude-code", universe_dir=udir)
        return udir, env.get("ANTHROPIC_API_KEY")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_worker, plan))

    for udir, key in results:
        expected = _VALID_KEY_A if udir == universe_a else _VALID_KEY_B
        assert key == expected, (
            f"{udir} must resolve its OWN BYO key, got {key!r}"
        )


def test_no_subscription_bundle_is_injected_per_universe(tmp_path, monkeypatch):
    """The RETIRED subscription lane is never resolved as per-universe auth: a
    legacy llm_subscription record fails loud (quarantine), never injecting a
    CLAUDE_CONFIG_DIR/CODEX_HOME bundle (round-12 #1)."""
    from tinyassets.credential_vault import RetiredSubscriptionLaneError

    root = tmp_path / "legacy"
    root.mkdir()
    (root / ".credential-vault.json").write_text(json.dumps({
        "schema_version": 1,
        "credentials": [{
            "credential_type": "llm_subscription", "service": "claude",
            "oauth_token": "sk-oauth-legacy",
        }],
    }), encoding="utf-8")
    with pytest.raises(RetiredSubscriptionLaneError):
        subprocess_env_for_provider("claude-code", universe_dir=root)


def test_call_sync_routes_preferred_writer_per_universe_context(
    tmp_path, monkeypatch
):
    """The per-universe PREFERENCE seam (BYO off / default): interleaved calls
    route to each universe's OWN preferred_writer from the threaded context, even
    while the globals point at A."""
    universe_a = tmp_path / "pref_a"
    universe_a.mkdir()
    (universe_a / "config.yaml").write_text(
        "preferred_writer: codex\n", encoding="utf-8"
    )
    universe_b = tmp_path / "pref_b"
    universe_b.mkdir()
    (universe_b / "config.yaml").write_text(
        "preferred_writer: claude-code\n", encoding="utf-8"
    )
    monkeypatch.delenv("TINYASSETS_PIN_WRITER", raising=False)
    monkeypatch.delenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", raising=False)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(universe_a))
    saved_config = runtime.universe_config
    runtime.universe_config = load_universe_config(universe_a)
    try:
        router = ProviderRouter()
        router.register(_RecordingProvider("codex", "openai", "CODEX_HOME"))
        router.register(
            _RecordingProvider("claude-code", "anthropic", "ANTHROPIC_API_KEY")
        )
        ctx_a = UniverseContext(
            universe_dir=universe_a, config=load_universe_config(universe_a)
        )
        ctx_b = UniverseContext(
            universe_dir=universe_b, config=load_universe_config(universe_b)
        )
        plan = [("a", ctx_a) if i % 2 == 0 else ("b", ctx_b) for i in range(16)]

        def _worker(item):
            label, ctx = item
            resp = router.call_sync(
                role="writer", prompt=f"p-{label}", system="s",
                universe_context=ctx,
            )
            return label, resp

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_worker, plan))

        for label, resp in results:
            if label == "a":
                assert resp.provider == "codex", resp.provider
                assert resp.text == str(universe_a)
            else:
                assert resp.provider == "claude-code", resp.provider
                assert resp.text == str(universe_b)
    finally:
        runtime.universe_config = saved_config
