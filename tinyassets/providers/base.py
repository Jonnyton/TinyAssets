"""Base types for the provider layer.

Every provider implements :class:`BaseProvider`.  The router and all
consumers work with :class:`ProviderResponse` and :class:`ModelConfig`.
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tinyassets.config import UniverseConfig


@dataclass(frozen=True, slots=True)
class UniverseContext:
    """Explicit per-universe routing context threaded through provider calls.

    Carries the universe directory (for credential-vault auth resolution) and
    the resolved :class:`~tinyassets.config.UniverseConfig` (for provider
    preference / allowlist), so the router and vault resolve per-universe config
    from an EXPLICIT argument instead of the process-global
    ``runtime.universe_config`` / ``TINYASSETS_UNIVERSE``. This is the
    multi-universe seam: a single daemon process can serve interleaved calls for
    different universes without a global bleeding across them. ``None`` fields
    preserve today's single-universe-daemon behavior (fall back to the globals).
    """

    universe_dir: Path | None = None
    config: "UniverseConfig | None" = None


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Configuration passed to every provider call."""

    timeout: int = 300
    """Subprocess / HTTP timeout in seconds."""

    max_tokens: int | None = None
    """Optional token cap (provider-specific interpretation)."""

    temperature: float = 0.7

    reasoning_effort: str = ""
    """Generic per-call reasoning/effort level (e.g. ``minimal`` / ``low`` /
    ``medium`` / ``high``). Empty = provider default. Each provider maps this to
    its own real setting — e.g. Codex ``-c model_reasoning_effort=<v>`` — so a
    branch can run a light node (localize) cheap+fast and a hard node
    (propose_changes) deep. Not a prompt hint; a real subprocess setting."""

    sandbox_workspace: bool = False
    """Run the CLI subprocess isolated to the universe's OWN dir instead of the
    host's cwd. When True, subprocess providers set ``cwd=universe_dir`` so the
    call does NOT inherit the daemon's working directory (which may be a source
    checkout, exposing repo files / ``CLAUDE.md`` / other universes). Set for the
    founder-facing universe-intelligence turn; leave False for host-trusted engine
    roles. The isolation is only as strong as the tool policy below — pair it with
    ``disallowed_tools`` to deny shell escape (a Bash tool can ``cd`` out).

    This is the *conversation* sandbox profile (WebFetch-only, no filesystem
    tools): safe WITHOUT an OS sandbox because the tool denylist removes every
    filesystem/shell tool. Coding nodes that must actually READ/WRITE a repo use
    ``os_sandbox_required`` instead — they keep the coding tools, so their
    confinement depends on an OS-level sandbox, not the tool denylist."""

    os_sandbox_required: bool = False
    """Require an OS-level sandbox (bwrap / container) to confine this call, and
    FAIL CLOSED if none is available. Set for coding nodes (``requires_sandbox``
    on the NodeDefinition, e.g. the patch loop's ``draft_patch``) that run a
    coding agent with real filesystem/shell tools against a checked-out repo.

    Unlike ``sandbox_workspace`` (which is safe unsandboxed because it denies all
    filesystem tools), a coding node KEEPS Read/Write/Edit/Bash so it can produce
    a patch — and the claude CLI cannot confine those tools to a directory
    (Read/Glob/Grep are default-allowed, and a bare deny is all-or-nothing). The
    only real confinement for a repo-touching coding turn is therefore an OS
    sandbox around the whole subprocess. When True, subprocess providers MUST:
    (1) refuse to run when no OS sandbox is available (raise
    :class:`SandboxUnavailableError` — never run unconfined), and (2) never use
    any bypass-sandbox escape hatch (codex ``--dangerously-bypass-approvals-and-
    sandbox``). Host-trusted roles leave this False (default) and are unaffected."""

    closed_tool_surface: bool = False
    """Disable ALL built-in tools for this call (maps to ``claude -p --tools ""``,
    per Anthropic's CLI docs). Set for text-generation nodes: a plain prompt node
    produces text and needs NO tools, so the honest closed surface is "no tools at
    all" (plus a strict empty MCP config) rather than a rotting per-name denylist.
    This is how a non-coding node is kept incapable of repo write — coding tools
    are reachable only through the coding classifier."""

    allowed_tools: tuple[str, ...] | None = None
    """Allowlist of CLI tool names the subprocess may use (e.g.
    ``("WebFetch", "Read")``). ``None`` = provider default (no restriction). Maps
    to ``claude -p --allowedTools``. Default-deny: when set, only these are
    usable."""

    disallowed_tools: tuple[str, ...] | None = None
    """Denylist of CLI tool names the subprocess must NOT use (e.g.
    ``("Bash", "WebSearch")``). ``None`` = no explicit denies. Maps to ``claude -p
    --disallowedTools`` and takes precedence over ``allowed_tools`` — the hard
    floor that closes shell-escape / host-access even if a settings file would
    grant them."""


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

