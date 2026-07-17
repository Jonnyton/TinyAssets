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
    SandboxUnavailableError,
    check_bwrap_failure,
    subprocess_env_for_provider,
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
    if config.sandbox_workspace:
        # Load ONLY project-tier settings. A universe dir is bare, so this loads
        # NOTHING — critically it excludes the USER's global settings, which carry
        # MCP servers and `bypassPermissions`. Without it, the sandboxed engine
        # still inherits the user's MCP tools (verified 2026-07-03: it saw
        # `mcp__codex__codex`), so a founder's universe could call e.g. Codex →
        # arbitrary code execution, fully bypassing the Bash deny. This strips all
        # ambient MCP + config from the founder-facing turn.
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
    # Fail-closed (2026-07-03 P0 review, Codex ADAPT): a sandboxed turn with no
    # universe_dir would inherit the daemon's cwd (the checkout) — the exact leak
    # this fixes. Refuse rather than silently run un-isolated.
    if config.sandbox_workspace and universe_dir is None:
        raise ProviderError(
            "sandboxed universe turn requires a universe_dir — refusing to run "
            "un-isolated in the daemon's working directory (fail-closed)."
        )
    run_cwd = str(universe_dir) if config.sandbox_workspace else None
    return flags, run_cwd


def _byo_scratch_dir(universe_dir: Path | None) -> str | None:
    """Return an empty per-universe SCRATCH cwd for a hardened BYO launch.

    Round-14 #2: a hardened spawn must NOT keep ``cwd=None`` (which inherits the
    daemon's checkout — repo source / other universes). Pin cwd to an isolated
    EMPTY scratch dir so, even before OS-level sandboxing, the process starts in a
    directory with nothing sensitive. ``None`` (no universe) falls back to the
    caller's cwd resolution — but hardened spawns always carry a universe_dir.
    """
    if universe_dir is None:
        return None
    scratch = Path(universe_dir) / ".credentials" / "claude-byo-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    return str(scratch)


def _byo_hardening_flags(proc_env: dict[str, str]) -> list[str]:
    """Return the CLI hardening flags for a BYO-bound claude -p launch, or [].

    Triggered by ``CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`` — the ONE byo-bound signal
    ``subprocess_env_for_provider`` sets (round-13 #1) after it has scrubbed every
    host credential from the child env.

    Round-16 #5 / round-17 #1: hardening is an ALLOWLIST (default-deny), NOT a
    denylist. A denylist fails OPEN on any new built-in / skill; an EMPTY allowlist
    fails CLOSED — nothing is permitted unless explicitly added. ``--bare`` already
    disables MCP servers, hooks, plugins, keychain/OAuth and ambient instructions.
    The tool floor is the empty ``--tools ""`` set — NOT ``--allowedTools ""``.
    ``--allowedTools`` only PRE-APPROVES tools (removes the permission prompt); it
    does NOT restrict AVAILABILITY, so under ``--bare`` the child would still expose
    Bash/Read/Edit (round-17 #1 critical: the r16 flag was fail-open). ``--tools ""``
    is the closed tool surface — the exact flag S3 uses for its closed text node —
    which disables ALL built-in tools (file Read/Edit/Write, shell, web). Phase-2
    explicitly ADDS only the capabilities a real BYO turn needs — pairs with the
    sandbox runner's OS isolation (execution stays dark until sandbox attestation,
    so this interim is belt-and-suspenders). Real-binary enforcement (Bash/Read
    genuinely unavailable) is a Phase-2 rollout gate — see the skipped
    ``test_byo_hardening_real_binary_tools_unavailable`` regression.
    """
    if proc_env.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") != "1":
        return []
    return ["--bare", "--tools", ""]


def _refuse_hardened_byo_shell(hardening: list[str], use_shell: bool) -> None:
    """Fail closed for a BYO-hardened claude call routed through a shell wrapper.

    Round-17 #1 (mirrors S3's ``_refuse_hardened_shell``): a ``.cmd``/``.bat`` claude
    wrapper is spawned via ``shlex.join(cmd)`` through ``cmd.exe``, where POSIX
    single-quotes are LITERAL — the security-critical empty ``--tools ""`` becomes
    literal ``''`` (which does NOT disable tools), silently UN-hardening the spawn.
    Refuse rather than run a BYO turn on the host's checkout with tools still live;
    the router then routes to another capable provider or fails loud (Hard Rule #8).
    Only fires when hardening is actually active (a byo-bound spawn) AND the install
    is shell-wrapped; native-executable installs are unaffected.
    """
    if hardening and use_shell:
        raise SandboxUnavailableError(
            "Hardened BYO claude call (closed tool surface) cannot run through the "
            "Windows .cmd/.bat shell wrapper: shlex.join under cmd.exe mangles the "
            "security-critical empty --tools \"\" into literal '', silently "
            "un-hardening the spawn (tools stay live). Refusing (fail closed). Use a "
            "native claude executable (not a .cmd/.bat wrapper) on hosts that run "
            "hardened BYO engines."
        )


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
        base_cmd, use_shell = _resolve_claude_cmd()
        cmd = [*base_cmd, "-p"]
        if system:
            cmd.extend(["--system-prompt", system])
        extra_flags, run_cwd = _sandbox_cli_args(config, universe_dir)
        cmd.extend(extra_flags)
        proc_env = subprocess_env_for_provider(self.name, universe_dir=universe_dir)
        hardening = _byo_hardening_flags(proc_env)  # round-13 #1: --bare + tool floor
        _refuse_hardened_byo_shell(hardening, use_shell)  # round-17 #1: fail closed
        cmd.extend(hardening)
        if hardening:  # round-14 #2: pin a hardened BYO spawn to an empty scratch cwd
            run_cwd = _byo_scratch_dir(universe_dir) or run_cwd

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

    async def complete_json(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        """Call with ``--output-format json`` for structured output."""
        base_cmd, use_shell = _resolve_claude_cmd()
        cmd = [*base_cmd, "-p", "--output-format", "json"]
        if system:
            cmd.extend(["--system-prompt", system])
        extra_flags, run_cwd = _sandbox_cli_args(config, universe_dir)
        cmd.extend(extra_flags)
        proc_env = subprocess_env_for_provider(self.name, universe_dir=universe_dir)
        hardening = _byo_hardening_flags(proc_env)  # round-13 #1: --bare + tool floor
        _refuse_hardened_byo_shell(hardening, use_shell)  # round-17 #1: fail closed
        cmd.extend(hardening)
        if hardening:  # round-14 #2: pin a hardened BYO spawn to an empty scratch cwd
            run_cwd = _byo_scratch_dir(universe_dir) or run_cwd

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

        return ProviderResponse(
            text=text,
            provider=self.name,
            model="claude",
            family=self.family,
            latency_ms=elapsed_ms,
        )
