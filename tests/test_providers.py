"""Tests for exact-authority routing, quota, and subprocess providers.

Unit tests mock the subprocess layer so they run without real CLI
binaries or network access.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import sys
import threading
import time
import types
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderAuthorityHeldError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
)
from tinyassets.providers.quota import QuotaTracker
from tinyassets.providers.router import ProviderRouter

# =====================================================================
# Helpers -- fake providers for testing
# =====================================================================


class FakeProvider(BaseProvider):
    """A configurable fake provider for unit tests."""

    def __init__(
        self,
        name: str,
        family: str,
        response_text: str = "ok",
        *,
        fail_with: Exception | None = None,
    ) -> None:
        self.name = name
        self.family = family
        self._response_text = response_text
        self._fail_with = fail_with
        self.call_count = 0
        self.last_config: ModelConfig | None = None

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir=None,
    ) -> ProviderResponse:
        self.call_count += 1
        self.last_config = config
        if self._fail_with is not None:
            raise self._fail_with
        return ProviderResponse(
            text=self._response_text,
            provider=self.name,
            model="fake",
            family=self.family,
            latency_ms=1.0,
        )


class SlowCountingProvider(BaseProvider):
    """Tracks whether router sync wrappers let calls overlap."""

    name = "claude-code"
    family = "anthropic"

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir=None,
    ) -> ProviderResponse:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.05)
        finally:
            with self.lock:
                self.active -= 1
        return ProviderResponse(
            text="ok",
            provider=self.name,
            model="fake",
            family=self.family,
            latency_ms=1.0,
        )


def _make_providers(**overrides: FakeProvider) -> dict[str, FakeProvider]:
    """Build a full provider map with defaults.  Override specific ones."""
    defaults = {
        "claude-code": FakeProvider("claude-code", "anthropic", "claude-resp"),
        "codex": FakeProvider("codex", "openai", "codex-resp"),
        "gemini-free": FakeProvider("gemini-free", "google", "gemini-resp"),
        "groq-free": FakeProvider("groq-free", "meta", "groq-resp"),
        "grok-free": FakeProvider("grok-free", "xai", "grok-resp"),
        "ollama-local": FakeProvider("ollama-local", "local", "ollama-resp"),
    }
    defaults.update(overrides)
    return defaults


# =====================================================================
# QuotaTracker
# =====================================================================


class TestQuotaTracker:
    def test_available_when_no_cooldown(self):
        qt = QuotaTracker()
        assert qt.available("claude-code") is True

    def test_cooldown_blocks_availability(self):
        qt = QuotaTracker()
        qt.cooldown("claude-code", 3600)
        assert qt.available("claude-code") is False

    def test_cooldown_expires(self):
        qt = QuotaTracker()
        # Set a cooldown that already expired.
        qt._cooldowns["claude-code"] = time.monotonic() - 1
        assert qt.available("claude-code") is True

    def test_rate_limit_gemini(self):
        qt = QuotaTracker()
        # Record 10 calls for gemini (hits per-minute limit).
        for _ in range(10):
            qt.record_success("gemini-free")
        assert qt.available("gemini-free") is False

    def test_rate_limit_does_not_affect_claude(self):
        qt = QuotaTracker()
        for _ in range(100):
            qt.record_success("claude-code")
        assert qt.available("claude-code") is True

    def test_cooldown_then_record_success(self):
        qt = QuotaTracker()
        qt.cooldown("groq-free", 10)
        assert qt.available("groq-free") is False
        # Success recording should still work (for post-cooldown tracking).
        qt.record_success("groq-free")


# =====================================================================
# ProviderRouter -- single call routing
# =====================================================================


def _assigned_context(
    tmp_path: Path,
    *,
    provider: str = "codex",
    roles: tuple[str, ...] = ("writer", "judge", "extract"),
) -> UniverseContext:
    from tinyassets.assigned_credential_execution import AssignedCredentialAuthority

    universe = tmp_path / "universe"
    universe.mkdir(exist_ok=True)
    snapshot = tmp_path / "credential-snapshot"
    snapshot.mkdir(exist_ok=True)
    return UniverseContext(
        universe_dir=universe,
        assigned_credential=AssignedCredentialAuthority(
            universe_id=universe.name,
            owner_user_id="owner-a",
            agent_binding_id="agent-a",
            binding_revision=1,
            provider=provider,
            credential_snapshot_dir=snapshot,
            binding_id="binding-a",
            binding_generation=1,
            binding_digest="sha256:" + "1" * 64,
            assignment_generation=1,
            assignment_digest="sha256:" + "3" * 64,
            binding_revocation_generation=0,
            credential_reference_id="credential-a",
            credential_reference_generation=1,
            credential_reference_digest="sha256:" + "2" * 64,
            credential_service="codex" if provider == "codex" else "claude",
            max_invocations=100,
            max_tokens=4096,
            max_cost_microunits=1_000_000,
            allowed_operations=("converse",),
            allowed_roles=roles,
        ),
    )


class TestProviderRouterExactAuthority:
    @pytest.fixture(autouse=True)
    def _budget(self, monkeypatch):
        from types import SimpleNamespace

        from tinyassets import provider_assignment

        def reserve(*_args, **kwargs):
            output = kwargs["requested_output_tokens"]
            return SimpleNamespace(
                output_tokens=output,
                reserved_total_tokens=output + 1,
                reserved_cost_microunits=(output + 1) * 100,
            )

        monkeypatch.setattr(provider_assignment, "reserve_served_provider_budget", reserve)
        monkeypatch.setattr(
            provider_assignment,
            "finalize_served_provider_budget",
            lambda *_a, **_k: None,
        )
        monkeypatch.setattr(
            provider_assignment,
            "abandon_served_provider_budget",
            lambda *_a, **_k: None,
        )

    @pytest.mark.asyncio
    async def test_assigned_provider_is_the_only_provider_called(self, tmp_path):
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        response = await router.call(
            "writer",
            "prompt",
            "system",
            operation="run_graph",
            universe_context=_assigned_context(tmp_path, provider="codex"),
        )

        assert response.provider == "codex"
        assert providers["codex"].call_count == 1
        assert sum(provider.call_count for provider in providers.values()) == 1
        assert providers["codex"].last_config.credential_snapshot_dir == (
            tmp_path / "credential-snapshot"
        )

    @pytest.mark.asyncio
    async def test_policy_cannot_replace_assigned_provider(self, tmp_path):
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        text, provider, meta = await router.call_with_policy(
            "writer",
            "prompt",
            "system",
            {"preferred": {"provider": "claude-code"}, "max_tokens": 27},
            operation="run_graph",
            universe_context=_assigned_context(tmp_path, provider="codex"),
        )

        assert (text, provider) == ("codex-resp", "codex")
        assert meta["attempts"] == 1
        assert providers["codex"].last_config.max_tokens == 27
        assert providers["claude-code"].call_count == 0

    @pytest.mark.asyncio
    async def test_assigned_failure_never_falls_back(self, tmp_path):
        providers = _make_providers(
            codex=FakeProvider(
                "codex",
                "openai",
                fail_with=ProviderUnavailableError("rate limited"),
            )
        )
        router = ProviderRouter(providers=providers)

        with pytest.raises(AllProvidersExhaustedError) as caught:
            await router.call(
                "writer",
                "prompt",
                "system",
                operation="run_graph",
                universe_context=_assigned_context(tmp_path, provider="codex"),
            )

        assert [attempt.provider for attempt in caught.value.attempts] == ["codex"]
        assert providers["codex"].call_count == 1
        assert providers["claude-code"].call_count == 0
        assert providers["ollama-local"].call_count == 0

    @pytest.mark.asyncio
    async def test_missing_authority_holds_before_launch(self):
        provider = FakeProvider("codex", "openai")
        router = ProviderRouter(providers={"codex": provider})

        with pytest.raises(ProviderAuthorityHeldError):
            await router.call("writer", "prompt", "system")

        assert provider.call_count == 0

    @pytest.mark.asyncio
    async def test_assignment_rejects_wrong_universe_and_token_ceiling(self, tmp_path):
        provider = FakeProvider("codex", "openai")
        router = ProviderRouter(providers={"codex": provider})
        context = _assigned_context(tmp_path, roles=("writer",))

        wrong_universe = replace(context, universe_dir=tmp_path / "other")
        with pytest.raises(ProviderAuthorityHeldError):
            await router.call(
                "writer",
                "prompt",
                "system",
                operation="run_graph",
                universe_context=wrong_universe,
            )
        with pytest.raises(PermissionError, match="assigned token ceiling"):
            await router.call(
                "writer",
                "prompt",
                "system",
                ModelConfig(max_tokens=4097),
                operation="run_graph",
                universe_context=context,
            )

        assert provider.call_count == 0

    @pytest.mark.asyncio
    async def test_judge_ensemble_is_one_exact_launch(self, tmp_path):
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        responses = await router.call_judge_ensemble(
            "judge",
            "system",
            operation="run_graph",
            universe_context=_assigned_context(tmp_path, provider="codex"),
        )

        assert [response.provider for response in responses] == ["codex"]
        assert sum(provider.call_count for provider in providers.values()) == 1

    def test_router_has_no_chain_or_fanout_api(self):
        router = ProviderRouter()
        assert not hasattr(router, "effective_chain")
        assert not hasattr(router, "preferred_provider")

    def test_retired_router_options_fail_loudly(self):
        with pytest.raises(TypeError, match="fallback_chain"):
            ProviderRouter(fallback_chain=["codex"])

    def test_sync_calls_can_overlap_on_exact_assignment(self, tmp_path):
        provider = SlowCountingProvider()
        router = ProviderRouter(providers={provider.name: provider})
        context = _assigned_context(tmp_path, provider=provider.name)

        def call_once() -> str:
            return router.call_sync(
                "writer",
                "prompt",
                "system",
                operation="run_graph",
                universe_context=context,
            ).text

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(lambda _item: call_once(), range(2))) == ["ok", "ok"]
        assert provider.max_active == 2


# =====================================================================
# ProviderRouter -- register / available_providers
# =====================================================================


class TestProviderRegistration:
    def test_register_provider(self):
        router = ProviderRouter()
        assert router.available_providers == []

        fake = FakeProvider("test-provider", "test-family")
        router.register(fake)
        assert "test-provider" in router.available_providers

    def test_register_overwrites(self):
        router = ProviderRouter()
        router.register(FakeProvider("p", "f1", "v1"))
        router.register(FakeProvider("p", "f2", "v2"))
        assert len(router.available_providers) == 1

    def test_claude_provider_not_registered_when_binary_absent(self):
        """claude-code must not appear in available_providers when 'claude' binary is missing."""
        from tinyassets.providers.claude_provider import ClaudeProvider

        with patch("shutil.which", return_value=None):
            assert not ClaudeProvider.is_available()
            router = ProviderRouter()
            if ClaudeProvider.is_available():
                router.register(ClaudeProvider())
            assert "claude-code" not in router.available_providers

    def test_codex_provider_not_registered_when_binary_absent(self):
        """codex must not appear in available_providers when 'codex' binary is missing."""
        from tinyassets.providers.codex_provider import CodexProvider

        with patch("shutil.which", return_value=None):
            assert not CodexProvider.is_available()
            router = ProviderRouter()
            if CodexProvider.is_available():
                router.register(CodexProvider())
            assert "codex" not in router.available_providers

    def test_claude_provider_registered_when_binary_present(self):
        """claude-code is registered when 'claude' binary is found."""
        from tinyassets.providers.claude_provider import ClaudeProvider

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            assert ClaudeProvider.is_available()

    def test_codex_provider_registered_when_binary_present(self):
        """codex is registered when 'codex' binary is found."""
        from tinyassets.providers.codex_provider import CodexProvider

        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            assert CodexProvider.is_available()

# =====================================================================
# ClaudeProvider (subprocess mock)
# =====================================================================


@pytest.fixture
def explicit_cli_credential_env(monkeypatch):
    """Low-level CLI mechanics still receive an explicit launch environment."""

    monkeypatch.setattr(
        "tinyassets.providers.claude_provider.subprocess_env_for_provider",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "tinyassets.providers.codex_provider.subprocess_env_for_provider",
        lambda *_args, **_kwargs: {},
    )


@pytest.mark.usefixtures("explicit_cli_credential_env")
class TestClaudeProvider:
    @pytest.mark.asyncio
    async def test_success(self):
        from tinyassets.providers.claude_provider import ClaudeProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Hello world", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.claude_provider._resolve_claude_cmd",
                  return_value=(["claude"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = ClaudeProvider()
            resp = await provider.complete("prompt", "system", ModelConfig())

        assert resp.text == "Hello world"
        assert resp.provider == "claude-code"
        assert resp.family == "anthropic"

    @pytest.mark.asyncio
    async def test_exit_code_1_quick_triggers_unavailable(self):
        from tinyassets.providers.claude_provider import ClaudeProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"unavailable"))
        mock_proc.returncode = 1
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.claude_provider._resolve_claude_cmd",
                  return_value=(["claude"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = ClaudeProvider()
            with pytest.raises(ProviderUnavailableError):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self):
        from tinyassets.providers.claude_provider import ClaudeProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.claude_provider._resolve_claude_cmd",
                  return_value=(["claude"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()),
        ):
            provider = ClaudeProvider()
            with pytest.raises(ProviderTimeoutError):
                await provider.complete("prompt", "system", ModelConfig(timeout=1))


# =====================================================================
# CodexProvider (subprocess mock)
# =====================================================================


@pytest.mark.usefixtures("explicit_cli_credential_env")
class TestCodexProvider:
    @pytest.mark.asyncio
    async def test_success(self):
        from tinyassets.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"codex output", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = CodexProvider()
            resp = await provider.complete("prompt", "system", ModelConfig())

        assert resp.text == "codex output"
        assert resp.provider == "codex"
        assert resp.family == "openai"

    @pytest.mark.asyncio
    async def test_error_raises_provider_error(self):
        from tinyassets.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"bad"))
        mock_proc.returncode = 2
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = CodexProvider()
            with pytest.raises(ProviderError):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_empty_stdout_raises_provider_error(self):
        """Empty stdout with exit 0 must raise ProviderError, not return ''."""
        from tinyassets.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = CodexProvider()
            with pytest.raises(ProviderError, match="empty response"):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_auth_failure_exit_0_raises_provider_error(self):
        """codex v0.122 exits 0 on 401 but emits Unauthorized in stderr."""
        from tinyassets.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(
            b"",
            b"Error: 401 Unauthorized - Reconnecting...",
        ))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = CodexProvider()
            with pytest.raises(ProviderError, match="auth-error"):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_skip_git_repo_check_in_command_without_bwrap(self):
        """codex exec must bypass sandbox only when bwrap is unavailable."""
        from tinyassets.providers.codex_provider import CodexProvider

        captured_cmd = []
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"hello", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        async def _fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            return mock_proc

        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("tinyassets.providers.codex_provider.get_sandbox_status",
                  return_value={"bwrap_available": False, "reason": "test"}),
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        ):
            provider = CodexProvider()
            await provider.complete("prompt", "system", ModelConfig())

        assert "--skip-git-repo-check" in captured_cmd, (
            f"Expected --skip-git-repo-check in command: {captured_cmd}"
        )
        assert "--dangerously-bypass-approvals-and-sandbox" in captured_cmd
        assert "--full-auto" not in captured_cmd
        assert "--ephemeral" in captured_cmd
        assert "-C" in captured_cmd
        assert "-m" in captured_cmd
        assert captured_cmd[captured_cmd.index("-m") + 1] == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_runs_from_repo_root_so_coding_tasks_can_read_source(self):
        """BUG-060: loop investigations need repo source/tests, not an empty tempdir."""
        import tinyassets.providers.codex_provider as codex_provider
        from tinyassets.providers.codex_provider import CodexProvider

        captured_cmd = []
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"hello", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        async def _fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            return mock_proc

        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("tinyassets.providers.codex_provider.get_sandbox_status",
                  return_value={"bwrap_available": False, "reason": "test"}),
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        ):
            provider = CodexProvider()
            await provider.complete("prompt", "system", ModelConfig())

        repo_root = Path(codex_provider.__file__).resolve().parents[2]
        assert "-C" in captured_cmd
        assert captured_cmd[captured_cmd.index("-C") + 1] == str(repo_root)

    @pytest.mark.asyncio
    async def test_model_can_be_overridden_by_env(self, monkeypatch):
        """Operators can move the provider forward after the deployed CLI supports it."""
        from tinyassets.providers.codex_provider import CodexProvider

        captured_cmd = []
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"hello", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        async def _fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            return mock_proc

        monkeypatch.setenv("TINYASSETS_CODEX_MODEL", "gpt-5.5")
        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("tinyassets.providers.codex_provider.get_sandbox_status",
                  return_value={"bwrap_available": True, "reason": None}),
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        ):
            provider = CodexProvider()
            await provider.complete("prompt", "system", ModelConfig())

        assert captured_cmd[captured_cmd.index("-m") + 1] == "gpt-5.5"

    @pytest.mark.asyncio
    async def test_uses_full_auto_when_bwrap_available(self):
        """Healthy bwrap hosts should keep Codex's sandboxed auto mode."""
        from tinyassets.providers.codex_provider import CodexProvider

        captured_cmd = []
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"hello", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        async def _fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            return mock_proc

        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("tinyassets.providers.codex_provider.get_sandbox_status",
                  return_value={"bwrap_available": True, "reason": None}),
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        ):
            provider = CodexProvider()
            await provider.complete("prompt", "system", ModelConfig())

        assert "--full-auto" in captured_cmd
        assert "--dangerously-bypass-approvals-and-sandbox" not in captured_cmd
        assert "--skip-git-repo-check" in captured_cmd
        assert "--ephemeral" in captured_cmd