HOST_AUTH_ENV_VARS: tuple[str, ...] = (
    *API_KEY_PROVIDER_ENV_VARS,
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "TINYASSETS_CODEX_AUTH_JSON_B64",
    "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64",
)


def _truthy_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def api_key_providers_enabled() -> bool:
    """Return True only when a host explicitly opts into API-key providers."""
    return _truthy_env(os.environ.get("TINYASSETS_ALLOW_API_KEY_PROVIDERS"))


def require_api_key_provider_opt_in(provider_name: str) -> None:
    """Fail API-key-backed providers unless the host deliberately enables them."""
    if api_key_providers_enabled():
        return
    from tinyassets.exceptions import ProviderUnavailableError

    raise ProviderUnavailableError(
        f"{provider_name} is API-key-backed and disabled by default. "
        "TinyAssets daemons are subscription-only unless the host deliberately "
        "sets TINYASSETS_ALLOW_API_KEY_PROVIDERS=1 for this daemon."
    )


def subprocess_env_without_api_keys() -> dict[str, str] | None:
    """Return a subprocess env that ignores API-key auth unless opted in."""
    if api_key_providers_enabled():
        return None
    env = os.environ.copy()
    for name in API_KEY_PROVIDER_ENV_VARS:
        env.pop(name, None)
    return env


# NOTE (Codex S3 r9 #4 — dead-stack removal): the sanitized minimal-allowlist +
# per-universe vault-only env (`sanitized_subprocess_env`, `_has_provider_vault_auth`,
# the vault-auth refusal) was the ENVIRONMENT materialization for a repo-writing
# coding subprocess. Repo-touching nodes fail closed at the graph choke point
# before any provider spawn (no per-job runner), so that plumbing is unreachable
# and has been REMOVED as dead security surface — git history preserves it as the
# Phase-2 per-job runner slice's contract. Text nodes use the normal
# `subprocess_env_for_provider`; their cwd isolation is the per-job scratch below.


def new_sandbox_job_dir() -> str:
    """Create a fresh, empty per-job scratch dir for a sandbox-required spawn.

    The coding node's cwd is pinned here — NOT the daemon's source checkout
    (which exposes our platform source) and NOT ``/data`` (cross-tenant data).
    Caller removes it via :func:`cleanup_sandbox_job_dir` when the job ends.
    """
    import tempfile

    return tempfile.mkdtemp(prefix="tinyassets-sandbox-job-")


def cleanup_sandbox_job_dir(scratch_dir: str | None) -> None:
    """Best-effort removal of a per-job scratch dir (no-op for ``None``)."""
    if not scratch_dir:
        return
    import shutil

    shutil.rmtree(scratch_dir, ignore_errors=True)


def sandbox_spawn_env_and_dir(
    provider_name: str,
    config: "ModelConfig",  # noqa: ARG001 — kept for call-site stability
    *,
    universe_dir: Path | None = None,
) -> tuple[dict[str, str], str | None]:
    """Return ``(proc_env, None)`` for a provider subprocess spawn.

    Returns the normal provider env; the coding-EXECUTION env materialization
    (sanitized vault-only env + vault-auth refusal) was Phase-2 runner plumbing
    and has been removed (see the note above) — repo/coding nodes never reach a
    provider. The per-job scratch cwd for hardened text spawns is created by the
    provider itself (codex `-C`, claude cwd) via :func:`new_sandbox_job_dir`.
    """
    return (
        subprocess_env_for_provider(provider_name, universe_dir=universe_dir),
        None,
    )


