"""Tests for the provider layer: routing, fallback, quota, subprocess providers.

Unit tests mock the subprocess layer so they run without real CLI
binaries or network access.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.exceptions import (
    AllProvidersExhaustedError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from workflow.providers.base import (
    DEGRADED_JUDGE_RESPONSE,
    BaseProvider,
    ModelConfig,
    ProviderResponse,
)
from workflow.providers.quota import QuotaTracker
from workflow.providers.router import FALLBACK_CHAINS, ProviderRouter

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

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
    ) -> ProviderResponse:
        self.call_count += 1
        if self._fail_with is not None:
            raise self._fail_with
        return ProviderResponse(
            text=self._response_text,
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


class TestProviderRouterCall:
    @pytest.mark.asyncio
    async def test_writer_uses_first_available(self):
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        resp = await router.call("writer", "write prose", "you are a writer")
        assert resp.provider == "claude-code"
        assert resp.text == "claude-resp"
        assert providers["claude-code"].call_count == 1
        assert providers["codex"].call_count == 0

    @pytest.mark.asyncio
    async def test_writer_falls_back_on_error(self):
        providers = _make_providers(
            **{"claude-code": FakeProvider(
                "claude-code", "anthropic",
                fail_with=ProviderUnavailableError("down"),
            )}
        )
        router = ProviderRouter(providers=providers)

        resp = await router.call("writer", "write prose", "system")
        assert resp.provider == "codex"
        assert resp.text == "codex-resp"

    @pytest.mark.asyncio
    async def test_writer_falls_to_ollama(self):
        failing = {
            "claude-code": FakeProvider("claude-code", "anthropic", fail_with=ProviderError("x")),
            "codex": FakeProvider("codex", "openai", fail_with=ProviderTimeoutError("x")),
            "gemini-free": FakeProvider(
                "gemini-free", "google",
                fail_with=ProviderUnavailableError("x"),
            ),
            "groq-free": FakeProvider("groq-free", "meta", fail_with=ProviderError("x")),
            "ollama-local": FakeProvider("ollama-local", "local", "ollama-resp"),
        }
        router = ProviderRouter(providers=failing)

        resp = await router.call("writer", "prompt", "system")
        assert resp.provider == "ollama-local"

    @pytest.mark.asyncio
    async def test_writer_raises_when_all_exhausted(self):
        all_fail = {
            name: FakeProvider(name, "x", fail_with=ProviderError("down"))
            for name in FALLBACK_CHAINS["writer"]
        }
        router = ProviderRouter(providers=all_fail)

        with pytest.raises(AllProvidersExhaustedError):
            await router.call("writer", "prompt", "system")

    @pytest.mark.asyncio
    async def test_judge_returns_degraded_when_all_exhausted(self):
        all_fail = {
            name: FakeProvider(name, "x", fail_with=ProviderError("down"))
            for name in FALLBACK_CHAINS["judge"]
        }
        router = ProviderRouter(providers=all_fail)

        resp = await router.call("judge", "prompt", "system")
        assert resp.degraded is True
        assert resp is DEGRADED_JUDGE_RESPONSE

    @pytest.mark.asyncio
    async def test_extract_prefers_codex(self):
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        resp = await router.call("extract", "extract facts", "system")
        assert resp.provider == "codex"

    @pytest.mark.asyncio
    async def test_skips_missing_providers(self):
        # Only ollama registered.
        providers = {"ollama-local": FakeProvider("ollama-local", "local", "ok")}
        router = ProviderRouter(providers=providers)

        resp = await router.call("writer", "prompt", "system")
        assert resp.provider == "ollama-local"

    @pytest.mark.asyncio
    async def test_cooldown_applied_on_unavailable(self):
        providers = _make_providers(
            **{"claude-code": FakeProvider(
                "claude-code", "anthropic",
                fail_with=ProviderUnavailableError("rate limited"),
            )}
        )
        quota = QuotaTracker()
        router = ProviderRouter(providers=providers, quota=quota)

        resp = await router.call("writer", "prompt", "system")
        # Should have fallen back to codex.
        assert resp.provider == "codex"
        # Claude should now be in cooldown.
        assert quota.available("claude-code") is False

    @pytest.mark.asyncio
    async def test_timeout_cooldown_applied(self):
        providers = _make_providers(
            **{"claude-code": FakeProvider(
                "claude-code", "anthropic",
                fail_with=ProviderTimeoutError("hung"),
            )}
        )
        quota = QuotaTracker()
        router = ProviderRouter(providers=providers, quota=quota)

        resp = await router.call("writer", "prompt", "system")
        assert resp.provider == "codex"
        assert quota.available("claude-code") is False


# =====================================================================
# ProviderRouter -- preferred provider config
# =====================================================================


class TestPreferredProvider:
    def test_apply_preference_reorders(self):
        chain = ["claude-code", "codex", "gemini-free"]
        result = ProviderRouter._apply_preference(chain, "gemini-free")
        assert result == ["gemini-free", "claude-code", "codex"]

    def test_apply_preference_noop_when_empty(self):
        chain = ["claude-code", "codex"]
        assert ProviderRouter._apply_preference(chain, "") == chain

    def test_apply_preference_noop_when_not_in_chain(self):
        chain = ["claude-code", "codex"]
        assert ProviderRouter._apply_preference(chain, "grok-free") == chain

    def test_apply_preference_already_first(self):
        chain = ["claude-code", "codex"]
        assert ProviderRouter._apply_preference(chain, "claude-code") == chain

    @pytest.mark.asyncio
    async def test_api_key_preferred_writer_ignored_without_opt_in(self, monkeypatch):
        from workflow import runtime_singletons as runtime
        from workflow.config import UniverseConfig

        monkeypatch.setattr(
            runtime, "universe_config",
            UniverseConfig(preferred_writer="gemini-free"),
        )
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        resp = await router.call("writer", "prompt", "system")
        assert resp.provider == "claude-code"
        assert providers["gemini-free"].call_count == 0

    @pytest.mark.asyncio
    async def test_preferred_writer_tried_first_with_api_key_opt_in(self, monkeypatch):
        from workflow import runtime_singletons as runtime
        from workflow.config import UniverseConfig

        monkeypatch.setenv("WORKFLOW_ALLOW_API_KEY_PROVIDERS", "1")
        monkeypatch.setattr(
            runtime, "universe_config",
            UniverseConfig(preferred_writer="gemini-free"),
        )
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        resp = await router.call("writer", "prompt", "system")
        assert resp.provider == "gemini-free"

    @pytest.mark.asyncio
    async def test_api_key_preferred_judge_ignored_without_opt_in(self, monkeypatch):
        from workflow import runtime_singletons as runtime
        from workflow.config import UniverseConfig

        monkeypatch.setattr(
            runtime, "universe_config",
            UniverseConfig(preferred_judge="groq-free"),
        )
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        resp = await router.call("judge", "prompt", "system")
        assert resp.provider == "codex"
        assert providers["groq-free"].call_count == 0

    @pytest.mark.asyncio
    async def test_preferred_judge_tried_first_with_api_key_opt_in(self, monkeypatch):
        from workflow import runtime_singletons as runtime
        from workflow.config import UniverseConfig

        monkeypatch.setenv("WORKFLOW_ALLOW_API_KEY_PROVIDERS", "1")
        monkeypatch.setattr(
            runtime, "universe_config",
            UniverseConfig(preferred_judge="groq-free"),
        )
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        resp = await router.call("judge", "prompt", "system")
        assert resp.provider == "groq-free"

    @pytest.mark.asyncio
    async def test_preferred_writer_falls_back_on_failure(self, monkeypatch):
        from workflow import runtime_singletons as runtime
        from workflow.config import UniverseConfig

        monkeypatch.setattr(
            runtime, "universe_config",
            UniverseConfig(preferred_writer="gemini-free"),
        )
        providers = _make_providers(
            **{"gemini-free": FakeProvider(
                "gemini-free", "google",
                fail_with=ProviderUnavailableError("down"),
            )}
        )
        router = ProviderRouter(providers=providers)

        resp = await router.call("writer", "prompt", "system")
        # API-key provider is ignored by default; chain stays subscription-first.
        assert resp.provider == "claude-code"


# =====================================================================
# ProviderRouter -- judge ensemble
# =====================================================================


class TestJudgeEnsemble:
    @pytest.mark.asyncio
    async def test_fans_out_to_subscription_default_providers(self):
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        results = await router.call_judge_ensemble("judge this", "system")
        # API-key-backed judges are ignored unless the host opts in.
        assert len(results) == 2
        families = {r.family for r in results}
        assert families == {"openai", "local"}

    @pytest.mark.asyncio
    async def test_fans_out_to_all_available_with_api_key_opt_in(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_ALLOW_API_KEY_PROVIDERS", "1")
        providers = _make_providers()
        router = ProviderRouter(providers=providers)

        results = await router.call_judge_ensemble("judge this", "system")
        assert len(results) == 5
        families = {r.family for r in results}
        assert families == {"openai", "google", "meta", "xai", "local"}

    @pytest.mark.asyncio
    async def test_partial_availability(self):
        """Only registered providers are called — no duplicates."""
        providers = {
            "codex": FakeProvider("codex", "openai", "codex-resp"),
            "gemini-free": FakeProvider("gemini-free", "google", "gemini-resp"),
        }
        router = ProviderRouter(providers=providers)

        results = await router.call_judge_ensemble("judge this", "system")
        assert len(results) == 1
        families = {r.family for r in results}
        assert families == {"openai"}

    @pytest.mark.asyncio
    async def test_ensemble_with_failures(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_ALLOW_API_KEY_PROVIDERS", "1")
        providers = {
            "codex": FakeProvider("codex", "openai", fail_with=ProviderError("x")),
            "gemini-free": FakeProvider("gemini-free", "google", "gemini-resp"),
            "groq-free": FakeProvider("groq-free", "meta", "groq-resp"),
            "ollama-local": FakeProvider("ollama-local", "local", "ollama-resp"),
        }
        router = ProviderRouter(providers=providers)

        results = await router.call_judge_ensemble("judge this", "system")
        # Codex fails -> gemini, groq, ollama should fill 3 slots.
        assert len(results) >= 2
        families = {r.family for r in results}
        assert "openai" not in families

    @pytest.mark.asyncio
    async def test_empty_ensemble_when_all_fail(self):
        all_fail = {
            name: FakeProvider(name, name, fail_with=ProviderError("down"))
            for name in ["codex", "gemini-free", "groq-free", "grok-free", "ollama-local"]
        }
        router = ProviderRouter(providers=all_fail)

        results = await router.call_judge_ensemble("judge this", "system")
        assert results == []


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
        from workflow.providers.claude_provider import ClaudeProvider

        with patch("shutil.which", return_value=None):
            assert not ClaudeProvider.is_available()
            router = ProviderRouter()
            if ClaudeProvider.is_available():
                router.register(ClaudeProvider())
            assert "claude-code" not in router.available_providers

    def test_codex_provider_not_registered_when_binary_absent(self):
        """codex must not appear in available_providers when 'codex' binary is missing."""
        from workflow.providers.codex_provider import CodexProvider

        with patch("shutil.which", return_value=None):
            assert not CodexProvider.is_available()
            router = ProviderRouter()
            if CodexProvider.is_available():
                router.register(CodexProvider())
            assert "codex" not in router.available_providers

    def test_claude_provider_registered_when_binary_present(self):
        """claude-code is registered when 'claude' binary is found."""
        from workflow.providers.claude_provider import ClaudeProvider

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            assert ClaudeProvider.is_available()

    def test_codex_provider_registered_when_binary_present(self):
        """codex is registered when 'codex' binary is found."""
        from workflow.providers.codex_provider import CodexProvider

        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            assert CodexProvider.is_available()


# =====================================================================
# ClaudeProvider (subprocess mock)
# =====================================================================


class TestClaudeProvider:
    @pytest.mark.asyncio
    async def test_success(self):
        from workflow.providers.claude_provider import ClaudeProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Hello world", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("workflow.providers.claude_provider._resolve_claude_cmd",
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
        from workflow.providers.claude_provider import ClaudeProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"unavailable"))
        mock_proc.returncode = 1
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("workflow.providers.claude_provider._resolve_claude_cmd",
                  return_value=(["claude"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = ClaudeProvider()
            with pytest.raises(ProviderUnavailableError):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self):
        from workflow.providers.claude_provider import ClaudeProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("workflow.providers.claude_provider._resolve_claude_cmd",
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


class TestCodexProvider:
    @pytest.mark.asyncio
    async def test_success(self):
        from workflow.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"codex output", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("workflow.providers.codex_provider._resolve_codex_cmd",
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
        from workflow.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"bad"))
        mock_proc.returncode = 2
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("workflow.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = CodexProvider()
            with pytest.raises(ProviderError):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_empty_stdout_raises_provider_error(self):
        """Empty stdout with exit 0 must raise ProviderError, not return ''."""
        from workflow.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("workflow.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = CodexProvider()
            with pytest.raises(ProviderError, match="empty response"):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_auth_failure_exit_0_raises_provider_error(self):
        """codex v0.122 exits 0 on 401 but emits Unauthorized in stderr."""
        from workflow.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(
            b"",
            b"Error: 401 Unauthorized - Reconnecting...",
        ))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("workflow.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            provider = CodexProvider()
            with pytest.raises(ProviderError, match="auth-error"):
                await provider.complete("prompt", "system", ModelConfig())

    @pytest.mark.asyncio
    async def test_skip_git_repo_check_in_command_without_bwrap(self):
        """codex exec must bypass sandbox only when bwrap is unavailable."""
        from workflow.providers.codex_provider import CodexProvider

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
            patch("workflow.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("workflow.providers.codex_provider.get_sandbox_status",
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
        import workflow.providers.codex_provider as codex_provider
        from workflow.providers.codex_provider import CodexProvider

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
            patch("workflow.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("workflow.providers.codex_provider.get_sandbox_status",
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
        from workflow.providers.codex_provider import CodexProvider

        captured_cmd = []
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"hello", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        async def _fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            return mock_proc

        monkeypatch.setenv("WORKFLOW_CODEX_MODEL", "gpt-5.5")
        with (
            patch("workflow.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("workflow.providers.codex_provider.get_sandbox_status",
                  return_value={"bwrap_available": True, "reason": None}),
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        ):
            provider = CodexProvider()
            await provider.complete("prompt", "system", ModelConfig())

        assert captured_cmd[captured_cmd.index("-m") + 1] == "gpt-5.5"

    @pytest.mark.asyncio
    async def test_uses_full_auto_when_bwrap_available(self):
        """Healthy bwrap hosts should keep Codex's sandboxed auto mode."""
        from workflow.providers.codex_provider import CodexProvider

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
            patch("workflow.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("workflow.providers.codex_provider.get_sandbox_status",
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

        from workflow.providers.ollama_provider import OllamaProvider

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

        from workflow.providers.ollama_provider import OllamaProvider

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            provider = OllamaProvider()
            with pytest.raises(ProviderUnavailableError):
                await provider.complete("prompt", "system", ModelConfig())


# =====================================================================
# GrokProvider (OpenAI SDK mock)
# =====================================================================


class TestGrokProvider:
    def test_requires_api_key_provider_opt_in(self):
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            from workflow.providers.grok_provider import GrokProvider

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
                {"XAI_API_KEY": "test-key", "WORKFLOW_ALLOW_API_KEY_PROVIDERS": "1"},
            ),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            from workflow.providers.grok_provider import GrokProvider

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
                {"XAI_API_KEY": "test-key", "WORKFLOW_ALLOW_API_KEY_PROVIDERS": "1"},
            ),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            from workflow.providers.grok_provider import GrokProvider

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
                {"XAI_API_KEY": "test-key", "WORKFLOW_ALLOW_API_KEY_PROVIDERS": "1"},
            ),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            from workflow.providers.grok_provider import GrokProvider

            provider = GrokProvider()
            with pytest.raises(ProviderError):
                await provider.complete("prompt", "system", ModelConfig())

    def test_missing_api_key_raises_unavailable(self):
        with (
            patch.dict(
                "os.environ",
                {"WORKFLOW_ALLOW_API_KEY_PROVIDERS": "1"},
                clear=True,
            ),
            patch.dict(sys.modules, {"openai": MagicMock()}),
        ):
            from workflow.providers.grok_provider import GrokProvider

            with pytest.raises(ProviderUnavailableError, match="XAI_API_KEY"):
                GrokProvider()