# =====================================================================
# OllamaProvider (HTTP mock)
# =====================================================================


class TestOllamaProvider:
    @pytest.mark.asyncio
    async def test_success(self):
        import json

        from tinyassets.providers.ollama_provider import OllamaProvider

        response_body = json.dumps({"response": "ollama output"}).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            provider = OllamaProvider()
            resp = await provider.complete("prompt", "system", ModelConfig())

        assert resp.text == "ollama output"
        assert resp.provider == "ollama-local"
        assert resp.family == "local"

    @pytest.mark.asyncio
    async def test_connection_refused(self):
        import urllib.error

        from tinyassets.providers.ollama_provider import OllamaProvider

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            provider = OllamaProvider()
            with pytest.raises(ProviderUnavailableError):
                await provider.complete("prompt", "system", ModelConfig())


# =====================================================================
# GeminiProvider (google-genai SDK mock)
# =====================================================================


class TestGeminiProvider:
    @pytest.mark.asyncio
    async def test_sync_sdk_call_yields_event_loop(self):
        release = threading.Event()
        started = threading.Event()

        class _FakeModels:
            def generate_content(self, **kwargs):
                started.set()
                release.wait(timeout=0.2)
                return types.SimpleNamespace(text="gemini output")

        class _FakeClient:
            def __init__(self, api_key: str) -> None:
                self.api_key = api_key
                self.models = _FakeModels()

        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = _FakeClient
        fake_types = types.ModuleType("google.genai.types")
        fake_types.GenerateContentConfig = MagicMock
        fake_genai.types = fake_types
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai

        with (
            patch.dict(
                "os.environ",
                {
                    "GEMINI_API_KEY": "test-key",
                    "TINYASSETS_ALLOW_API_KEY_PROVIDERS": "1",
                },
            ),
            patch.dict(
                sys.modules,
                {
                    "google": fake_google,
                    "google.genai": fake_genai,
                    "google.genai.types": fake_types,
                },
            ),
        ):
            from tinyassets.providers.gemini_provider import GeminiProvider

            provider = GeminiProvider()
            task = asyncio.create_task(
                provider.complete("prompt", "system", ModelConfig())
            )
            await asyncio.sleep(0.02)
            assert started.is_set()
            assert not task.done()
            release.set()
            resp = await task

        assert resp.text == "gemini output"
        assert resp.provider == "gemini-free"