def subprocess_env_for_provider(
    provider_name: str, *, universe_dir: Path | None = None,
) -> dict[str, str]:
    """Return subprocess env with API-key policy and vault auth applied.

    When *universe_dir* is given it takes precedence over the process-global
    ``TINYASSETS_UNIVERSE`` for vault-auth resolution, so a single daemon can
    resolve per-universe credentials for an explicitly threaded universe.
    Engine credentials come from the platform vault via
    :mod:`tinyassets.credential_broker`. A universe with no engine deposits
    gets no overrides (the host_daemon default engine). Fail-closed states —
    unmigrated legacy plaintext, ``needs_redeposit``/revoked bindings — RAISE:
    the universe's engine stops rather than silently running on the host's
    credentials (the ambient identity leak).
    """
    host_env = subprocess_env_without_api_keys() or os.environ.copy()
    from tinyassets.credential_broker import (
        provider_auth_env_overrides,
        resolve_universe_from_env,
    )
    from tinyassets.engine_binding import (
        RetiredCredentialStateError,
        byo_credential_digest,
        byo_execution_enabled,
        get_pinned_byo_snapshot,
        resolve_engine_binding,
    )
    from tinyassets.exceptions import ProviderUnavailableError

    resolved_universe = (
        Path(universe_dir)
        if universe_dir is not None
        else resolve_universe_from_env(host_env)
    )
    if resolved_universe is None:
        return host_env

    from tinyassets.config import load_universe_config

    engine_source = (
        load_universe_config(resolved_universe).engine_source.strip().lower()
    )
    if engine_source == "host_daemon":
        return host_env

    binding = resolve_engine_binding(resolved_universe)
    if binding.needs_migration:
        raise RetiredCredentialStateError(
            "retired credential state cannot use ambient provider auth"
        )

    provider = provider_name.strip()
    byo_bound = binding.is_eligible_for(provider)
    if engine_source == "byo_api_key":
        if not byo_execution_enabled(resolved_universe):
            raise ProviderUnavailableError(
                "BYO execution is not fully attested; refusing ambient provider auth."
            )
        if not binding.bound or not byo_bound:
            raise ProviderUnavailableError(
                f"BYO provider {provider!r} is not an eligible executable binding; "
                "refusing ambient provider auth."
            )

    snapshot = get_pinned_byo_snapshot()
    routing_binding = (
        snapshot
        if snapshot is not None
        and snapshot.enabled
        and snapshot.credential_digest is not None
        and snapshot.universe_dir == str(resolved_universe)
        else None
    )
    if routing_binding is not None:
        fresh_digest = byo_credential_digest(resolved_universe)
        if fresh_digest != routing_binding.credential_digest:
            raise ProviderUnavailableError(
                "BYO credential changed or disappeared between routing and spawn; "
                "refusing ambient provider auth."
            )

    env = os.environ.copy()
    for name in HOST_AUTH_ENV_VARS:
        env.pop(name, None)
    # A bare-host CLI must never fall back to the daemon user's default config
    # directory after ambient auth is scrubbed. Pin each supported CLI to an
    # empty/universe-owned home; OAuth materialization may populate the same path.
    if provider == "codex":
        env["CODEX_HOME"] = str(resolved_universe / ".engine-auth" / "codex")
    elif provider == "claude-code":
        env["CLAUDE_CONFIG_DIR"] = str(
            resolved_universe / ".engine-auth" / "claude"
        )
    # A retained credential is not authority to use it after the universe
    # switches to another engine lane. Only an executable, attested BYO
    # binding may materialize broker-held auth into a child process.
    overrides = (
        provider_auth_env_overrides(
            provider,
            resolved_universe,
            require_binding=True,
        )
        if byo_bound
        else {}
    )
    env.update(overrides)
    if routing_binding is not None:
        fresh_digest = byo_credential_digest(resolved_universe)
        if fresh_digest != routing_binding.credential_digest:
            raise ProviderUnavailableError(
                "BYO credential changed during spawn materialization; refusing "
                "ambient provider auth."
            )
    if byo_bound and provider == "claude-code":
        env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] = "1"
    return env