# =====================================================================
# Fallback chain definitions
# =====================================================================


class TestFallbackChainDefinitions:
    def test_writer_chain_starts_with_claude(self):
        assert FALLBACK_CHAINS["writer"][0] == "claude-code"
        assert FALLBACK_CHAINS["writer"][-1] == "ollama-local"

    def test_judge_chain_starts_with_codex(self):
        assert FALLBACK_CHAINS["judge"][0] == "codex"

    def test_extract_chain_starts_with_codex(self):
        assert FALLBACK_CHAINS["extract"][0] == "codex"
        assert FALLBACK_CHAINS["extract"][-1] == "ollama-local"

    def test_embed_is_local_only(self):
        assert FALLBACK_CHAINS["embed"] == ["ollama-local"]

    def test_all_chains_include_ollama(self):
        """Ollama is in every chain as last-resort fallback."""
        for role, chain in FALLBACK_CHAINS.items():
            assert "ollama-local" in chain, f"{role} chain missing ollama-local"

    def test_ollama_is_last_in_judge_chain(self):
        """Ollama is last in judge chains (text-parsed, not JSON)."""
        assert FALLBACK_CHAINS["judge"][-1] == "ollama-local"

    def test_grok_in_writer_and_judge_chains(self):
        """Grok appears in writer and judge chains for diversity."""
        assert "grok-free" in FALLBACK_CHAINS["writer"]
        assert "grok-free" in FALLBACK_CHAINS["judge"]
