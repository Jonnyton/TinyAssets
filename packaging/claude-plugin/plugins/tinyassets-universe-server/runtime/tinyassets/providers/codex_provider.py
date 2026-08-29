"""Codex / GPT provider -- ``codex exec`` subprocess.

Covered by the ChatGPT Plus subscription.  Different model family from
Claude, making it ideal as a judge when Claude is the writer.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tinyassets.exceptions import (
    InteractiveDeadlineError,
    ProviderError,
    ProviderIdleTimeoutError,
    ProviderProtocolError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    check_bwrap_failure,
    get_sandbox_status,
    subprocess_env_for_provider,
)
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS

logger = logging.getLogger(__name__)


def _no_window_kwargs() -> dict:
    """Return subprocess kwargs to suppress console windows on Windows."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _resolve_codex_cmd() -> tuple[list[str], bool]:
    """Resolve the codex command, handling Windows .cmd/.bat wrappers.

    Returns (base_cmd, use_shell) where base_cmd is the command prefix
    and use_shell indicates whether to use shell execution.
    """
    codex_path = shutil.which("codex")
    if codex_path and sys.platform == "win32" and codex_path.lower().endswith((".cmd", ".bat")):
        return [codex_path], True
    if codex_path:
        return [codex_path], False
    return ["codex"], False


_CODEX_BIN_ASSIGNMENT = re.compile(
    r"(?m)^\s*CODEX_BIN\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|(\S+))\s*$"
)


def _resolved_codex_executable(base_cmd: list[str]) -> tuple[Path, Path]:
    """Return the invoked wrapper and the real executable it delegates to."""

    if not base_cmd:
        raise ProviderError("codex served sandbox cannot resolve an empty command")
    wrapper = Path(base_cmd[0]).expanduser()
    if not wrapper.is_absolute():
        located = shutil.which(str(wrapper))
        if not located:
            raise ProviderError("codex served sandbox cannot resolve the executable")
        wrapper = Path(located)
    try:
        wrapper = Path(os.path.abspath(wrapper))
        resolved = wrapper.resolve(strict=True)
    except OSError as exc:
        raise ProviderError(
            "codex served sandbox cannot resolve the executable"
        ) from exc
    real_executable = resolved
    if wrapper == resolved:
        try:
            with wrapper.open("rb") as stream:
                wrapper_text = stream.read(65_536).decode("utf-8", errors="strict")
        except (OSError, UnicodeError):
            wrapper_text = ""
        if "CODEX_BIN" in wrapper_text:
            match = _CODEX_BIN_ASSIGNMENT.search(wrapper_text)
            if match is None:
                raise ProviderError(
                    "codex served sandbox cannot resolve the wrapper's real binary"
                )
            try:
                raw_real_executable = next(
                    value for value in match.groups() if value is not None
                )
                real_path = Path(raw_real_executable)
                if not real_path.is_absolute():
                    raise OSError("wrapper target is not absolute")
                real_executable = real_path.resolve(strict=True)
            except OSError as exc:
                raise ProviderError(
                    "codex served sandbox cannot resolve the wrapper's real binary"
                ) from exc
    if not real_executable.is_file():
        raise ProviderError("codex served sandbox resolved binary is not a file")
    return wrapper, real_executable


def _codex_binary_tree(real_executable: Path) -> Path:
    for ancestor in real_executable.parents:
        if ancestor.name == "node_modules":
            tree = ancestor.parent
            break
    else:
        tree = real_executable.parent
    if not tree.is_dir():
        raise ProviderError("codex served sandbox cannot mount the resolved binary tree")
    return tree


_SECRET_SHAPES = re.compile(
    # Explicit secret shapes only (a generic long-token rule also hid hashes,
    # paths and model ids — the real cause). JWT fragments: any `eyJ…` run,
    # with or without the dotted tail.
    r"(sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_.-]{10,}|"
    r"(?i:bearer\s+\S+)|(?i:(?:token|secret|api[_-]?key|password)[\"']?\s*[:=]\s*\S+))"
)