# ---------------------------------------------------------------------------
# Codex refresh-viability probe (layered on top of the presence check below).
# ---------------------------------------------------------------------------

# Signatures captured live 2026-07-14 by running `codex exec` against the
# dead token stranded on the old workflow-data volume (exit code was 0 even
# on failure, so output text — stdout+stderr — is the only reliable signal).
# Matched case-insensitively (Codex review: the CLI's casing is not a
# contract). Additionally the probe mirrors CodexProvider's silent-auth
# heuristic: EMPTY stdout + a broad auth signal in stderr is also dead —
# broad signals are only trusted when the model produced no reply, so
# model text can never false-positive.
_CODEX_AUTH_FAILURE_PATTERNS: tuple[str, ...] = (
    "your access token could not be refreshed",
    "please log out and sign in again",
    "401 unauthorized",
)
_CODEX_SILENT_AUTH_SIGNALS: tuple[str, ...] = (
    "401", "unauthorized", "reconnecting", "auth",
)

_AUTH_PROBE_PROMPT = "Reply with exactly: OK"

DEFAULT_CODEX_AUTH_FRESH_S = 24 * 3600.0
DEFAULT_AUTH_PROBE_TTL_S = 1800.0
DEFAULT_AUTH_PROBE_TIMEOUT_S = 120.0

_PROBE_FALSY = {"0", "false", "off", "no"}

# Live-probe verdict cache. The supervisor calls the gate every loop tick;
# the probe subprocess must not run per tick. The AUTHORITATIVE cache is a
# small JSON file NEXT TO auth.json (shared volume): production runs the
# daemon and workers as separate containers sharing CODEX_HOME, so an
# in-memory dict would let a worker quarantine while the daemon's
# get_status kept reporting "ok" (Codex review 2026-07-14). The in-memory
# layer below remains as a fallback for read-only CODEX_HOMEs.
PROBE_CACHE_FILENAME = ".tinyassets_auth_probe.json"

_auth_probe_cache: dict[str, tuple[float, dict[str, str]]] = {}


def _reset_auth_probe_cache() -> None:
    """Test seam (in-memory layer only; tests isolate the disk layer via
    per-test CODEX_HOME tmp dirs)."""
    _auth_probe_cache.clear()


def _read_probe_cache_file(codex_home: Path) -> tuple[float, dict[str, str]] | None:
    """Read the cross-process verdict file; any corruption reads as absent."""
    import json as _json
    import math

    try:
        data = _json.loads(
            (codex_home / PROBE_CACHE_FILENAME).read_text(encoding="utf-8"),
        )
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    checked_at = data.get("checked_at")
    status = data.get("status")
    detail = data.get("detail")
    if not isinstance(checked_at, (int, float)) or not math.isfinite(float(checked_at)):
        return None
    if status not in ("ok", "not_logged_in") or not isinstance(detail, str):
        return None
    return float(checked_at), {
        "provider": "codex", "status": status, "detail": detail,
    }


def _write_probe_cache_file(
    codex_home: Path, checked_at: float, health: dict[str, str],
) -> None:
    """Best-effort atomic write of the cross-process verdict file."""
    import json as _json

    payload = _json.dumps({
        "checked_at": checked_at,
        "status": health["status"],
        "detail": health["detail"],
    }, ensure_ascii=True)
    target = codex_home / PROBE_CACHE_FILENAME
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        pass  # read-only home: the in-memory layer still covers this process


def _viability_probe_enabled() -> bool:
    raw = os.environ.get("TINYASSETS_AUTH_VIABILITY_PROBE", "").strip().lower()
    return raw not in _PROBE_FALSY


def _finite_positive_env_s(var: str, default: float) -> float:
    """Parse a seconds env var; only finite positive values are accepted
    (same hardening class as the idle-cycle window — Codex review
    2026-07-14: ``inf``/``nan`` must not silently disable comparisons)."""
    import math

    raw = os.environ.get(var, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value) or value <= 0:
        return default
    return value


