"""Claude provider -- ``claude -p`` subprocess.

Covered by the Claude Max subscription.  No API credits consumed.
Exit code 1 within 5 seconds signals API unavailability and triggers
a sticky cooldown in the router.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tinyassets.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    check_bwrap_failure,
    cleanup_sandbox_job_dir,
    enforce_os_sandbox,
    sandbox_spawn_env_and_dir,
)


def _no_window_kwargs() -> dict:
    """Return subprocess kwargs to suppress console windows on Windows."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _resolve_claude_cmd() -> tuple[list[str], bool]:
    """Resolve the claude command, handling Windows .cmd/.bat wrappers.

    Returns (base_cmd, use_shell) where base_cmd is the command prefix
    and use_shell indicates whether to use shell execution.
    """
    claude_path = shutil.which("claude")
    if claude_path and sys.platform == "win32" and claude_path.lower().endswith((".cmd", ".bat")):
        return [claude_path], True
    return ["claude"], False


def _sandbox_cli_args(
    config: ModelConfig, universe_dir: Path | None
) -> tuple[list[str], str | None]:
    """Build tool-policy flags + isolated cwd for a sandboxed subprocess turn.

    Returns ``(extra_cmd_flags, run_cwd)``. This is the P0 isolation seam for the
    founder-facing universe-intelligence turn (2026-07-03 live-test finding): the
    universe engine must NOT inherit the daemon's checkout (repo source,
    ``CLAUDE.md``, other universes) nor keep host tools (Bash → arbitrary host
    commands / clone / gh). ``--disallowedTools`` is the hard floor that denies
    shell escape even if a settings file would grant it; ``run_cwd`` pins the
    subprocess to the universe's own dir. Both are no-ops for host-trusted roles
    that leave the config fields at their defaults.
    """
    flags: list[str] = []
    # Strip ambient MCP + user config for BOTH hardened profiles: the founder
    # conversation (``sandbox_workspace``) and the coding node
    # (``os_sandbox_required``).
    hardened = bool(config.sandbox_workspace or config.os_sandbox_required)
    if hardened:
        # Load ONLY project-tier settings. A universe dir is bare, so this loads
        # NOTHING — critically it excludes the USER's global settings, which carry
        # MCP servers and `bypassPermissions`. Without it, the sandboxed engine
        # still inherits the user's MCP tools (verified 2026-07-03: it saw
        # `mcp__codex__codex`), so a founder's universe could call e.g. Codex →
        # arbitrary code execution, fully bypassing the Bash deny. This strips all
        # ambient MCP + config from the hardened turn.
        flags += ["--setting-sources", "project"]
    allowed = config.allowed_tools
    disallowed = config.disallowed_tools
    # ``--allowedTools``/``--disallowedTools`` are variadic (<tools...>): each
    # tool is its OWN argv token, not one space-joined string (a joined string is
    # read as a single bogus tool name and silently matches nothing).
    if allowed:
        flags += ["--allowedTools", *allowed]
    if disallowed:
        flags += ["--disallowedTools", *disallowed]
    # Fail-closed (2026-07-03 P0 review, Codex ADAPT): a founder-conversation
    # sandbox with no universe_dir would inherit the daemon's cwd (the checkout)
    # — the exact leak this fixes. Refuse rather than silently run un-isolated.
    # (A coding node runs IN the checked-out repo, so it does not require a
    # universe_dir; its confinement is the OS sandbox enforced separately by
    # enforce_os_sandbox() before the subprocess spawns.)
    if config.sandbox_workspace and universe_dir is None:
        raise ProviderError(
            "sandboxed universe turn requires a universe_dir — refusing to run "
            "un-isolated in the daemon's working directory (fail-closed)."
        )
    # Pin cwd to the isolated dir when one is supplied for a hardened turn (the
    # universe dir for a conversation; a checked-out repo dir when threaded for a
    # coding node). Otherwise leave cwd unset so a coding node runs in the
    # daemon's repo checkout, confined by the OS sandbox.
    run_cwd = str(universe_dir) if (hardened and universe_dir is not None) else None
    return flags, run_cwd