# =====================================================================
# GrokProvider (OpenAI SDK mock)
# =====================================================================


class TestGrokProvider:
    def test_requires_api_key_provider_opt_in(self):
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            from tinyassets.providers.grok_provider import GrokProvider

            with pytest.raises(ProviderUnavailableError, match="disabled by default"):
                GrokProvider()

    @pytest.mark.asyncio
    async def test_success(self):
        mock_choice = MagicMock()
        mock_choice.message.content = "grok output"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = mock_client

        with (
            patch.dict(
                "os.environ",
                {"XAI_API_KEY": "test-key", "TINYASSETS_ALLOW_API_KEY_PROVIDERS": "1"},
            ),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            from tinyassets.providers.grok_provider import GrokProvider

            provider = GrokProvider()
            resp = await provider.complete("prompt", "system", ModelConfig())

        assert resp.text == "grok output"
        assert resp.provider == "grok-free"
        assert resp.family == "xai"
        assert resp.model == "grok-4.1-fast"

    @pytest.mark.asyncio
    async def test_rate_limit_raises_unavailable(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception(
            "Error code: 429 - Rate limit exceeded"
        )

        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = mock_client

        with (
            patch.dict(
                "os.environ",
                {"XAI_API_KEY": "test-key", "TINYASSETS_ALLOW_API_KEY_PROVIDERS": "1"},
            ),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            from tinyassets.providers.grok_provider import GrokProvider

            provider = GrokProvider()
            with pytest.raises(ProviderUnavailableError):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_generic_error_raises_provider_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception(
            "Internal server error"
        )

        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = mock_client

        with (
            patch.dict(
                "os.environ",
                {"XAI_API_KEY": "test-key", "TINYASSETS_ALLOW_API_KEY_PROVIDERS": "1"},
            ),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            from tinyassets.providers.grok_provider import GrokProvider

            provider = GrokProvider()
            with pytest.raises(ProviderError):
                await provider.complete("prompt", "system", ModelConfig())

    def test_missing_api_key_raises_unavailable(self):
        with (
            patch.dict(
                "os.environ",
                {"TINYASSETS_ALLOW_API_KEY_PROVIDERS": "1"},
                clear=True,
            ),
            patch.dict(sys.modules, {"openai": MagicMock()}),
        ):
            from tinyassets.providers.grok_provider import GrokProvider

            with pytest.raises(ProviderUnavailableError, match="XAI_API_KEY"):
                GrokProvider()


# =====================================================================