def _codex_last_refresh_age_s(codex_home: Path, now: float | None = None) -> float | None:
    """Age in seconds of the auth.json ``last_refresh`` field.

    The file-mtime fallback applies ONLY to a VALID JSON object that lacks a
    usable ``last_refresh`` (e.g. a mid-write `codex login`). An unreadable
    or corrupt auth.json returns ``None`` — suspicious, so the caller
    escalates to the live probe instead of trusting mtime (Codex review
    2026-07-14: a fresh file containing garbage must not read viable and
    claim-and-poison)."""
    import json as _json
    import math
    import time as _time
    from datetime import datetime, timezone

    auth_path = codex_home / "auth.json"
    current = _time.time() if now is None else now
    try:
        data = _json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("last_refresh")
    if isinstance(raw, str) and raw.strip():
        try:
            text = raw.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age = current - parsed.timestamp()
            if math.isfinite(age):
                return age
        except (ValueError, TypeError, OverflowError):
            # A present-but-unparseable last_refresh is suspicious, not
            # mtime-fresh.
            return None
    try:
        return current - auth_path.stat().st_mtime
    except OSError:
        return None


def _codex_live_auth_probe(timeout_s: float) -> dict[str, str]:
    """One tiny real ``codex exec`` call; the only check that catches a
    dead refresh token (``codex login status`` reads the file locally and
    reported "Logged in" for the very token that 401'd — live 2026-07-14).

    Returns ``{"status": "ok"|"not_logged_in"|"inconclusive", "detail"}``.
    Uses whatever ``codex`` is on PATH so flock-wrapper deployments keep
    their single-use refresh-token serialization.
    """
    import subprocess
    import tempfile

    from tinyassets.providers.codex_provider import _resolve_codex_cmd

    base_cmd, use_shell = _resolve_codex_cmd()
    cmd = [
        *base_cmd, "exec", "--skip-git-repo-check", "-s", "read-only",
        _AUTH_PROBE_PROMPT,
    ]
    try:
        proc = subprocess.run(
            cmd if not use_shell else subprocess.list2cmdline(cmd),
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=tempfile.gettempdir(),
        )
    except FileNotFoundError:
        return {"status": "inconclusive",
                "detail": "codex binary not on PATH; probe skipped"}
    except subprocess.TimeoutExpired:
        return {"status": "inconclusive",
                "detail": f"live auth probe timed out after {timeout_s:.0f}s"}
    except OSError as exc:
        return {"status": "inconclusive",
                "detail": f"live auth probe could not run: {exc}"}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined_lower = f"{stdout}\n{stderr}".lower()
    matched = next(
        (p for p in _CODEX_AUTH_FAILURE_PATTERNS if p in combined_lower), None,
    )
    # CodexProvider silent-auth mirror: empty stdout + a broad auth signal
    # in stderr is dead too. Broad signals are only trusted when the model
    # produced NO reply, so probe/model text can never false-positive.
    if matched is None and not stdout.strip():
        matched = next(
            (s for s in _CODEX_SILENT_AUTH_SIGNALS if s in stderr.lower()),
            None,
        )
    if matched is not None:
        return {
            "status": "not_logged_in",
            "detail": (
                f"refresh-viability probe FAILED (matched {matched!r}); "
                "token is dead despite auth.json being present — run a "
                "fresh `codex login` for this CODEX_HOME"
            ),
        }
    if proc.returncode != 0:
        return {"status": "inconclusive",
                "detail": f"live auth probe exit {proc.returncode} without an "
                          "auth-failure signature"}
    if not stdout.strip():
        return {"status": "inconclusive",
                "detail": "live auth probe returned empty output without an "
                          "auth-failure signature"}
    return {"status": "ok", "detail": "live auth probe passed (real call ok)"}