class ClaudeProvider(BaseProvider):
    """Calls Claude via the ``claude -p`` CLI binary."""

    name = "claude-code"
    family = "anthropic"

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("claude") is not None

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        # Coding-node fail-closed gate: if this call requires an OS sandbox and
        # none is available, refuse BEFORE spawning rather than run a coding
        # agent unconfined against the host (hard rule #8).
        enforce_os_sandbox(config)
        base_cmd, use_shell = _resolve_claude_cmd()
        cmd = [*base_cmd, "-p"]
        if system:
            cmd.extend(["--system-prompt", system])
        extra_flags, run_cwd = _sandbox_cli_args(config, universe_dir)
        cmd.extend(extra_flags)
        # Defense-in-depth for a SANDBOX-REQUIRED coding node (Codex S3 round-3):
        # even under host attestation, spawn with a SANITIZED minimal env (only
        # this provider's own auth — no cross-tenant secrets to `env`-dump) and
        # pin cwd to a fresh per-job scratch dir (not the repo, not /data).
        # No-op for host-trusted calls (normal env, scratch_dir=None).
        proc_env, scratch_dir = sandbox_spawn_env_and_dir(
            self.name, config, universe_dir=universe_dir,
        )
        if scratch_dir is not None:
            run_cwd = scratch_dir
        try:
            win_kw = _no_window_kwargs()
            if use_shell:
                proc = await asyncio.create_subprocess_shell(
                    shlex.join(cmd),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=proc_env,
                    cwd=run_cwd,
                    **win_kw,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=proc_env,
                    cwd=run_cwd,
                    **win_kw,
                )

            start = time.monotonic()

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=prompt.encode("utf-8")),
                    timeout=config.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise ProviderTimeoutError(
                    f"claude -p exceeded {config.timeout}s timeout"
                )

            elapsed_ms = (time.monotonic() - start) * 1000

            # Exit code 1 within 5 seconds => API unavailable (sticky cooldown)
            if proc.returncode == 1 and elapsed_ms < 5000:
                raise ProviderUnavailableError(
                    "claude -p returned exit code 1 quickly -- API likely unavailable"
                )

            # Windows-specific crash codes: treat as unavailable so the
            # router applies cooldown instead of retrying immediately.
            # 0xC0000374 (3221225588) = heap corruption
            # 0xC0000005 (3221225477) = access violation
            # 0xC000013A (3221225786) = control-C / abnormal termination
            _WINDOWS_CRASH_CODES = {3221225588, 3221225477, 3221225786}
            if proc.returncode in _WINDOWS_CRASH_CODES:
                raise ProviderUnavailableError(
                    f"claude -p crashed with Windows exit code {proc.returncode:#x} "
                    f"— subprocess failure, applying cooldown"
                )

            stderr_text = stderr.decode(errors="replace")
            check_bwrap_failure(stderr_text)

            if proc.returncode != 0:
                raise ProviderError(
                    f"claude -p exit {proc.returncode}: {stderr_text}"
                )

            text = stdout.decode("utf-8", errors="replace").strip()

            return ProviderResponse(
                text=text,
                provider=self.name,
                model="claude",
                family=self.family,
                latency_ms=elapsed_ms,
            )
        finally:
            cleanup_sandbox_job_dir(scratch_dir)

    async def complete_json(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        """Call with ``--output-format json`` for structured output."""
        # Coding-node fail-closed gate (see complete()): refuse before spawning
        # when an OS sandbox is required but unavailable.
        enforce_os_sandbox(config)
        base_cmd, use_shell = _resolve_claude_cmd()
        cmd = [*base_cmd, "-p", "--output-format", "json"]
        if system:
            cmd.extend(["--system-prompt", system])
        extra_flags, run_cwd = _sandbox_cli_args(config, universe_dir)
        cmd.extend(extra_flags)
        # Same sandbox-required posture as complete(): sanitized env + per-job
        # scratch cwd for a coding node; normal env / no scratch otherwise.
        proc_env, scratch_dir = sandbox_spawn_env_and_dir(
            self.name, config, universe_dir=universe_dir,
        )
        if scratch_dir is not None:
            run_cwd = scratch_dir
        try:
            win_kw = _no_window_kwargs()
            if use_shell:
                proc = await asyncio.create_subprocess_shell(
                    shlex.join(cmd),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=proc_env,
                    cwd=run_cwd,
                    **win_kw,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=proc_env,
                    cwd=run_cwd,
                    **win_kw,
                )

            start = time.monotonic()

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=prompt.encode("utf-8")),
                    timeout=config.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise ProviderTimeoutError("claude -p (json) timed out")

            elapsed_ms = (time.monotonic() - start) * 1000

            if proc.returncode == 1 and elapsed_ms < 5000:
                raise ProviderUnavailableError(
                    "claude -p (json) returned exit code 1 quickly"
                )

            _WINDOWS_CRASH_CODES = {3221225588, 3221225477, 3221225786}
            if proc.returncode in _WINDOWS_CRASH_CODES:
                raise ProviderUnavailableError(
                    f"claude -p (json) crashed with Windows exit code "
                    f"{proc.returncode:#x} — applying cooldown"
                )

            stderr_text_json = stderr.decode(errors="replace")
            check_bwrap_failure(stderr_text_json)

            if proc.returncode != 0:
                raise ProviderError(
                    f"claude -p (json) exit {proc.returncode}: {stderr_text_json}"
                )

            raw = stdout.decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            text = parsed.get("result", raw)
        finally:
            cleanup_sandbox_job_dir(scratch_dir)

        return ProviderResponse(
            text=text,
            provider=self.name,
            model="claude",
            family=self.family,
            latency_ms=elapsed_ms,
        )
