"""Claude provider -- ``claude -p`` subprocess.

Covered by the Claude Max subscription.  No API credits consumed.

``complete`` (the served interactive writer path) STREAMS the CLI with
``--output-format stream-json --verbose --include-partial-messages``: it reads
stdout NDJSON line-by-line, drains stderr concurrently, and judges liveness by
an idle watchdog that resets only on a real protocol event — never on a single
total wall-clock deadline. A progressing turn is never failed for elapsed time;
a genuinely idle turn is ended in ~30s (``provider_idle_timeout``) instead of
300s, and reaching the absolute cap is an ``interactive_deadline`` — neither
cools the provider. Exit code 1 within 5 seconds still signals API
unavailability (sticky cooldown). ``complete_json`` remains a blocking
non-streaming call for structured output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
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
    ProviderOverloadedError,
    ProviderProtocolError,
    ProviderRateLimitedError,
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

logger = logging.getLogger(__name__)

# Windows-specific crash codes: treat as unavailable so the router applies a
# cooldown instead of retrying immediately.
#   0xC0000374 (3221225588) = heap corruption
#   0xC0000005 (3221225477) = access violation
#   0xC000013A (3221225786) = control-C / abnormal termination
_WINDOWS_CRASH_CODES = frozenset({3221225588, 3221225477, 3221225786})

# Generous stdout reader buffer so a large single JSON `result` line does not
# trip the default 64 KiB StreamReader limit (which would read as a broken
# stream). Chat replies are far under this; an over-limit line is a real
# protocol fault.
_STDOUT_READER_LIMIT = 2 ** 22  # 4 MiB

# Margin added to a provider-stated retry_delay when extending the idle budget
# to cover a documented retry wait (blocker B): the CLI needs a little slack
# beyond its own stated wait to re-issue the request and resume streaming.
_RETRY_GRACE_MARGIN_S = 5.0


def _coerce_int(value: object) -> int | None:
    """Return *value* as an int, or ``None`` for non-integers (mock-safe)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _content_blocks(message: object) -> list[dict]:
    """Normalize an Anthropic message ``content`` to a list of block dicts."""
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _finite_nonneg(value: object) -> float | None:
    """Return ``value`` as a non-negative float, else ``None`` (bool-safe)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
        return float(value)
    return None


def _extract_api_retry(obj: dict) -> dict:
    """Classify a ``system/api_retry`` event -> {failure_class, retry_after}.

    REAL Claude 2.1.236 schema (Codex-documented, not invented): the CLI emits
    ``error`` (a string, e.g. ``"rate_limit"`` / ``"overloaded"``),
    ``error_status`` (an int HTTP status, e.g. ``429`` / ``529``), and
    ``retry_delay_ms`` (an int). Only rate-limit / overload map to a cooling
    failure class; anything else is a pure liveness signal (the CLI is retrying)
    and only surfaces if the stream never recovers.
    """
    raw = ""
    err = obj.get("error")
    if isinstance(err, str):
        raw = err
    elif isinstance(err, dict) and isinstance(err.get("type"), str):
        # Tolerate a nested ``{type: ...}`` shape defensively; the documented
        # 2.1.236 field is the bare string above.
        raw = err["type"]
    low = raw.lower()
    status = _coerce_int(obj.get("error_status"))
    failure_class: str | None = None
    if "overload" in low or status == 529:
        failure_class = "provider_overloaded"
    elif "rate" in low or status == 429:
        failure_class = "provider_rate_limited"
    ms = _finite_nonneg(obj.get("retry_delay_ms"))
    retry_after = ms / 1000.0 if ms is not None else None
    return {"failure_class": failure_class, "retry_after": retry_after}


def _extract_rate_limit_event(obj: dict, *, now: float | None = None) -> dict:
    """Classify a top-level ``rate_limit_event`` -> {failure_class, retry_after}.

    REAL Claude 2.1.236 schema: ``rate_limit_info.{status, resetsAt,
    rateLimitType, overageStatus}``. ``status == "allowed"`` is INFORMATIONAL —
    the reference trace shows it emitted on a SUCCESSFUL turn — so it is never a
    failure (the caller treats it as a liveness heartbeat). Any other status is
    an active limit; ``retry_after`` is derived from ``resetsAt`` (unix seconds).
    """
    info = obj.get("rate_limit_info")
    if not isinstance(info, dict):
        return {"failure_class": None, "retry_after": None}
    status = str(info.get("status") or "").strip().lower()
    if status in ("", "allowed"):
        return {"failure_class": None, "retry_after": None}
    retry_after: float | None = None
    resets_at = _finite_nonneg(info.get("resetsAt"))
    if resets_at is not None:
        current = time.time() if now is None else now
        delta = resets_at - current
        if delta > 0:
            retry_after = delta
    return {"failure_class": "provider_rate_limited", "retry_after": retry_after}


def _normalize_stream_obj(obj: dict) -> list[tuple[str, dict]]:
    """Collapse one stream-json object to normalized (kind, payload) events.

    RELAY only assistant text (``text_delta``) and the terminal ``result``.
    Every OTHER recognized protocol event — reasoning/thinking, hooks, status,
    notification, structural stream framing, ``tool_progress``,
    ``system/tool_heartbeat``, an informational ``rate_limit_event`` — is a
    ``heartbeat``: it proves the CLI is alive and working (verified against a
    real 2.1.236 trace where a reasoning stretch emits ONLY thinking + framing),
    so it resets the idle watchdog, but its content is NEVER relayed. Only
    whitespace / unparseable-suppressed / unknown-but-well-formed types return
    nothing.
    """
    events: list[tuple[str, dict]] = []
    kind = obj.get("type")
    if kind == "system":
        subtype = obj.get("subtype")
        if subtype == "init":
            events.append(("init", {}))
        elif subtype == "api_retry":
            events.append(("api_retry", _extract_api_retry(obj)))
        else:
            # thinking_tokens / status / notification / hook_started /
            # hook_response / tool_heartbeat / ... — recognized activity.
            events.append(("heartbeat", {}))
    elif kind == "assistant":
        for block in _content_blocks(obj.get("message")):
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text") or ""
                if text:
                    events.append(("text_delta", {"text": text}))
                else:
                    events.append(("heartbeat", {}))
            elif block_type == "tool_use":
                events.append(("tool_use", {"name": block.get("name")}))
            else:
                # thinking / redacted_thinking / signature — liveness, never
                # relayed.
                events.append(("heartbeat", {}))
    elif kind == "user":
        for block in _content_blocks(obj.get("message")):
            if block.get("type") == "tool_result":
                events.append(("tool_result", {}))
            else:
                events.append(("heartbeat", {}))
    elif kind == "stream_event":
        event = obj.get("event")
        if isinstance(event, dict):
            event_type = event.get("type")
            if event_type == "content_block_delta":
                delta = event.get("delta")
                if (
                    isinstance(delta, dict)
                    and delta.get("type") == "text_delta"
                    and (delta.get("text") or "")
                ):
                    events.append(
                        ("text_delta", {"text": delta["text"], "partial": True})
                    )
                else:
                    # thinking_delta / signature_delta / input_json_delta /
                    # empty text_delta -> liveness, never relayed.
                    events.append(("heartbeat", {}))
            elif event_type == "content_block_start":
                cb = event.get("content_block")
                if isinstance(cb, dict) and cb.get("type") == "tool_use":
                    events.append(("tool_use", {"name": cb.get("name")}))
                else:
                    events.append(("heartbeat", {}))
            else:
                # message_start/_delta/_stop, content_block_stop, ping -> liveness
                events.append(("heartbeat", {}))
    elif kind == "result":
        events.append(("result", {"obj": obj}))
    elif kind == "rate_limit_event":
        classified = _extract_rate_limit_event(obj)
        if classified["failure_class"]:
            events.append(("api_retry", classified))
        else:
            # status == "allowed": informational (seen even on success).
            events.append(("heartbeat", {}))
    elif kind == "tool_progress":
        events.append(("heartbeat", {}))
    # unknown well-formed type -> ignored (tolerant; not a protocol error and
    # not counted as liveness — a truly hung process emits nothing at all).
    return events


def _result_is_success(obj: dict) -> bool:
    """Whether a terminal ``result`` event represents a successful turn."""
    if bool(obj.get("is_error")):
        return False
    subtype = str(obj.get("subtype") or "").lower()
    return subtype in ("", "success")


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
    turn_id = (config.engine_mcp_turn_id or "").strip()
    if not (actor_id and graph_id):
        return []
    import json as _json
    import os as _os
    import sys as _sys
    from pathlib import Path as _Path

    # Config lives in the sandboxed universe_dir (the engine has no filesystem
    # read tool, so it never sees it). It carries only identifiers — the founder
    # actor_id + graph_id + data root — never a secret. Overwritten each turn.
    config_path = universe_dir / ".engine_mcp_config.json"
    server_env = {
        "TINYASSETS_ENGINE_ACTOR_ID": actor_id,
        "TINYASSETS_ENGINE_GRAPH_ID": graph_id,
    }
    # The turn this engine surface serves (2026-08-29). It rides the SAME
    # channel as the identity: env for the stdio child, and the bearer for the
    # HTTP server below -- both daemon-controlled and invisible to the LLM. A
    # write_brain proposal is stamped with it, so the founder-only writer
    # consumes only the proposal its own turn produced. Absent -> no proposal.
    if turn_id:
        server_env["TINYASSETS_ENGINE_TURN_ID"] = turn_id
    data_dir = _os.environ.get("TINYASSETS_DATA_DIR", "").strip()
    if data_dir:
        server_env["TINYASSETS_DATA_DIR"] = data_dir
    # Transport selection. The claude CLI's STDIO MCP spawn is flaky in the
    # headless served subprocess (verified live 2026-08-19: the server process
    # never launched, CLI reported "still connecting"); HTTP MCP connects
    # reliably. So when a persistent per-universe HTTP engine server is running,
    # point --mcp-config at its loopback URL + inject the per-server bearer
    # secret (Codex gate #6). Falls back to stdio when none is running. The route
    # map ``{graph_id: {"url": ..., "secret": ...}}`` is written 0600 by
    # engine_mcp_http; the secret goes in the --mcp-config HEADERS (which the CLI
    # holds internally — never surfaced to the LLM), not the prompt.
    http_url = ""
    http_secret = ""
    try:
        _routes_path = _Path(data_dir or ".") / ".engine_mcp_http_routes.json"
        if _routes_path.is_file():
            _routes = _json.loads(_routes_path.read_text(encoding="utf-8"))
            if isinstance(_routes, dict):
                _entry = _routes.get(graph_id)
                if isinstance(_entry, dict):
                    http_url = str(_entry.get("url") or "").strip()
                    http_secret = str(_entry.get("secret") or "").strip()
    except Exception:  # noqa: BLE001 - never break a turn on a bad route file
        http_url = ""
        http_secret = ""
    if http_url and http_secret:
        # The HTTP engine server is LONG-LIVED and shared across turns, so the
        # turn id cannot come from its startup env: it rides the per-request
        # bearer as ``<secret>.<turn_id>`` (the secret is url-safe base64 and a
        # turn id is ``turn_<ULID>``, so neither half contains a dot).
        # ``engine_mcp_server._parse_bearer`` authenticates the secret half in
        # constant time and binds the turn half for that request only. Same
        # channel as the auth, per Codex round-1: not a universe-global file.
        bearer = http_secret + ("." + turn_id if turn_id else "")
        mcp_config = {
            "mcpServers": {
                "tinyassets": {
                    "type": "http",
                    "url": http_url,
                    "headers": {"Authorization": "Bearer " + bearer},
                }
            }
        }
    else:
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
        """Stream a served interactive turn, judged by an idle watchdog.

        Returns a terminal :class:`ProviderResponse` on success. Raises a
        classified provider exception on failure (``ProviderIdleTimeoutError`` /
        ``InteractiveDeadlineError`` / ``ProviderRateLimitedError`` /
        ``ProviderOverloadedError`` / ``ProviderProtocolError`` /
        ``ProviderUnavailableError`` / ``ProviderError``).
        """
        base_cmd, use_shell = _resolve_claude_cmd()
        cmd = [
            *base_cmd, "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if system:
            cmd.extend(["--system-prompt", system])
        extra_flags, run_cwd = _sandbox_cli_args(config, universe_dir)
        cmd.extend(extra_flags)
        proc_env = subprocess_env_for_provider(
            self.name,
            universe_dir=universe_dir,
            credential_snapshot_dir=config.credential_snapshot_dir,
        )
        win_kw = _no_window_kwargs()
        if use_shell:
            proc = await asyncio.create_subprocess_shell(
                shlex.join(cmd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
                cwd=run_cwd,
                limit=_STDOUT_READER_LIMIT,
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
                limit=_STDOUT_READER_LIMIT,
                **win_kw,
            )
        return await self._read_stream(proc, prompt, config)

    @staticmethod
    async def _terminate(proc) -> None:
        """Kill and reap a subprocess, tolerating an already-dead process."""
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 - already exited / mock
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except Exception:  # noqa: BLE001 - reap best-effort
            pass

    @staticmethod
    def _parse_line(raw: bytes) -> tuple[list[tuple[str, dict]], bool]:
        """Parse one stdout line -> (normalized events, malformed?).

        Whitespace-only lines are ignored (no events, not malformed). A
        non-whitespace line that is not a JSON object is malformed (fail loud).
        """
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ([], True)
        stripped = text.strip()
        if not stripped:
            return ([], False)
        try:
            obj = json.loads(stripped)
        except (ValueError, TypeError):
            return ([], True)
        if not isinstance(obj, dict):
            return ([], True)
        return (_normalize_stream_obj(obj), False)

    async def _read_stream(
        self, proc, prompt: str, config: ModelConfig,
    ) -> ProviderResponse:
        profile = config.stream_timeout_profile()
        start = time.monotonic()
        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            try:
                while True:
                    chunk = await proc.stderr.read(4096)
                    if not isinstance(chunk, (bytes, bytearray)) or not chunk:
                        break
                    stderr_chunks.append(bytes(chunk))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - stderr drain must never break a turn
                return

        async def _feed_stdin() -> None:
            try:
                if proc.stdin is not None:
                    proc.stdin.write(prompt.encode("utf-8"))
                    await proc.stdin.drain()
                    proc.stdin.close()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a closed stdin must not break a turn
                return

        stderr_task = asyncio.create_task(_drain_stderr())
        stdin_task = asyncio.create_task(_feed_stdin())

        async def _finish_stderr() -> str:
            try:
                await asyncio.wait_for(asyncio.shield(stderr_task), timeout=2)
            except Exception:  # noqa: BLE001 - best-effort collect
                pass
            return b"".join(stderr_chunks).decode(errors="replace")

        # Mutable attempt telemetry (blocker K). Declared BEFORE the closures so
        # both ``_raise_timeout`` and every classified raise can attach a
        # snapshot to the exception. Only writes need ``nonlocal``; the closures
        # below read these by late binding.
        assembled: list[str] = []
        partial: list[str] = []
        terminal: dict | None = None
        last_retry: dict | None = None
        seen_init = False
        seen_progress = False
        ttft_ms: float | None = None
        tool_phase: str | None = None
        side_effect_state = "none"
        last_progress = start
        soft_slo_logged = False
        # A documented retry event carries a provider-stated wait; while it is in
        # flight the idle budget is extended to cover it so a real retry wait is
        # NOT relabeled a hang (blocker B). Cleared on the next real progress.
        pending_retry_delay: float | None = None

        def _attach(exc: ProviderError) -> ProviderError:
            """Attach the current attempt-telemetry snapshot to a raised error."""
            exc.attempt_telemetry = {
                "provider": self.name,
                "failure_class": getattr(exc, "failure_class", None),
                "phase": (
                    "streaming" if seen_progress
                    else "init" if seen_init else "launch"
                ),
                "side_effect_state": side_effect_state,
                "tool_phase": tool_phase,
                "ttft_ms": ttft_ms,
                "last_progress_age_ms": (time.monotonic() - last_progress) * 1000,
                "exit_code": _coerce_int(proc.returncode),
                "terminal": terminal is not None,
            }
            return exc

        async def _raise_timeout(bound_is_absolute: bool, allow: float) -> None:
            await self._terminate(proc)
            check_bwrap_failure(await _finish_stderr())
            if bound_is_absolute:
                raise _attach(InteractiveDeadlineError(
                    f"claude -p exceeded the {profile.absolute_cap_s:.0f}s "
                    "absolute interactive cap while still streaming"
                ))
            raise _attach(ProviderIdleTimeoutError(
                f"claude -p produced no protocol event for {allow:.0f}s "
                "(idle watchdog fired; no provider cooldown)"
            ))

        try:
            while True:
                now = time.monotonic()
                if not seen_init:
                    allow = profile.init_s
                elif not seen_progress:
                    allow = profile.first_progress_s
                else:
                    allow = profile.idle_s
                # A known provider retry wait extends the idle budget (blocker B):
                # a 60s documented retry_delay must not be relabeled idle at 30s.
                # The absolute cap still bounds the total turn.
                if pending_retry_delay is not None:
                    allow = max(allow, pending_retry_delay + _RETRY_GRACE_MARGIN_S)
                idle_deadline = last_progress + allow
                abs_deadline = start + profile.absolute_cap_s
                budget = min(idle_deadline, abs_deadline) - now
                bound_is_absolute = abs_deadline <= idle_deadline
                if budget <= 0:
                    await _raise_timeout(bound_is_absolute, allow)
                if not soft_slo_logged and now - start >= profile.soft_slo_s:
                    soft_slo_logged = True
                    logger.info(
                        "served claude turn exceeded soft SLO %.0fs; still "
                        "progressing", profile.soft_slo_s,
                    )
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=budget,
                    )
                except asyncio.TimeoutError:
                    await _raise_timeout(bound_is_absolute, allow)
                except (ValueError, asyncio.LimitOverrunError):
                    await self._terminate(proc)
                    await _finish_stderr()
                    raise _attach(ProviderProtocolError(
                        "claude -p stream line exceeded the reader buffer limit"
                    ))
                if not line:
                    break  # EOF
                events, malformed = self._parse_line(line)
                if malformed:
                    await self._terminate(proc)
                    check_bwrap_failure(await _finish_stderr())
                    raise _attach(ProviderProtocolError(
                        "claude -p emitted a malformed (non-JSON) stream line"
                    ))
                progressed = False
                for kind, payload in events:
                    progressed = True
                    if kind == "init":
                        seen_init = True
                    elif kind == "heartbeat":
                        # A recognized protocol event (thinking / hooks / status /
                        # stream framing / tool_progress / informational
                        # rate_limit_event): liveness only. Reset the watchdog
                        # (progressed=True above), never relay, never change phase.
                        pass
                    elif kind == "text_delta":
                        seen_init = True
                        seen_progress = True
                        pending_retry_delay = None
                        if ttft_ms is None:
                            ttft_ms = (time.monotonic() - start) * 1000
                        if payload.get("partial"):
                            partial.append(payload.get("text") or "")
                        else:
                            assembled.append(payload.get("text") or "")
                    elif kind == "tool_use":
                        seen_init = True
                        seen_progress = True
                        pending_retry_delay = None
                        tool_phase = "tool_use"
                        if side_effect_state == "none":
                            side_effect_state = "possible"
                    elif kind == "tool_result":
                        seen_init = True
                        seen_progress = True
                        pending_retry_delay = None
                        tool_phase = "tool_result"
                        side_effect_state = "committed"
                    elif kind == "api_retry":
                        seen_init = True
                        # A documented retry is liveness AND arms the retry-wait
                        # grace so the idle watchdog covers the provider's stated
                        # wait (blocker B). NOT seen_progress: a retry is not the
                        # first useful output.
                        retry_after = payload.get("retry_after")
                        if isinstance(retry_after, (int, float)) and retry_after > 0:
                            pending_retry_delay = float(retry_after)
                        if payload.get("failure_class"):
                            last_retry = payload
                    elif kind == "result":
                        terminal = payload.get("obj")
                if progressed:
                    last_progress = time.monotonic()
                if terminal is not None:
                    break

            # Normal loop exit (terminal result or EOF). Reap + collect stderr.
            await self._terminate(proc)
            returncode = proc.returncode
            stderr_text = await _finish_stderr()
            check_bwrap_failure(stderr_text)
            elapsed_ms = (time.monotonic() - start) * 1000

            if terminal is not None and _result_is_success(terminal):
                final_text = str(terminal.get("result") or "").strip()
                if not final_text:
                    final_text = (
                        "".join(assembled).strip() or "".join(partial).strip()
                    )
                if not final_text:
                    raise _attach(ProviderError(
                        "claude -p returned a success result with no assistant text"
                    ))
                usage = terminal.get("usage")
                usage = usage if isinstance(usage, dict) else {}
                cost = terminal.get("total_cost_usd")
                cost_micro = (
                    round(float(cost) * 1_000_000)
                    if isinstance(cost, (int, float)) and math.isfinite(cost)
                    else None
                )
                return ProviderResponse(
                    text=final_text,
                    provider=self.name,
                    model="claude",
                    family=self.family,
                    latency_ms=elapsed_ms,
                    input_tokens=_coerce_int(usage.get("input_tokens")),
                    output_tokens=_coerce_int(usage.get("output_tokens")),
                    cost_microunits=cost_micro,
                    ttft_ms=ttft_ms,
                    last_progress_age_ms=(time.monotonic() - last_progress) * 1000,
                    tool_phase=tool_phase,
                    exit_code=_coerce_int(returncode),
                    side_effect_state=side_effect_state,
                )

            # Not a successful terminal result — classify the failure.
            # A TYPED provider retry signal (real system/api_retry / rate_limit_event)
            # is authoritative and MUST be checked BEFORE the exit-code heuristics
            # (Codex re-review #2 blocker A): a genuine 429/529 followed by a quick
            # exit 1 was otherwise mislabeled as generic "unavailable" with no
            # retry_after, losing the honest rate-limit classification + cooldown.
            if last_retry is not None and last_retry.get("failure_class"):
                retry_after = last_retry.get("retry_after")
                if last_retry["failure_class"] == "provider_overloaded":
                    raise _attach(ProviderOverloadedError(
                        "claude -p reported provider overload and did not recover",
                        retry_after=retry_after,
                    ))
                raise _attach(ProviderRateLimitedError(
                    "claude -p reported a provider rate limit and did not recover",
                    retry_after=retry_after,
                ))
            if returncode == 1 and elapsed_ms < 5000:
                raise _attach(ProviderUnavailableError(
                    "claude -p returned exit code 1 quickly -- API likely unavailable"
                ))
            if returncode in _WINDOWS_CRASH_CODES:
                raise _attach(ProviderUnavailableError(
                    f"claude -p crashed with Windows exit code {returncode:#x} "
                    "— subprocess failure, applying cooldown"
                ))
            if terminal is not None:
                raise _attach(ProviderError(
                    f"claude -p terminal result was not success "
                    f"(subtype={terminal.get('subtype')!r})"
                ))
            if returncode not in (0, None):
                raise _attach(ProviderError(
                    f"claude -p exit {returncode}: {stderr_text[:400]}"
                ))
            # EOF with a clean/absent exit but NO terminal result: the stream was
            # truncated (blocker J). Classify it as a protocol error rather than a
            # bare, unclassified ProviderError.
            raise _attach(ProviderProtocolError(
                "claude -p stream ended without a terminal result event "
                "(truncated stream)"
            ))
        finally:
            # Every exit path — normal EOF, a classified raise, an unexpected
            # reader exception, or CALLER CANCELLATION — must kill the subprocess
            # and reap BOTH helper tasks so neither the process nor the
            # stdin/stderr drains leak (blocker E: the Codex probe caught
            # ``killed_after_caller_cancel: False``). ``proc.kill()`` is
            # synchronous, so the process is signalled even if a subsequent await
            # is itself cancelled; the in-band ``_terminate`` above is idempotent
            # with this.
            try:
                proc.kill()
            except Exception:  # noqa: BLE001 - already exited / mock
                pass
            stdin_task.cancel()
            stderr_task.cancel()
            # BOUND the reap (Codex re-review #2 blocker E): a kill-resistant or
            # wedged ``proc.wait()`` must not hang the finally — and thus a caller
            # cancellation — forever. The process was already signalled by
            # ``proc.kill()`` above, so on a reap timeout we accept a best-effort
            # detach rather than blocking indefinitely.
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        proc.wait(), stdin_task, stderr_task,
                        return_exceptions=True,
                    ),
                    timeout=5,
                )
            except Exception:  # noqa: BLE001 - best-effort reap (CancelledError still propagates)
                pass

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
        proc_env = subprocess_env_for_provider(
            self.name,
            universe_dir=universe_dir,
            credential_snapshot_dir=config.credential_snapshot_dir,
        )
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