def _codex_refresh_viability(
    codex_home: Path, *, allow_probe: bool = True,
) -> dict[str, str]:
    """Layered viability verdict for a PRESENT auth.json (see the
    subscription_auth_health docs below for the full ladder).

    ``allow_probe=False`` is for latency-sensitive callers (get_status —
    an MCP request must never block on a probe subprocess): it serves the
    freshness fast path and any cached verdict, and reports stale creds as
    "ok" with a probe-deferred detail instead of probing inline. The
    execution-gate decision belongs to the external daemon, which may probe.
    """
    import time as _time

    presence_ok = {
        "provider": "codex", "status": "ok",
        "detail": f"auth.json present at {codex_home}",
    }
    if not _viability_probe_enabled():
        return presence_ok

    fresh_s = _finite_positive_env_s(
        "TINYASSETS_CODEX_AUTH_FRESH_S", DEFAULT_CODEX_AUTH_FRESH_S,
    )
    age = _codex_last_refresh_age_s(codex_home)
    if age is not None and 0 <= age < fresh_s:
        presence_ok["detail"] = (
            f"auth.json present at {codex_home}; last_refresh "
            f"{age:.0f}s ago (< {fresh_s:.0f}s) — refresh-viable"
        )
        return presence_ok

    ttl_s = _finite_positive_env_s(
        "TINYASSETS_AUTH_PROBE_TTL_S", DEFAULT_AUTH_PROBE_TTL_S,
    )
    now = _time.time()
    # Disk cache first (cross-process truth for an external daemon fleet), then the
    # in-memory layer (covers read-only CODEX_HOMEs).
    cached = _read_probe_cache_file(codex_home)
    if cached is None:
        cached = _auth_probe_cache.get(str(codex_home))
    if cached is not None and 0 <= now - cached[0] < ttl_s:
        return dict(cached[1])

    if not allow_probe:
        presence_ok["detail"] = (
            f"auth.json present at {codex_home}; last_refresh stale "
            f"(age {'unknown' if age is None else f'{age:.0f}s'}) — live "
            "probe deferred to the external daemon"
        )
        return presence_ok

    timeout_s = _finite_positive_env_s(
        "TINYASSETS_AUTH_PROBE_TIMEOUT_S", DEFAULT_AUTH_PROBE_TIMEOUT_S,
    )
    probe = _codex_live_auth_probe(timeout_s)
    if probe["status"] == "not_logged_in":
        health = {"provider": "codex", "status": "not_logged_in",
                  "detail": probe["detail"]}
    else:
        # "ok" and "inconclusive" both read ok: only a POSITIVE dead
        # signature quarantines (false not_logged_in on a healthy worker is
        # worse; a false ok still fails at call time + trips loop_stalled).
        health = {"provider": "codex", "status": "ok",
                  "detail": f"auth.json present at {codex_home}; {probe['detail']}"}
    _auth_probe_cache[str(codex_home)] = (now, dict(health))
    _write_probe_cache_file(codex_home, now, health)
    return health