def _redacted_stderr_excerpt(stderr_text: str, limit: int = 240) -> str:
    """The last stderr line, secrets replaced, as a head+tail excerpt.

    Feeds user-visible diagnostics (router chain_state), so it must be safe
    even if codex ever echoes credential material. Head+tail (not a plain
    prefix) because codex 0.135 appends its auth error code at the END of
    the line."""
    lines = [line.strip() for line in stderr_text.strip().splitlines() if line.strip()]
    if not lines:
        return "(no stderr)"
    text = _SECRET_SHAPES.sub("[redacted]", lines[-1])
    if len(text) <= limit:
        return text
    half = (limit - 5) // 2
    return text[:half] + " ... " + text[-half:]


def _codex_home_file_mounts(codex_home: Path) -> list[str]:
    """``--ro-bind`` args for each regular file of the sealed snapshot."""
    args: list[str] = []
    for entry in sorted(codex_home.iterdir()):
        if entry.is_symlink() or not entry.is_file():
            continue
        args.extend(("--ro-bind", str(entry), f"/codex-home/{entry.name}"))
    if not args:
        raise ProviderError("codex served sandbox found no credential files to mount")
    return args


def _codex_sandbox_mounts(base_cmd: list[str]) -> tuple[Path, ...]:
    wrapper, real_executable = _resolved_codex_executable(base_cmd)
    candidates = [_codex_binary_tree(real_executable)]
    covered_roots = tuple(Path(path) for path in ("/usr", "/bin", "/lib", "/lib64"))
    if not any(wrapper.is_relative_to(root) for root in covered_roots):
        candidates.append(wrapper.parent)
    mounts: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve(strict=True)
        if resolved not in mounts:
            mounts.append(resolved)
    return tuple(mounts)


_VALID_CODEX_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})


def _reasoning_effort_args(effort: str | None) -> list[str]:
    """Map a generic ModelConfig.reasoning_effort to Codex's CLI override.

    Codex honors ``-c model_reasoning_effort=<minimal|low|medium|high|xhigh>``.
    Empty / unknown values yield no flag (provider default), so the knob is a
    pure opt-in and never breaks a call.
    """
    normalized = (effort or "").strip().lower()
    if normalized in _VALID_CODEX_EFFORTS:
        return ["-c", f"model_reasoning_effort={normalized}"]
    return []


def _codex_model() -> str:
    """Return the Codex CLI model to request for provider calls."""
    return os.environ.get("TINYASSETS_CODEX_MODEL", "gpt-5.4").strip() or "gpt-5.4"


