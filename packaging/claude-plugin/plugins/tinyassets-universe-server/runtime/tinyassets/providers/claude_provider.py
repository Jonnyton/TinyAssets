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


def _engine_mcp_flags(config: ModelConfig, universe_dir: Path) -> list[str]:
    """Wire the local, founder-scoped TinyAssets MCP server into the engine turn.

    Founder directive 2026-08-12: the universe agent ("Tiny") gets the SAME MCP
    handles the founder's browser chatbot has. This writes a per-universe
    ``--mcp-config`` pointing at ``python -m tinyassets.engine_mcp_server`` and
    returns the flags that admit EXACTLY that one server:

      * ``--strict-mcp-config`` — grants ONLY the servers in ``--mcp-config`` and
        excludes the logged-in claude.ai account connectors (Google Drive /
        codex → code exec). Verified 2026-08-13: with strict + a single-server
        config, ``mcp__codex__codex`` is unreachable — this is what actually
        closes the 2026-07-03 ambient-MCP leak, not ``--setting-sources``.

    FAIL-CLOSED: the engine MCP is wired only when the founder actor_id AND the
    universe graph_id are both present; a missing either returns no flags so the
    turn stays WebFetch-only rather than exposing tools with an unbound identity.
    The server itself binds ``_current_identity`` to the founder and pins every
    handler to ``engine_mcp_graph_id`` (see ``tinyassets.engine_mcp_server``).
    """
    actor_id = (config.engine_mcp_actor_id or "").strip()
    graph_id = (config.engine_mcp_graph_id or "").strip()
    if not (actor_id and graph_id):
        return []
    import json as _json
    import os as _os
    import sys as _sys

    # Config lives in the sandboxed universe_dir (the engine has no filesystem
    # read tool, so it never sees it). It carries only identifiers — the founder
    # actor_id + graph_id + data root — never a secret. Overwritten each turn.
    config_path = universe_dir / ".engine_mcp_config.json"
    server_env = {
        "TINYASSETS_ENGINE_ACTOR_ID": actor_id,
        "TINYASSETS_ENGINE_GRAPH_ID": graph_id,
    }
    data_dir = _os.environ.get("TINYASSETS_DATA_DIR", "").strip()
    if data_dir:
        server_env["TINYASSETS_DATA_DIR"] = data_dir
    # The stdio server runs `python -m tinyassets.engine_mcp_server` with the
    # engine's cwd (the universe dir) — NOT the daemon's package root. When the
    # daemon runs from a checkout/image dir (e.g. /app) rather than a
    # site-packages install, the child cannot import `tinyassets` without the
    # package root on PYTHONPATH (reproduced in the local e2e: every tool call
    # failed "No module named 'tinyassets'"). Propagate the exact root the
    # daemon itself imported from, ahead of any existing PYTHONPATH.
    import tinyassets as _pkg

    pkg_root = str(Path(_pkg.__file__).resolve().parent.parent)
    existing = _os.environ.get("PYTHONPATH", "").strip()
    server_env["PYTHONPATH"] = (
        f"{pkg_root}{_os.pathsep}{existing}" if existing else pkg_root
    )
    mcp_config = {
        "mcpServers": {
            "tinyassets": {
                "command": _sys.executable,
                "args": ["-m", "tinyassets.engine_mcp_server"],
                "env": server_env,
            }
        }
    }
    try:
        config_path.write_text(_json.dumps(mcp_config), encoding="utf-8")
    except OSError:
        # If we cannot write the config, fail closed to WebFetch-only rather than
        # passing --mcp-config a missing path (which would error the whole turn).
        return []
    return ["--mcp-config", str(config_path), "--strict-mcp-config"]


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
    # Founder-scoped engine MCP: only inside the sandbox (universe_dir present),
    # and only when the caller opted in with a bound founder + universe. The
    # matching ``mcp__tinyassets__*`` handles are added to ``allowed_tools`` by
    # the caller (universe_intelligence._sandboxed_config).
    if config.engine_mcp_enabled and universe_dir is not None:
        engine_flags = _engine_mcp_flags(config, universe_dir)
        # FAIL CLOSED (Codex ADAPT 2026-08-13 #1): when engine MCP is on, the
        # caller has ALREADY relaxed the tool policy — it dropped the ``mcp__*``
        # wildcard deny so the tinyassets handles are admittable, trusting that
        # ``--strict-mcp-config`` will exclude every OTHER (ambient account)
        # connector. If the config could not be written (``_engine_mcp_flags``
        # returned no ``--strict-mcp-config``), running anyway would fail OPEN —
        # ambient connectors would load with neither the wildcard deny NOR strict
        # mode. Refuse the turn instead of silently downgrading isolation.
        if "--strict-mcp-config" not in engine_flags:
            raise ProviderError(
                "engine MCP was requested but --strict-mcp-config could not be "
                "installed; refusing to run with a relaxed tool policy that would "
                "expose ambient MCP connectors (fail-closed)."
            )
        flags += engine_flags
    run_cwd = str(universe_dir) if config.sandbox_workspace else None
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
        base_cmd, use_shell = _resolve_claude_cmd()
        cmd = [*base_cmd, "-p"]
        if system:
            cmd.extend(["--system-prompt", system])
        extra_flags, run_cwd = _sandbox_cli_args(config, universe_dir)
        cmd.extend(extra_flags)
        proc_env = subprocess_env_for_provider(self.name, universe_dir=universe_dir)

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