# Subscription-auth health. The 2026-06-25 loop-wedge root cause was an executor
# whose claude-code auth was dead (no credentials) that kept claiming tasks
# and failing every one, poisoning the queue for ~3 weeks undetected.
# ``is_available()`` only checks the binary is on PATH (``shutil.which``); it
# does NOT check login state. This helper lets an external daemon fail closed
# before claiming work instead of leaving the failure buried in executor logs.
#
# Returns ``{"provider", "status", "detail"}`` where status is one of:
#   "ok"            — subscription credentials are present (and, for codex,
#                     refresh-viable per the layered probe below)
#   "not_logged_in" — credentials are missing or proven dead (the actionable
#                     failure)
#   "unknown"       — no checkable subscription auth here (API-key providers,
#                     ollama, or an unrecognized name); callers never gate on it
#
# Codex gets a layered refresh-viability check on top of presence
# (live-proven gap 2026-07-14: a stale /data/.codex/auth.json stranded by the
# Jun-27 volume migration passed BOTH this presence check AND `codex login
# status`, yet 401'd at call time — the exact 2026-06-25 queue-poison class):
#   1. presence — auth.json missing => not_logged_in (unchanged fast path).
#   2. freshness — auth.json `last_refresh` (fallback: file mtime) younger
#      than TINYASSETS_CODEX_AUTH_FRESH_S => ok without any subprocess. An
#      actively-used token is refreshed by real calls, so busy workers never
#      pay for a probe.
#   3. live probe — stale creds trigger one tiny `codex exec` call (the check
#      that actually caught the dead token; `codex login status` only reads
#      the file locally and lies). Output matching the refresh-failure
#      signatures => not_logged_in (quarantine BEFORE the queue is poisoned).
#      Verdicts are cached per CODEX_HOME for TINYASSETS_AUTH_PROBE_TTL_S.
#
# Failure philosophy per the claude-code note below: inconclusive probe
# outcomes (binary missing, timeout, transport error) read "ok" — a false
# "ok" still fails at call time and trips loop_stalled; only a POSITIVE dead
# signature quarantines. The probe invokes whatever `codex` is on PATH, so
# deployments that ship the flock wrapper for the single-use refresh-token
# chain keep their serialization.
def subscription_auth_health(
    provider_name: str, *, allow_probe: bool = True,
) -> dict[str, str]:
    """Return subscription-auth health for *provider_name*.

    ``allow_probe=False`` for latency-sensitive callers (get_status): never
    spawns the live-probe subprocess; serves fast paths + cached verdicts.
    """
    name = (provider_name or "").strip()
    if name == "codex":
        codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
        if not (codex_home / "auth.json").is_file():
            return {"provider": name, "status": "not_logged_in",
                    "detail": f"no auth.json at {codex_home}"}
        return _codex_refresh_viability(codex_home, allow_probe=allow_probe)
    if name == "claude-code":
        if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip():
            return {"provider": name, "status": "ok",
                    "detail": "CLAUDE_CODE_OAUTH_TOKEN set"}
        config_dir = Path(
            os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")
        )
        # Deliberately conservative: any non-empty config dir reads "ok". For a
        # quarantine gate, a false "not_logged_in" (quarantining a HEALTHY
        # worker) is worse than a false "ok" (which still fails at call time and
        # trips the loop_stalled warning). Only the empty/absent dir — the exact
        # 2026-06-25 incident — yields "not_logged_in".
        try:
            if config_dir.is_dir() and any(config_dir.iterdir()):
                return {"provider": name, "status": "ok",
                        "detail": f"config dir populated at {config_dir}"}
        except OSError as exc:
            return {"provider": name, "status": "not_logged_in",
                    "detail": f"config dir unreadable: {exc}"}
        return {"provider": name, "status": "not_logged_in",
                "detail": f"no token and empty/absent {config_dir}"}
    return {"provider": name, "status": "unknown",
            "detail": "no subscription-auth probe for this provider"}


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


OS_SANDBOX_ATTESTATION_ENV = "TINYASSETS_OS_SANDBOX_ATTESTED"


def os_sandbox_attested() -> bool:
    """True only when the ENTIRE server process is attested to run under real OS
    isolation.

    Meant to be set (``TINYASSETS_OS_SANDBOX_ATTESTED=1``) ONLY by a container
    entrypoint that has genuinely confined the whole process (container-per-job /
    gVisor / microVM / namespaces). This is the ONLY thing that confines an
    in-process, NON-self-sandboxing coding agent like ``claude -p`` — which is
    spawned with Bash/Read/Write and has no sandbox flag of its own. A launchable
    ``bwrap`` (``get_sandbox_status``) proves only that bwrap CAN start a sandbox;
    it does NOT prove the running ``claude -p`` subprocess is confined (Codex S3
    review). So confinement of that class is gated on this attestation, never on
    bwrap-launchability.

    Reality today (patch-loop S3): the production entrypoint / compose
    (``deploy/docker-entrypoint.sh``, ``deploy/compose.yml``) DELIBERATELY do NOT
    set this — the current droplet provides no per-job OS isolation, so every
    sandbox-required coding node fails closed at run time BY DESIGN until such a
    host exists. Do not set it as a convenience; that re-opens the exact
    exfiltration vector the gate closes.

    ``TINYASSETS_OS_SANDBOX_ATTESTED`` may ONLY be set when a real per-job runner
    provides ALL of (Codex latest-model FINDING 3, the deferred production
    enabler — NOT built in this slice):
      (a) a prepared per-job repo checkout (the job's own working tree),
      (b) tenant/host path invisibility (no /data, no other tenants, no platform
          source visible to the job),
      (c) restricted network egress,
      (d) resource limits (cpu/mem/pids/time), and
      (e) scoped credential brokering — the job sees ONLY its own owner-scoped
          credential, never platform-global auth (see sanitized_subprocess_env /
          FINDING 2).
    Until a runner enforces all five, coding nodes stay fail-closed in prod — that
    is the design, stated loudly.
    """
    return _truthy_env(os.environ.get(OS_SANDBOX_ATTESTATION_ENV))