def _codex_workdir() -> str:
    """Return the source workspace Codex should inspect for coding tasks."""
    configured = os.environ.get("TINYASSETS_CODEX_WORKDIR", "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parents[2])


#: Env var codex reads the engine-MCP bearer from (``bearer_token_env_var``). The
#: secret lands in the codex subprocess env, NOT on argv or in the prompt — so the
#: served model never sees it (mirrors claude_provider's --mcp-config headers).
_ENGINE_MCP_BEARER_ENV = "TINYASSETS_ENGINE_MCP_BEARER"

#: Exactly the engine tools the served agent may call (codex ``enabled_tools``).
#: Belt-and-suspenders with the server's own registration: even if a tool is
#: added to the server, it is not callable unless listed here. PUBLISH is
#: deliberately absent (deferred to the consent-gated slice — Codex ADAPT #5).
# run_graph + write_graph ARE included (2026-08-23): the invoke_branch closure is
# now sanitized (#2498), so a run/build reaching a public branch is safe.
# remix_shape (cross-author fork) stays EXCLUDED pending its own review slice.
# Served engine-MCP allowlist — the SINGLE canonical list from served_tools.py,
# shared verbatim with the claude surface (universe_intelligence._ENGINE_MCP_TOOLS)
# so the two provider surfaces CANNOT drift (founder rule: all surfaces do the same
# things). To change what the served agent can do, edit served_tools.py once.
_ENGINE_MCP_ENABLED_TOOLS = SERVED_ENGINE_MCP_TOOLS

#: Force the served CWD project untrusted so codex never loads a project-level
#: ``/workspace/.codex/config.toml`` (which a crafted universe could ship with its
#: OWN ``mcp_servers``). Codex ADAPT 2026-08-22 #3: ``-c mcp_servers={...}``
#: MERGES rather than replaces, so eliminating every lower-precedence config
#: source — not a blanket ``mcp_servers={}`` clear (a no-op) — is what keeps the
#: injected server the only one. Applied to every served turn.
_UNTRUSTED_WORKSPACE_ARGS = ("-c", 'projects."/workspace".trust_level="untrusted"')


def _codex_engine_mcp_args(config: ModelConfig, proc_env: dict[str, str]) -> list[str]:
    """The ``-c`` config args governing the served codex turn's MCP surface.

    Always forces ``/workspace`` untrusted so no project ``.codex/config.toml``
    (and its ``mcp_servers``) loads. Then, when the founder-scoped engine MCP is
    enabled AND a per-universe HTTP engine server is running (its loopback
    ``url`` + ``secret`` in ``.engine_mcp_http_routes.json``, written 0600 by
    ``engine_mcp_http``), wires codex to that ONE trusted server — the same
    commons + own-universe handles the browser chatbot has — restricted to
    ``enabled_tools`` and marked ``required``, and injects the bearer into
    ``proc_env`` (codex reads it via ``bearer_token_env_var``, keeping it off
    argv/prompt). This is the codex analogue of
    ``claude_provider._engine_mcp_flags``.

    Injection safety (verified against codex-cli 0.146, 2026-08-22): ``-c
    mcp_servers={...}`` MERGES rather than replaces, so a served turn is kept to
    exactly this one server by eliminating every other source —
    ``--ignore-user-config`` drops ``$CODEX_HOME/config.toml``; the untrusted
    ``/workspace`` skips project config; the chat turn's ``/workspace`` is an
    empty tmpfs anyway; and ``--disable apps`` removes account ChatGPT connectors.

    FAIL CLOSED: engine MCP requested but no running HTTP server (no route / no
    secret) -> add no server (WebFetch-only), never a half-wired or
    unauthenticated one. stdio is not an option (the package is not in the jail).
    """
    args = list(_UNTRUSTED_WORKSPACE_ARGS)
    if not (
        getattr(config, "engine_mcp_enabled", False)
        and (getattr(config, "engine_mcp_actor_id", "") or "").strip()
        and (getattr(config, "engine_mcp_graph_id", "") or "").strip()
    ):
        return args
    graph_id = config.engine_mcp_graph_id.strip()
    data_dir = (
        proc_env.get("TINYASSETS_DATA_DIR")
        or os.environ.get("TINYASSETS_DATA_DIR")
        or ""
    ).strip()
    url = ""
    secret = ""
    try:
        routes_path = Path(data_dir or ".") / ".engine_mcp_http_routes.json"
        if routes_path.is_file():
            routes = json.loads(routes_path.read_text(encoding="utf-8"))
            if isinstance(routes, dict):
                entry = routes.get(graph_id)
                if isinstance(entry, dict):
                    url = str(entry.get("url") or "").strip()
                    secret = str(entry.get("secret") or "").strip()
    except Exception:  # noqa: BLE001 - never break a turn on a bad route file
        url = ""
        secret = ""
    if not (url and secret):
        return args
    # A malformed url containing a double-quote would break the inline TOML; a
    # loopback engine url never does, but refuse rather than emit broken config.
    if '"' in url:
        return args
    proc_env[_ENGINE_MCP_BEARER_ENV] = secret
    enabled = ",".join(f'"{t}"' for t in _ENGINE_MCP_ENABLED_TOOLS)
    # Dotted key merges the one server into the (otherwise-empty) map.
    # default_tools_approval_mode="approve": codex MCP tools default to `auto`,
    # which requires per-call approval; a non-interactive served `codex exec` has
    # no approver, so the prompt auto-cancels ("user cancelled MCP tool call").
    # Auto-approve this ONE trusted, enabled_tools-restricted server so its tools
    # actually execute (Codex diagnosis 2026-08-22; verified key parses on 0.146).
    server = (
        "mcp_servers.tinyassets={"
        f'url="{url}",bearer_token_env_var="{_ENGINE_MCP_BEARER_ENV}",'
        f'required=true,default_tools_approval_mode="approve",'
        f"enabled_tools=[{enabled}]"
        "}"
    )
    args += ["-c", server]
    return args


def _terminate(proc) -> None:
    """Kill a provider subprocess, tolerating one that has already exited.

    `proc.kill()` on a finished process raises ProcessLookupError on POSIX, which would
    replace the real exception (often CancelledError) with a confusing one.
    """
    with contextlib.suppress(ProcessLookupError, OSError):
        if proc.returncode is None:
            proc.kill()


# --- streamed reader (parity with claude_provider._read_stream) --------------
#: ``codex exec --json`` item types that mean "the turn is waiting on its own
#: tool". While one is open the idle watchdog stands down: the tool has its own
#: timeout, and a turn waiting on work it asked for is not idle.
_CODEX_TOOL_ITEM_TYPES = frozenset({
    "mcp_tool_call", "command_execution", "web_search", "file_change",
})
#: Event types that count as liveness: the CLI talking in its protocol.
_CODEX_LIVENESS_PREFIXES = ("thread.", "turn.", "item.", "error")
#: Terminal-failure events. They still prove the process is alive, but a tool
#: that was open when the turn failed is not coming back, so the idle watchdog
#: re-arms rather than waiting out the tool allowance (Codex round 2, P1).
_CODEX_TERMINAL_FAILURE_TYPES = frozenset({"turn.failed", "error"})
#: How long a turn may wait on ONE open tool before that wait counts as idle.
#: The tool-in-flight rule exists because a 30s idle budget killed healthy
#: 42s tool calls; but "not idle until the absolute cap" turned a wedged tool
#: into an hour-long wait (Codex round 2, P1). Fifteen minutes covers any run a
#: served tool call launches today and still ends a silent wedge.
_TOOL_WAIT_S = 900.0
#: asyncio's default 64 KiB stream limit raises on one long JSON line. A
#: single ``item.completed`` carrying an MCP result - a GET /contents reply is
#: the base64 of a whole file - can exceed it (Codex round 2, P1: a 70,000-char
#: event raised ``Separator is found, but chunk is longer than limit``). Same
#: bound the claude reader uses; an over-long line is still a protocol error,
#: not a hang.
_STDOUT_READER_LIMIT = 32 * 1024 * 1024


async def _stream_codex_exec(
    proc, stdin_bytes: bytes, config: ModelConfig, *, start: float,
) -> tuple[bytes, bytes]:
    """Read ``codex exec --json`` incrementally under the idle-watchdog profile.

    Founder rule 2026-08-29: *"a turn should continue till finished unless
    interrupted by the user or should stop for some other reason."* The previous
    reader buffered everything under one ``wait_for(communicate(),
    timeout=config.timeout)``, so a productive multi-call turn was killed at
    300s - three clean GitHub round-trips, then the wall clock - and the router
    then cooled the provider for 120s as if it were sick. Claude's streamed
    reader had already moved past that (``claude_provider._read_stream``); this
    gives codex the same profile.

    The genuine stop reasons, and what each raises:

    * **idle** - no protocol event for ``profile.idle_s`` while NOT inside a
      tool call -> :class:`ProviderIdleTimeoutError` (no provider cooldown);
    * **cap** - still progressing past ``profile.absolute_cap_s`` ->
      :class:`InteractiveDeadlineError` (no cooldown; a runaway backstop, not
      a deadline - see ``universe_intelligence._sandboxed_config``).

    A turn waiting on its OWN tool is not idle. ``run_graph`` took 42s live on
    2026-08-29; a 30s idle budget would have killed a healthy turn mid-call,
    which is worse than the cap it replaces. So while an ``item.started`` tool
    item has no matching ``item.completed``, the idle allowance is the absolute
    cap. (Claude's reader does not do this - its ``tool_phase`` is telemetry
    only. Tracked separately; not widened here.)

    Returns ``(stdout_bytes, stderr_bytes)`` exactly as ``communicate()`` did,
    so every downstream parse is unchanged.
    """
    profile = config.stream_timeout_profile()
    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    last_progress = start
    seen_init = False
    seen_progress = False
    tools_in_flight: set[str] = set()
    soft_slo_logged = False

    async def _drain_stderr() -> None:
        try:
            while True:
                chunk = await proc.stderr.read(4096)
                if not isinstance(chunk, (bytes, bytearray)) or not chunk:
                    break
                err_chunks.append(bytes(chunk))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - stderr drain must never break a turn
            return

    async def _feed_stdin() -> None:
        try:
            if proc.stdin is not None:
                proc.stdin.write(stdin_bytes)
                await proc.stdin.drain()
                proc.stdin.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a closed stdin must not break a turn
            return

    stderr_task = asyncio.create_task(_drain_stderr())
    stdin_task = asyncio.create_task(_feed_stdin())

    async def _finish_stderr() -> bytes:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(stderr_task), timeout=2)
        return b"".join(err_chunks)

    def _attach(exc: ProviderError) -> ProviderError:
        exc.attempt_telemetry = {
            "provider": "codex",
            "failure_class": getattr(exc, "failure_class", None),
            "phase": (
                "streaming" if seen_progress else "init" if seen_init else "launch"
            ),
            "tool_phase": "in_tool" if tools_in_flight else None,
            "last_progress_age_ms": (time.monotonic() - last_progress) * 1000,
            "exit_code": proc.returncode,
        }
        return exc

    async def _raise_timeout(bound_is_absolute: bool, allow: float) -> None:
        _terminate(proc)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=5)
        check_bwrap_failure(
            (await _finish_stderr()).decode("utf-8", errors="replace")
        )
        if bound_is_absolute:
            raise _attach(InteractiveDeadlineError(
                f"codex exec exceeded the {profile.absolute_cap_s:.0f}s absolute "
                "interactive cap while still progressing"
            ))
        raise _attach(ProviderIdleTimeoutError(
            f"codex exec produced no protocol event for {allow:.0f}s "
            "(idle watchdog fired; no provider cooldown)"
        ))

    try:
        while True:
            now = time.monotonic()
            if tools_in_flight:
                allow = min(profile.absolute_cap_s, _TOOL_WAIT_S)
            elif not seen_init:
                allow = profile.init_s
            elif not seen_progress:
                allow = profile.first_progress_s
            else:
                allow = profile.idle_s
            idle_deadline = last_progress + allow
            abs_deadline = start + profile.absolute_cap_s
            budget = min(idle_deadline, abs_deadline) - now
            bound_is_absolute = abs_deadline <= idle_deadline
            if budget <= 0:
                await _raise_timeout(bound_is_absolute, allow)
            if not soft_slo_logged and now - start >= profile.soft_slo_s:
                soft_slo_logged = True
                logger.info(
                    "served codex turn exceeded soft SLO %.0fs; still progressing",
                    profile.soft_slo_s,
                )
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=budget)
            except asyncio.TimeoutError:
                await _raise_timeout(bound_is_absolute, allow)
            except (ValueError, asyncio.LimitOverrunError):
                _terminate(proc)
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(proc.wait(), timeout=5)
                await _finish_stderr()
                raise _attach(ProviderProtocolError(
                    "codex exec stream line exceeded the reader buffer limit"
                ))
            if not line:
                break
            out_chunks.append(line)
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except (ValueError, TypeError):
                # Not protocol. Proves the process is alive, not that it is
                # making progress; only real events reset the clock.
                continue
            if not (isinstance(obj, dict) and isinstance(obj.get("type"), str)):
                continue
            etype = obj["type"]
            if etype.startswith(_CODEX_LIVENESS_PREFIXES):
                last_progress = time.monotonic()
                seen_init = True
                seen_progress = True
            if etype in _CODEX_TERMINAL_FAILURE_TYPES:
                tools_in_flight.clear()
            item = obj.get("item")
            if isinstance(item, dict) and item.get("type") in _CODEX_TOOL_ITEM_TYPES:
                key = str(item.get("id") or item.get("type"))
                if etype == "item.started":
                    tools_in_flight.add(key)
                elif etype in ("item.completed", "item.failed"):
                    tools_in_flight.discard(key)
    finally:
        # Every exit path - EOF, a classified raise, a reader exception, or
        # CALLER CANCELLATION - reaps BOTH helper tasks, bounded, so neither
        # drain leaks (Codex round 2, P2; same ownership the claude reader
        # settled on). ``_terminate`` is idempotent and only kills a process
        # that is still running, so a clean exit keeps its real returncode.
        stdin_task.cancel()
        # Let the stderr drain FINISH before cancelling it: on a clean EOF the
        # child's stderr is usually a few bytes still in flight, and cancelling
        # first returned b"" for stderr the caller then parsed for auth /
        # bwrap signals. Bounded, so a child holding fd 2 open cannot hang us.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(stderr_task), timeout=2)
        stderr_task.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(
                asyncio.gather(stdin_task, stderr_task, return_exceptions=True),
                timeout=5,
            )

    # stdout EOF is NOT process exit (Codex round 2, P1): a child can close fd 1
    # and keep running. Give it a bounded grace to exit on its own, then end it,
    # so the caller never gets returncode=None with a live orphan behind it.
    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.wait(), timeout=5)
    if proc.returncode is None:
        logger.warning("codex exec closed stdout but did not exit; terminating")
        _terminate(proc)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=5)
    return b"".join(out_chunks), b"".join(err_chunks)


