"""Base types for the provider layer.

Every provider implements :class:`BaseProvider`.  The router and all
consumers work with :class:`ProviderResponse` and :class:`ModelConfig`.
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Configuration passed to every provider call."""

    timeout: int = 300
    """Subprocess / HTTP timeout in seconds."""

    max_tokens: int | None = None
    """Optional token cap (provider-specific interpretation)."""

    temperature: float = 0.7


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Uniform response envelope returned by every provider."""

    text: str
    provider: str
    model: str
    family: str
    latency_ms: float
    degraded: bool = False


# Sentinel for quality-floor-only degraded judge responses.
DEGRADED_JUDGE_RESPONSE = ProviderResponse(
    text="",
    provider="none",
    model="quality-floor-only",
    family="none",
    latency_ms=0.0,
    degraded=True,
)


API_KEY_PROVIDER_ENV_VARS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "XAI_API_KEY",
)


def _truthy_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def api_key_providers_enabled() -> bool:
    """Return True only when a host explicitly opts into API-key providers."""
    return _truthy_env(os.environ.get("WORKFLOW_ALLOW_API_KEY_PROVIDERS"))


def require_api_key_provider_opt_in(provider_name: str) -> None:
    """Fail API-key-backed providers unless the host deliberately enables them."""
    if api_key_providers_enabled():
        return
    from workflow.exceptions import ProviderUnavailableError

    raise ProviderUnavailableError(
        f"{provider_name} is API-key-backed and disabled by default. "
        "Workflow daemons are subscription-only unless the host deliberately "
        "sets WORKFLOW_ALLOW_API_KEY_PROVIDERS=1 for this daemon."
    )


def subprocess_env_without_api_keys() -> dict[str, str] | None:
    """Return a subprocess env that ignores API-key auth unless opted in."""
    if api_key_providers_enabled():
        return None
    env = os.environ.copy()
    for name in API_KEY_PROVIDER_ENV_VARS:
        env.pop(name, None)
    return env


# bwrap failure signature emitted to stderr on Linux hosts that lack
# unprivileged user namespaces. When this appears the CLI silently wrote
# the error to state and returned exit=0 — hard-rule #8 demands we detect
# and raise rather than let the garbage propagate.
_BWRAP_FAILURE_PATTERNS: tuple[str, ...] = (
    "bwrap: No permissions to create a new namespace",
    "bwrap: No permissions to create new namespace",
    "bwrap: No such file or directory",
    "sandbox initialization failed",
)


class SandboxUnavailableError(Exception):
    """Raised when bwrap / sandbox is unavailable on the host.

    Carries the exact stderr excerpt so callers can surface guidance.
    """


def check_bwrap_failure(stderr_text: str) -> None:
    """Raise SandboxUnavailableError if *stderr_text* contains a bwrap error.

    Called by subprocess-backed providers after every CLI invocation so the
    failure is loud (raises) rather than silent (appears in state as output).
    No-op on Windows (bwrap is Linux-only).
    """
    import sys as _sys
    if _sys.platform == "win32":
        return
    lower = stderr_text.lower()
    for pattern in _BWRAP_FAILURE_PATTERNS:
        if pattern.lower() in lower:
            raise SandboxUnavailableError(
                f"Sandbox (bwrap) is unavailable on this host. "
                f"The CLI subprocess emitted a sandboxing failure:\n"
                f"  {stderr_text[:400].strip()}\n\n"
                f"Fix options:\n"
                f"  1. Enable unprivileged user namespaces: "
                f"sysctl -w kernel.unprivileged_userns_clone=1\n"
                f"  2. Use a branch that contains only design-only nodes "
                f"(requires_sandbox=false). These nodes don't need bwrap.\n"
                f"  3. Run the daemon on a host where bwrap is available."
            )


def probe_sandbox_available() -> dict[str, object]:
    """Probe whether bwrap is available on this host.

    Returns {bwrap_available: bool, reason: str | None}.  Cached at
    module level after first call so get_status probes once at startup.
    """
    import shutil as _shutil
    import subprocess as _subprocess
    import sys as _sys

    if _sys.platform == "win32":
        return {"bwrap_available": False, "reason": "bwrap is Linux-only (win32 host)"}

    bwrap_path = _shutil.which("bwrap")
    if not bwrap_path:
        return {"bwrap_available": False, "reason": "bwrap not found on PATH"}

    try:
        version_result = _subprocess.run(
            [bwrap_path, "--version"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if version_result.returncode != 0:
            return {
                "bwrap_available": False,
                "reason": (
                    f"bwrap --version exited {version_result.returncode}: "
                    f"{version_result.stderr[:200]}"
                ),
            }

        launch_result = _subprocess.run(
            [bwrap_path, "--ro-bind", "/", "/", "/bin/sh", "-c", "true"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if launch_result.returncode == 0:
            return {"bwrap_available": True, "reason": None}
        excerpt = (
            launch_result.stderr.strip()
            or launch_result.stdout.strip()
            or "no output"
        )
        return {
            "bwrap_available": False,
            "reason": (
                f"bwrap functional probe exited {launch_result.returncode}: "
                f"{excerpt[:200]}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"bwrap_available": False, "reason": f"probe error: {exc}"}


# Module-level cache populated on first get_status call.
_sandbox_probe_cache: dict[str, object] | None = None


def get_sandbox_status() -> dict[str, object]:
    """Return cached sandbox probe result (probes once per process)."""
    global _sandbox_probe_cache  # noqa: PLW0603
    if _sandbox_probe_cache is None:
        _sandbox_probe_cache = probe_sandbox_available()
    return _sandbox_probe_cache


class BaseProvider(abc.ABC):
    """Abstract base for all LLM providers."""

    name: str = ""
    """Short identifier used in fallback chains (e.g. ``'claude-code'``)."""

    family: str = ""
    """Model family for judge diversity enforcement."""

    @classmethod
    def is_available(cls) -> bool:
        """Return True if this provider's binary/dependency is present.

        Subprocess-backed providers override this to probe the binary with
        ``shutil.which`` so the router skips registration on cloud hosts
        where the CLI is absent — avoiding 30s+ wasted cooldowns per call.
        """
        return True

    @abc.abstractmethod
    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
    ) -> ProviderResponse:
        """Send *prompt* with *system* instructions and return a response."""