def enforce_os_sandbox(config: "ModelConfig") -> None:
    """Fail closed unless the running process is attested to be OS-isolated.

    The build-blocking gate for coding nodes (``os_sandbox_required``): a node
    that runs a coding agent with real filesystem/shell tools against a repo can
    only be confined by an OS-level sandbox around the WHOLE process — the CLI
    tool denylist cannot pin Read/Bash to a directory, and ``claude -p`` does not
    self-sandbox. Requiring merely that ``bwrap`` can launch is insufficient: a
    bare Linux host where bwrap works would pass yet still spawn ``claude -p``
    UNCONFINED (Codex S3 CRITICAL). So the gate requires
    :func:`os_sandbox_attested` — a positive attestation from the container
    entrypoint that the process is actually isolated. No attestation ⇒ raise so
    the node fails LOUDLY (hard rule #8) rather than run a coding agent
    unconfined on the capacity host (arbitrary-repo exfiltration / abuse vector).
    Called by the router preflight and the claude provider BEFORE spawning.
    No-op for host-trusted roles (``os_sandbox_required`` is False by default).

    (Codex ``codex exec`` self-confines via ``--full-auto`` + bwrap and enforces
    that in its own provider path; this whole-process attestation is the gate for
    the non-self-sandboxing ``claude -p`` path and the provider-agnostic router
    preflight.)
    """
    if not getattr(config, "os_sandbox_required", False):
        return
    if not os_sandbox_attested():
        raise SandboxUnavailableError(
            "This node runs a coding agent with real filesystem/shell tools and "
            "requires the ENTIRE server process to run under verified OS "
            "isolation (a container entrypoint that confines the process and "
            f"sets {OS_SANDBOX_ATTESTATION_ENV}=1). That attestation is absent — "
            "and a launchable bwrap does NOT prove the running claude -p "
            "subprocess is confined (it is spawned with Bash/Read/Write and no "
            "self-sandbox). Refusing to run the coding node unconfined (fail "
            "closed). Run the daemon inside the attested OS-isolation container, "
            "or use a design-only branch with no requires_sandbox nodes."
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

    supports_coding_sandbox: bool = False
    """Whether this provider DECLARES AND ENFORCES the hardened coding-sandbox
    contract (os_sandbox attestation / bwrap self-confinement + sanitized env +
    tool policy). Only the subprocess CLI providers (claude-code, codex) do. A
    sandbox-required call is HARD-FILTERED to these providers before dispatch
    (Codex latest-model FINDING 4): a text/HTTP/local provider (e.g. ollama)
    silently ignores the hardened config and would return a fake 'patched'
    without ever confining anything — never let it serve a coding job."""

    enforces_closed_tool_surface: bool = False
    """Whether this provider actually HONORS a closed / text-only tool surface
    (``ModelConfig.closed_tool_surface`` → claude ``--tools ""``). TRUE only for
    claude-code. FALSE for codex — codex ignores tool allow/deny fields entirely,
    so a ``closed_tool_surface`` node routed to codex would silently keep tools.
    A call whose config requires the closed surface is HARD-FILTERED to enforcing
    providers before dispatch (Codex S3 REJECT r2 C1b); if none is available it
    fails closed rather than run on a provider that can't honor it."""

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
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        """Send *prompt* with *system* instructions and return a response.

        *universe_dir*, when supplied, scopes vault-backed subscription auth to
        that universe (subscription-backed providers pass it into
        :func:`subprocess_env_for_provider`); providers that never touch the
        vault ignore it.
        """