class CodexProvider(BaseProvider):
    """Calls GPT via the ``codex exec`` CLI binary."""

    name = "codex"
    family = "openai"

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("codex") is not None

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        full_input = f"{system}\n\n{prompt}" if system else prompt

        base_cmd, use_shell = _resolve_codex_cmd()
        model = _codex_model()
        sandbox_status = get_sandbox_status()
        sandbox_args = ["--full-auto"] if sandbox_status.get("bwrap_available") else [
            "--dangerously-bypass-approvals-and-sandbox"
        ]
        # Prompt-node calls use Codex as a subscription-backed text model, but
        # loop-investigation coding prompts still need repo source/tests mounted.
        # Prefer Codex's sandboxed auto mode when bwrap is actually usable;
        # bwrap-less hosts fall back to the hosted subscription mode already
        # used by auto-fix, with API keys stripped.
        # Per-node effort (real Codex setting, not a prompt hint): when the
        # branch node declares config.reasoning_effort, override Codex's
        # model_reasoning_effort so a light node (e.g. localize) runs minimal/
        # low and finishes fast+cheap instead of deep-reasoning a trivial task.
        effort_args = _reasoning_effort_args(
            getattr(config, "reasoning_effort", "")
        )
        proc_env = subprocess_env_for_provider(
            self.name,
            universe_dir=universe_dir,
            credential_snapshot_dir=config.credential_snapshot_dir,
        )
        machine_accounting = bool(config.sandbox_workspace)
        if config.sandbox_workspace:
            if universe_dir is None or use_shell or not sandbox_status.get("bwrap_available"):
                raise ProviderError(
                    "codex served turns require the OS sandbox; refusing unconfined launch"
                )
            bwrap_path = str(sandbox_status.get("bwrap_path") or shutil.which("bwrap") or "")
            codex_home = Path(proc_env.get("CODEX_HOME", "")).resolve(strict=False)
            universe_root = universe_dir.resolve(strict=False)
            try:
                codex_home.relative_to(universe_root)
            except ValueError as exc:
                raise ProviderError("codex auth home is outside the served universe") from exc
            if not bwrap_path or not codex_home.is_dir():
                raise ProviderError(
                    "codex served turns require an available OS sandbox and universe auth"
                )
            binary_mounts = _codex_sandbox_mounts(base_cmd)
            sandbox_args = [
                "--full-auto",
                "--ignore-user-config",
                "--ignore-rules",
                "--disable",
                "shell_tool",
                "--disable",
                "unified_exec",
                # MCP surface for the served turn (see _codex_engine_mcp_args):
                # forces `/workspace` untrusted so no project `.codex/config.toml`
                # loads, then — when the founder-scoped engine MCP is on + its
                # per-universe HTTP server is running — wires codex to that ONE
                # trusted server (commons + own-universe handles, restricted to
                # enabled_tools, bearer via env), else no server (WebFetch-only).
                # With `--ignore-user-config` + untrusted workspace, that server is
                # the turn's only mcp_servers source. Account ChatGPT connectors
                # are removed separately by `--disable apps` below.
                *_codex_engine_mcp_args(config, proc_env),
                "-c",
                'web_search="cached"',
                "--json",
            ]
        cmd = [
            *base_cmd,
            "exec",
            "-m",
            model,
            *effort_args,
            *sandbox_args,
            # Disable the `apps` feature (codex >= 0.135 default: stable/on) on
            # EVERY codex launch — served and non-served alike. It exposes the
            # subscription account's installed ChatGPT connectors — including
            # TinyAssets' OWN /mcp connector — to the model as `codex_apps` MCP
            # tools. `--ignore-user-config` does NOT strip these: they are
            # account/cloud-side, not config.toml. Seeing its own persona prompt,
            # the served universe intelligence "relays" the turn back through the
            # tinyassets_converse/write_graph app tool, which needs a fresh
            # ChatGPT-side OAuth and returns "This app connection requires
            # reauthentication..." — a confused-deputy loop that intermittently
            # replaced the real reply (live-diagnosed 2026-08-22, raw codex --json
            # showed the codex_apps tool call). No codex turn — served text,
            # served code, or the non-served auto-fix path — is ever a legitimate
            # client of the account's connectors. codex rejects unknown feature
            # names, so this fails closed on any future version that renames it.
            # Disabling apps also removes the codex_apps MCP server upstream, so
            # `enable_mcp_apps` / `apps_mcp_path_override` cannot resurrect it.
            "--disable",
            "apps",
            "--skip-git-repo-check",
            "--ephemeral",
        ]

        win_kw = _no_window_kwargs()
        if config.sandbox_workspace:
            inner_cmd = [*cmd, "-C", "/workspace"]
            # A converse/chat turn is NOT a coding task: give codex an EMPTY
            # scratch /workspace (tmpfs) inside the same jail instead of the
            # universe, so it answers as a chat model rather than acting as a
            # code agent on the mounted files (live 2026-08-22: served converse
            # replied with persona-echo / "reauthentication" while hosted-mode
            # codex chatted + recalled memory correctly). Coding turns
            # (run_graph etc.) keep the read-only universe workspace.
            workspace_mount = (
                ["--tmpfs", "/workspace"]
                if getattr(config, "sandbox_chat", False)
                else ["--ro-bind", str(universe_root), "/workspace"]
            )
            bwrap_cmd = [
                bwrap_path,
                "--die-with-parent",
                "--new-session",
                "--unshare-all",
                "--share-net",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                *workspace_mount,
                "--tmpfs",
                "/workspace/.runtime/provider-launch-credentials",
                # CODEX_HOME is a private tmpfs with the snapshot's credential
                # FILES bound read-only into it: codex >= 0.135's launcher
                # takes `flock $CODEX_HOME/.lock` before starting, so a
                # read-only home dir died instantly ("cannot open lock file
                # /codex-home/.lock: Read-only file system", exit 73 in 56 ms
                # -> "codex exhausted", live 2026-08-22). The credential bytes
                # stay immutable; only scratch files can be created beside them.
                "--tmpfs",
                "/codex-home",
                *_codex_home_file_mounts(codex_home),
                "--setenv",
                "CODEX_HOME",
                "/codex-home",
                "--setenv",
                "HOME",
                "/tmp",
            ]
            for system_path in (
                "/usr",
                "/bin",
                "/lib",
                "/lib64",
                "/etc/ssl/certs",
                "/etc/resolv.conf",
                "/etc/hosts",
                "/etc/nsswitch.conf",
            ):
                if Path(system_path).exists() or system_path == "/usr":
                    bwrap_cmd.extend(("--ro-bind", system_path, system_path))
            for binary_mount in binary_mounts:
                if binary_mount == Path("/usr"):
                    continue
                if binary_mount.parent == Path("/opt"):
                    bwrap_cmd.extend(("--dir", "/opt"))
                bwrap_cmd.extend(
                    ("--ro-bind", str(binary_mount), str(binary_mount))
                )
            cmd_with_cwd = [*bwrap_cmd, "--", *inner_cmd]
            proc_env["CODEX_HOME"] = "/codex-home"
            proc_env["HOME"] = "/tmp"
        else:
            cmd_with_cwd = [*cmd, "-C", _codex_workdir()]
        if use_shell:
            proc = await asyncio.create_subprocess_shell(
                shlex.join(cmd_with_cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_STDOUT_READER_LIMIT,
                env=proc_env,
                **win_kw,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd_with_cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_STDOUT_READER_LIMIT,
                env=proc_env,
                **win_kw,
            )

        start = time.monotonic()

        try:
            if machine_accounting:
                # `--json` is on this path only, so ONLY this path has protocol
                # events to watch. Streamed under the idle-watchdog profile,
                # like claude: a progressing turn is never killed by a wall
                # clock, a hung one ends in ~30s. See _stream_codex_exec.
                stdout, stderr = await _stream_codex_exec(
                    proc, full_input.encode("utf-8"), config, start=start,
                )
            else:
                # Plain-text stdout, no events to reset a watchdog on: the
                # legacy total timeout stays exactly as it was. Streaming this
                # path killed every long non-served call on the 10s init
                # budget (Codex round 2, P0 - reproduced against the real CLI).
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=full_input.encode("utf-8")),
                    timeout=config.timeout,
                )
        except asyncio.TimeoutError:
            _terminate(proc)
            await proc.wait()
            raise ProviderTimeoutError(
                f"codex exec exceeded {config.timeout}s timeout"
            )
        except BaseException:
            # Every OTHER way out — cancellation, shutdown, an unexpected error in
            # communicate() — used to leave the subprocess running. Cross-family review
            # reproduced it: cancelling an in-flight call gave
            # `{'slot_live': 0, 'subprocess_killed': False}`. The admission slot was
            # returned while the ~189 MB process it was accounting for was still alive,
            # so the bound would drift further from reality with every cancellation
            # until the box ran out of memory it believed was free.
            #
            # BaseException, not Exception: `asyncio.CancelledError` derives from
            # BaseException, and cancellation is the case that actually happens.
            _terminate(proc)
            with contextlib.suppress(Exception):
                await proc.wait()
            raise

        elapsed_ms = (time.monotonic() - start) * 1000

        stderr_text = stderr.decode("utf-8", errors="replace")
        # Sandbox failures are classified FIRST: they are a host defect, not a
        # provider outage, and must surface as such instead of being folded
        # into a "likely unavailable" cooldown (how the 2026-08-21 outage hid).
        check_bwrap_failure(stderr_text)
        # Quick exit-code-1 => provider unavailable (same heuristic as claude).
        # Carry a REDACTED excerpt of codex's own words so the real cause is
        # visible; never raw stderr (it can carry token material).
        if proc.returncode == 1 and elapsed_ms < 5000:
            raise ProviderUnavailableError(
                "codex exec returned exit code 1 quickly -- likely unavailable: "
                + _redacted_stderr_excerpt(stderr_text)
            )


        if proc.returncode != 0:
            raise ProviderError(
                f"codex exec exit {proc.returncode}: {stderr_text}"
            )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        input_tokens = None
        output_tokens = None
        cost_microunits = None
        if machine_accounting:
            messages: list[str] = []
            usage: dict[str, object] | None = None
            try:
                events = [json.loads(line) for line in stdout_text.splitlines() if line.strip()]
            except (json.JSONDecodeError, TypeError) as exc:
                raise ProviderError("codex returned invalid accounting output") from exc
            for event in events:
                if not isinstance(event, dict):
                    raise ProviderError("codex returned invalid accounting output")
                item = event.get("item")
                if (
                    event.get("type") == "item.completed"
                    and isinstance(item, dict)
                    and item.get("type") == "agent_message"
                    and isinstance(item.get("text"), str)
                ):
                    messages.append(item["text"])
                if event.get("type") == "turn.completed" and isinstance(
                    event.get("usage"), dict
                ):
                    usage = event["usage"]
            if not messages or usage is None:
                raise ProviderError("codex accounting output omitted result or usage")
            try:
                input_tokens = int(usage["input_tokens"])
                output_tokens = int(usage["output_tokens"]) + int(
                    usage.get("reasoning_output_tokens", 0)
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError("codex accounting output contained invalid usage") from exc
            if input_tokens < 0 or output_tokens < 0:
                raise ProviderError("codex accounting output contained invalid usage")
            cost_microunits = (input_tokens + output_tokens) * 100
            text = messages[-1].strip()
        else:
            text = stdout_text

        if not text:
            # codex v0.122+ exits 0 on auth failure (401) but emits nothing to
            # stdout. Detect the silent-auth-failure pattern and surface it as a
            # hard error rather than returning an empty response that cascades
            # silently through downstream nodes.
            _auth_patterns = ("401", "Unauthorized", "Reconnecting", "auth")
            stderr_lower = stderr_text.lower()
            if any(p.lower() in stderr_lower for p in _auth_patterns):
                excerpt = stderr_text[:300].strip()
                raise ProviderError(
                    f"codex returned empty stdout with auth-error signal in stderr "
                    f"(exit={proc.returncode}): {excerpt}"
                )
            raise ProviderError(
                f"codex returned empty response (exit={proc.returncode}); "
                f"stderr: {stderr_text[:200].strip() or '(empty)'}"
            )

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=model,
            family=self.family,
            latency_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microunits=cost_microunits,
        )
