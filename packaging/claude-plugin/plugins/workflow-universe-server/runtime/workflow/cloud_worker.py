"""Cloud-side node-executor worker — real 24/7 uptime for node execution.

Motivation
----------
Today's droplet container runs ``python -m workflow.universe_server`` which
is MCP-server-only. It answers protocol handshakes, it lists tools, it
returns ``get_status`` output — but it does NOT execute queued
BranchTasks. Execution depends on the host's Windows tray running
``fantasy_daemon``. When the host's laptop is off, queued requests
pile up at ``pending_requests`` forever.

Evidence from live prod 2026-04-22:
  last_activity=2026-04-20T05:44Z (~2d stale)
  pending_requests=3
  activity_log=0 entries
  phase=offline/dormant-starved

This module closes that gap. It runs as a sibling container to the MCP
daemon, identifies itself as ``cloud-droplet`` (distinct from the host's
``host`` identity), and supervises a ``fantasy_daemon`` subprocess
against the active universe. The subprocess's normal claim→execute→
finalize loop picks up queued tasks via ``dispatcher.select_next_task``
+ ``branch_tasks.claim_task``. The claim is file-locked so the host's
tray + the cloud worker can run concurrently without double-claiming.

Why supervise a subprocess instead of re-implementing the claim loop?
  - ``fantasy_daemon._run_graph`` is ~500 lines tightly coupled to
    SqliteSaver, dashboard events, knowledge graph, heartbeat. Replicating
    it in-process would be a substantial refactor.
  - The subprocess inherits ``/etc/workflow/env`` (via compose env_file)
    after project-wide provider auth policy is applied. API-key provider
    env vars are stripped unless ``WORKFLOW_ALLOW_API_KEY_PROVIDERS=1``.
  - Supervision is simple: restart on exit, exponential backoff on
    repeated failures. The GHA p0-outage-triage watchdog-hotloop class
    already covers the pathological case if backoff hits its ceiling.

Concurrency safety
------------------
``workflow.branch_tasks.claim_task`` is file-locked via a sidecar .lock
file (see ``workflow/branch_tasks.py:_file_lock``). Two fantasy_daemon
processes on different hosts claiming tasks in the same universe dir
will race for the lock; the loser sees ``status != "pending"`` and
returns None. No double-claim is possible.

The cloud worker identifies itself via ``UNIVERSE_SERVER_HOST_USER=
cloud-droplet`` so activity log entries distinguish laptop-host runs
from cloud-droplet runs. Default ``host`` is the laptop; ``cloud-droplet``
is this supervisor's subprocess.

LLM routing
-----------
The subprocess defaults to subscription-backed auth. API-key provider env vars
are stripped unless the host deliberately enables
``WORKFLOW_ALLOW_API_KEY_PROVIDERS=1`` for this daemon. Optionally, host can
set ``FANTASY_DAEMON_LLM_TYPES`` or ``WORKFLOW_PIN_WRITER`` on the cloud side
to pin an approved subscription-backed model and let the host's tray handle
other runs when it's online — that configuration is orthogonal to this
supervisor and applies naturally via ``/etc/workflow/env``.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Defaults tuned for a droplet-scale workload.
DEFAULT_IDLE_BACKOFF_S = 10.0     # Seconds to sleep after a clean exit.
DEFAULT_CRASH_BACKOFF_S = 5.0     # Initial backoff on non-zero exit.
DEFAULT_MAX_BACKOFF_S = 300.0     # 5-min ceiling on exponential backoff.
DEFAULT_BACKOFF_MULT = 2.0        # Doubling per consecutive crash.
DEFAULT_POLL_INTERVAL_S = 0.5     # Subprocess monitor poll granularity.
DEFAULT_PRODUCER_POLL_INTERVAL_S = 30.0  # Goal-pool pickup latency cap.
# Re-check cadence while a worker is auth-quarantined. Short enough that a
# re-seeded credential resumes claiming promptly; long enough that a dead-auth
# worker doesn't spin. NOT escalated like crash backoff — auth-dead is a steady
# state, not a crash, and must not feed the crash counter.
DEFAULT_AUTH_QUARANTINE_BACKOFF_S = 60.0

# Host identity. Matches AGENTS.md §Configuration →
# UNIVERSE_SERVER_HOST_USER semantics. We default to "cloud-droplet"
# so activity-log entries are distinguishable from the laptop's "host"
# identity.
DEFAULT_HOST_USER = "cloud-droplet"
DEFAULT_WORKER_MODELS = {
    "codex": "gpt-5",
    "claude-code": "claude",
}


def _resolve_universe_path() -> Path:
    """Return the universe path the subprocess should operate on.

    Precedence (first non-empty wins):
      1. ``WORKFLOW_UNIVERSE`` env var (explicit override).
      2. ``$WORKFLOW_DATA_DIR/$UNIVERSE_SERVER_DEFAULT_UNIVERSE``.
      3. First directory under ``WORKFLOW_DATA_DIR`` that has a
         ``PROGRAM.md`` or ``soul.md`` (auto-selects the active universe in the common
         "one universe" droplet deployment).
      4. ``$WORKFLOW_DATA_DIR/default-universe`` as a last-resort fallback.
    """
    explicit = os.environ.get("WORKFLOW_UNIVERSE", "").strip()
    if explicit:
        return Path(explicit)

    from workflow.storage import active_universe_id, data_dir
    base = data_dir()

    active_uid = active_universe_id(base)
    if active_uid:
        return base / active_uid

    default_uid = os.environ.get("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "").strip()
    if default_uid:
        candidate = base / default_uid
        if candidate.is_dir():
            return candidate

    if base.is_dir():
        for entry in sorted(base.iterdir()):
            if (
                entry.is_dir()
                and ((entry / "PROGRAM.md").exists() or (entry / "soul.md").exists())
            ):
                return entry

    return base / "default-universe"


def _cloud_host_user() -> str:
    """Host-user identity for activity log entries.

    Operators can override via ``UNIVERSE_SERVER_HOST_USER`` but the
    default is ``cloud-droplet`` so the droplet's activity is trivially
    distinguishable from the laptop's ``host`` entries in ``get_status``.
    """
    override = os.environ.get("UNIVERSE_SERVER_HOST_USER", "").strip()
    return override or DEFAULT_HOST_USER


def _worker_id() -> str:
    override = os.environ.get("WORKFLOW_WORKER_ID", "").strip()
    return override or _cloud_host_user()


def _safe_worker_id(worker_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", worker_id.strip())
    return safe.strip(".-") or "default"


def supervisor_heartbeat_filename(worker_id: str | None = None) -> str:
    clean = _safe_worker_id(worker_id or "")
    if not worker_id or clean == "default":
        return SUPERVISOR_HEARTBEAT_FILENAME
    return f".worker_supervisor.{clean}.json"


def _build_subprocess_env(universe: Path | None = None) -> dict[str, str]:
    """Construct the env dict the fantasy_daemon subprocess inherits.

    Starts from the parent env, overlays the cloud-specific host-user
    identity, and applies the project-wide provider auth policy before
    subprocess launch.
    """
    from workflow.providers.base import subprocess_env_without_api_keys

    env = subprocess_env_without_api_keys() or dict(os.environ)
    env["UNIVERSE_SERVER_HOST_USER"] = _cloud_host_user()
    if universe is not None:
        env["WORKFLOW_UNIVERSE"] = str(universe)
    # Make sure unified execution is on — dispatcher pick is gated on
    # this flag. It defaults on in production but we force it here so
    # cloud worker behavior is deterministic regardless of env file.
    env.setdefault("WORKFLOW_UNIFIED_EXECUTION", "1")
    return env


def _provider_from_daemon_args(extra_args: list[str] | None) -> str:
    args = list(extra_args or [])
    for idx, value in enumerate(args):
        if value == "--provider" and idx + 1 < len(args):
            return str(args[idx + 1]).strip()
        if value.startswith("--provider="):
            return value.split("=", 1)[1].strip()
    return ""


def _worker_model_for_provider(provider_name: str) -> str:
    explicit = os.environ.get("WORKFLOW_WORKER_MODEL", "").strip()
    if explicit:
        return explicit
    if provider_name == "codex":
        return os.environ.get("WORKFLOW_CODEX_MODEL", "").strip() or DEFAULT_WORKER_MODELS["codex"]
    if provider_name == "claude-code":
        return (
            os.environ.get("WORKFLOW_CLAUDE_MODEL", "").strip()
            or DEFAULT_WORKER_MODELS["claude-code"]
        )
    return provider_name


def _subscription_auth_available(provider_name: str) -> bool:
    """True unless the provider's subscription credentials are missing.

    Delegates to the shared ``subscription_auth_health`` probe so the worker
    self-quarantine gate, the registry-visibility check, and ``get_status``
    all read auth from one source of truth.
    """
    from workflow.providers.base import subscription_auth_health

    return subscription_auth_health(provider_name).get("status") != "not_logged_in"


def _worker_auth_health(daemon_args: list[str] | None) -> dict[str, str] | None:
    """Resolve this worker's writer provider and its subscription-auth health.

    Returns ``None`` when no specific writer is resolvable (a generic worker we
    must not gate — it may legitimately route across the fallback chain).
    Otherwise returns the ``subscription_auth_health`` dict for the worker's
    pinned / ``--provider`` writer so the supervisor can self-quarantine a
    dead-auth worker before it claims and poisons the queue.
    """
    provider = _provider_from_daemon_args(daemon_args) or os.environ.get(
        "WORKFLOW_PIN_WRITER", ""
    ).strip()
    if not provider:
        return None
    from workflow.providers.base import subscription_auth_health

    return subscription_auth_health(provider)


def _register_worker_runtime(universe: Path, provider_name: str) -> str | None:
    """Best-effort runtime registry visibility for a supervised worker."""
    if not provider_name:
        return None
    if not _subscription_auth_available(provider_name):
        logger.warning(
            "cloud_worker: %s subscription auth not available; "
            "runtime registration will retry on next spawn",
            provider_name,
        )
        return None
    try:
        from workflow.daemon_registry import (
            ensure_daemon_runtime,
            select_project_loop_daemon,
        )
        from workflow.storage import data_dir

        base = data_dir()
        daemon = select_project_loop_daemon(base)
        if daemon is None:
            logger.warning(
                "cloud_worker: no project loop daemon registered; "
                "skipping runtime registration",
            )
            return
        runtime = ensure_daemon_runtime(
            base,
            daemon_id=daemon["daemon_id"],
            universe_id=universe.name or "default-universe",
            provider_name=provider_name,
            model_name=_worker_model_for_provider(provider_name),
            created_by=_cloud_host_user(),
            worker_id=_worker_id(),
            metadata={
                "container_host": socket.gethostname(),
                "worker_provider": provider_name,
            },
        )
        logger.info(
            "cloud_worker: runtime registered worker_id=%s provider=%s runtime=%s",
            _worker_id(), provider_name, runtime["runtime_instance_id"],
        )
        return str(runtime["runtime_instance_id"])
    except Exception:  # noqa: BLE001
        logger.exception(
            "cloud_worker: runtime registration failed for provider=%s",
            provider_name,
        )
    return None


def _truthy_env(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _soul_loop_declared_for_universe(universe: Path) -> bool:
    """Return True when the dark soul-loop worker route should be used."""
    if not _truthy_env("WORKFLOW_SOUL_LOOP_DISPATCH"):
        return False
    try:
        from workflow.api.universe import (
            LEGACY_FANTASY_LOOP_BRANCH_DEF_ID,
            _universe_loop_dispatch,
        )

        loop_branch_def_id, _info = _universe_loop_dispatch(universe)
    except Exception:  # noqa: BLE001
        logger.exception(
            "cloud_worker: soul-loop dispatch resolution failed for %s",
            universe,
        )
        return False
    return bool(
        loop_branch_def_id
        and loop_branch_def_id != LEGACY_FANTASY_LOOP_BRANCH_DEF_ID
    )


def _daemon_module_for_universe(universe: Path) -> str:
    if _soul_loop_declared_for_universe(universe):
        return "workflow"
    return "fantasy_daemon"


def _spawn_daemon_for_universe(
    universe: Path,
    *,
    extra_args: list[str] | None = None,
) -> subprocess.Popen:
    """Spawn the legacy daemon, or the workflow bridge for flagged soul loops."""
    module = _daemon_module_for_universe(universe)
    if module == "fantasy_daemon":
        if extra_args is None:
            return _spawn_fantasy_daemon(universe)
        return _spawn_fantasy_daemon(universe, extra_args=extra_args)
    return _spawn_fantasy_daemon(
        universe,
        module=module,
        extra_args=extra_args,
    )


def _register_branch_task_producers_from_env() -> None:
    """Register flag-enabled producers in this worker process.

    The modules may have been imported before the env flags were set,
    so call ``register_if_enabled()`` explicitly instead of relying on
    import-time side effects.
    """
    if _truthy_env("WORKFLOW_GOAL_POOL"):
        from workflow.producers.goal_pool import register_if_enabled

        register_if_enabled()
    if _truthy_env("WORKFLOW_PAID_MARKET"):
        from workflow.producers.node_bid import register_if_enabled

        register_if_enabled()


def _queue_has_running_branch_task(universe: Path) -> bool:
    """Return True when interrupting the subprocess may abandon a claim."""
    try:
        from workflow.branch_tasks import read_queue

        return any(task.status == "running" for task in read_queue(universe))
    except Exception:  # noqa: BLE001
        logger.exception("cloud_worker: queue status check failed")
        return True


def _has_pickable_branch_task(universe: Path) -> bool:
    """Return True when the dispatcher has an eligible pending task.

    The MCP server appends some BranchTasks directly (not via producers).
    The long-running fantasy_daemon subprocess only attempts a dispatcher
    claim at startup, so the supervisor must notice these pending rows and
    restart the idle wrapper process to let it pick them up.
    """
    try:
        from workflow.dispatcher import (
            dispatcher_enabled,
            load_dispatcher_config,
            select_next_task,
        )

        if not dispatcher_enabled():
            return False
        unified = os.environ.get("WORKFLOW_UNIFIED_EXECUTION", "1")
        if unified.strip().lower() in {"0", "off", "false", "no"}:
            return False
        return select_next_task(
            universe,
            config=load_dispatcher_config(universe),
        ) is not None
    except Exception:  # noqa: BLE001
        logger.exception("cloud_worker: pending BranchTask check failed")
        return False


def _pump_branch_task_producers(universe: Path) -> int:
    """Append producer output to ``branch_tasks.json``.

    ``fantasy_daemon`` only scans producers at graph-start. The cloud
    worker is long-running, so a public goal-pool post that lands after
    startup can otherwise sit in ``goal_pool/`` indefinitely. Pumping
    here keeps the queue fresh even while the default graph is active.
    """
    if not (_truthy_env("WORKFLOW_GOAL_POOL") or _truthy_env("WORKFLOW_PAID_MARKET")):
        return 0
    try:
        _register_branch_task_producers_from_env()

        from workflow.dispatcher import run_branch_task_producers_into_queue
        from workflow.subscriptions import list_subscriptions

        return run_branch_task_producers_into_queue(
            universe,
            subscribed_goals=list_subscriptions(universe),
        )
    except Exception:  # noqa: BLE001
        logger.exception("cloud_worker: branch-task producer pump failed")
        return 0


def _spawn_fantasy_daemon(
    universe: Path,
    *,
    python: str = sys.executable,
    module: str = "fantasy_daemon",
    extra_args: list[str] | None = None,
) -> subprocess.Popen:
    """Spawn ``python -m fantasy_daemon --universe <path> --no-tray``.

    Returns the ``Popen`` handle. Caller owns lifecycle.
    """
    args = [
        python, "-m", module,
        "--universe", str(universe),
        "--no-tray",
    ]
    if extra_args:
        args.extend(extra_args)
    runtime_instance_id = _register_worker_runtime(
        universe,
        _provider_from_daemon_args(extra_args),
    )
    if runtime_instance_id:
        os.environ["WORKFLOW_RUNTIME_INSTANCE_ID"] = runtime_instance_id
    else:
        os.environ.pop("WORKFLOW_RUNTIME_INSTANCE_ID", None)
    env = _build_subprocess_env(universe)
    env["WORKFLOW_WORKER_ID"] = _worker_id()
    if runtime_instance_id:
        env["WORKFLOW_RUNTIME_INSTANCE_ID"] = runtime_instance_id
    else:
        env.pop("WORKFLOW_RUNTIME_INSTANCE_ID", None)
    logger.info(
        "spawning fantasy_daemon: universe=%s host_user=%s",
        universe, env.get("UNIVERSE_SERVER_HOST_USER"),
    )
    return subprocess.Popen(args, env=env)


def _compute_backoff(
    crash_count: int,
    *,
    base: float,
    mult: float,
    ceiling: float,
) -> float:
    """Exponential backoff: ``min(base * mult^(crash_count-1), ceiling)``.

    crash_count=1 → base, crash_count=2 → base*mult, etc. Capped so a
    long-running outage doesn't push retry gaps into hours.
    """
    if crash_count <= 0:
        return 0.0
    delay = base * (mult ** (crash_count - 1))
    return min(delay, ceiling)


class SupervisorState:
    """Runtime state for the supervisor loop. Testable without spawning.

    Tracks consecutive crashes + last exit status so the loop can
    compute correct backoff + recognize "clean shutdown vs. crash".
    """

    def __init__(self) -> None:
        self.crash_count = 0
        self.clean_exit_count = 0
        self.total_spawns = 0
        self.total_clean_exits = 0
        self.total_crashes = 0
        # Times this worker skipped spawning a claim-subprocess because its
        # writer provider was unauthenticated (auth self-quarantine).
        self.auth_quarantine_count = 0
        self.started_at = _utcnow_iso()
        self.last_spawn_at = ""
        self.last_exit_rc: int | None = None

    def record_exit(self, returncode: int) -> None:
        self.total_spawns += 1
        self.last_exit_rc = returncode
        if returncode == 0:
            self.crash_count = 0
            self.clean_exit_count += 1
            self.total_clean_exits += 1
        else:
            self.crash_count += 1
            self.clean_exit_count = 0
            self.total_crashes += 1

    def summary(self) -> str:
        return (
            f"spawns={self.total_spawns} "
            f"clean={self.total_clean_exits} "
            f"crashes={self.total_crashes} "
            f"consec={self.crash_count} "
            f"auth_quarantined={self.auth_quarantine_count}"
        )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Heartbeat file the supervisor writes into the universe dir. Liveness
# consumers (workflow.api.universe worker_liveness, the activity canary,
# workflow.cloud_worker_healthcheck) read it to distinguish "worker wedged"
# from "idle, nothing queued" — the gap behind the 2026-06 dormancy
# (docs/specs/daemon-liveness-watchdog.md). Deliberately NOT activity.log:
# that file's mtime is the daemon last-activity source, and supervisor
# ticks freshening it would mask a wedged subprocess.
SUPERVISOR_HEARTBEAT_FILENAME = ".worker_supervisor.json"


def write_supervisor_heartbeat(
    universe: Path,
    state: SupervisorState,
    *,
    iteration: int,
    phase: str,
    subprocess_pid: int | None = None,
    subprocess_alive: bool = False,
    planned_sleep_s: float = 0.0,
) -> None:
    """Atomically write the supervisor liveness beat. Best-effort.

    A probe write must never take down the supervisor (the loop IS the
    uptime surface), so failures log loudly and return.
    """
    beat = {
        "ts": _utcnow_iso(),
        "phase": phase,
        "iteration": iteration,
        "supervisor_started_at": state.started_at,
        "last_spawn_at": state.last_spawn_at,
        "last_exit_rc": state.last_exit_rc,
        "total_spawns": state.total_spawns,
        "total_crashes": state.total_crashes,
        "consec_crashes": state.crash_count,
        "subprocess_pid": subprocess_pid,
        "subprocess_alive": subprocess_alive,
        "planned_sleep_s": planned_sleep_s,
        "worker_id": _worker_id(),
        "runtime_instance_id": os.environ.get(
            "WORKFLOW_RUNTIME_INSTANCE_ID", "",
        ).strip(),
    }
    filenames = [supervisor_heartbeat_filename(_worker_id())]
    if filenames[0] != SUPERVISOR_HEARTBEAT_FILENAME:
        filenames.append(SUPERVISOR_HEARTBEAT_FILENAME)
    for filename in filenames:
        target = universe / filename
        tmp = universe / (filename + ".tmp")
        try:
            tmp.write_text(json.dumps(beat), encoding="utf-8")
            tmp.replace(target)
        except OSError:
            logger.exception("cloud_worker: heartbeat write failed at %s", target)


# Stop-path child-termination budget. Docker's default stop_grace_period is 10s:
# on redeploy the container gets SIGTERM then SIGKILL 10s later. The supervisor
# must terminate the child, CONFIRM its death, AND release its orphaned lease
# within that window, so these are intentionally short. The old 30s wait never
# completed — docker killed the container mid-wait, so neither the child's
# graceful finalize nor the lease release ran. A child between nodes exits in <1s
# (and finalizes its own lease); a child mid-LLM node won't exit in 5s OR 30s, so
# the shorter wait loses nothing and leaves room for the kill-confirm + release
# before SIGKILL (5 + 2 + release < 10s). The producer restart path (container
# stays up) keeps the longer 30s wait.
_STOP_CHILD_DRAIN_S = 5.0
# After SIGKILL, confirm the child is actually gone before releasing its lease.
_STOP_KILL_CONFIRM_S = 2.0


def _terminate_child_for_stop(proc) -> bool:
    """Terminate the subprocess on shutdown; return True iff its exit is CONFIRMED.

    SIGTERM first (lets a between-nodes child finalize its own lease), then a
    bounded wait; on timeout SIGKILL and a short confirm wait. The caller must
    release the child's orphaned lease ONLY when this returns True — releasing
    while the child can still run risks it ``mark_status()``-ing a row a peer has
    since re-claimed (``mark_status`` has no owner guard), prematurely
    terminalizing the peer's work. If death can't be confirmed, the startup
    reclaim (PR #1401) and the lease TTL remain the backstop. Codex review.
    """
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=_STOP_CHILD_DRAIN_S)
        return True
    except subprocess.TimeoutExpired:
        logger.warning("cloud_worker: subprocess did not exit; killing")
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=_STOP_KILL_CONFIRM_S)
        return True
    except subprocess.TimeoutExpired:
        logger.warning(
            "cloud_worker: subprocess still alive after kill; skipping shutdown "
            "lease release (startup/TTL reclaim will recover)",
        )
        return False


def _release_own_orphaned_leases(universe: Path) -> int:
    """Release branch-task leases orphaned by this worker's dead subprocess.

    Graceful-drain complement to the startup reclaim (PR #1401): reuses
    ``reclaim_predecessor_tasks`` at SHUTDOWN. By the time the supervisor loop
    exits the subprocess is dead, so any ``running`` row under our own
    ``worker_id`` is an orphan it left (a SIGKILL mid-node on redeploy skips the
    child's finalize). Releasing here frees the work for a live PEER immediately
    instead of waiting for our replacement container to boot (whose startup
    reclaim is the backstop). Best-effort — cleanup must never crash shutdown.

    Scoped to our own unique ``worker_id``; the shared ``DEFAULT_HOST_USER``
    fallback is excluded for the same reason as ``_dispatcher_startup`` — several
    un-configured supervisors could share it, and reclaiming it could steal a
    live twin's task.
    """
    worker_id = _worker_id()
    if not worker_id or worker_id == DEFAULT_HOST_USER:
        return 0
    try:
        from workflow.branch_tasks import reclaim_predecessor_tasks

        released = reclaim_predecessor_tasks(universe, worker_id=worker_id)
        if released:
            logger.info(
                "cloud_worker: released %d orphaned lease(s) for worker_id=%s "
                "on shutdown (graceful drain)",
                released, worker_id,
            )
        return released
    except Exception:  # noqa: BLE001 — shutdown cleanup must not raise
        logger.exception("cloud_worker: shutdown lease release failed")
        return 0


def run_supervisor(
    universe: Path,
    *,
    idle_backoff: float = DEFAULT_IDLE_BACKOFF_S,
    crash_backoff: float = DEFAULT_CRASH_BACKOFF_S,
    max_backoff: float = DEFAULT_MAX_BACKOFF_S,
    backoff_mult: float = DEFAULT_BACKOFF_MULT,
    poll_interval: float = DEFAULT_POLL_INTERVAL_S,
    producer_poll_interval: float = DEFAULT_PRODUCER_POLL_INTERVAL_S,
    auth_quarantine_backoff: float = DEFAULT_AUTH_QUARANTINE_BACKOFF_S,
    max_iterations: int | None = None,
    daemon_args: list[str] | None = None,
    spawn_fn=None,
    sleep_fn=None,
) -> SupervisorState:
    """Run the supervisor loop until max_iterations or SIGTERM.

    Each iteration:
      1. Spawn the daemon against the universe.
      2. Wait for it to exit.
      3. Record exit as clean or crash.
      4. Sleep with exponential backoff after consecutive clean exits or
         crashes. Clean exits usually mean no active work; backing them off
         prevents the universe-cycle wrapper from steady polling while idle.

    ``max_iterations`` is an injection seam for tests — leave None in
    production for an unbounded loop. ``spawn_fn`` + ``sleep_fn`` are
    test seams so the loop can be exercised without subprocess I/O.
    None defaults resolve to the module-level ``_spawn_daemon_for_universe``
    + ``time.sleep`` at call time (not import time), so tests can
    monkeypatch the module attribute freely.
    """
    if spawn_fn is None:
        if daemon_args:
            def spawn_fn(universe: Path) -> subprocess.Popen:
                return _spawn_daemon_for_universe(
                    universe,
                    extra_args=daemon_args,
                )
        else:
            spawn_fn = _spawn_daemon_for_universe
    if sleep_fn is None:
        sleep_fn = time.sleep

    state = SupervisorState()
    iteration = 0
    # True only when a shutdown terminated the child AND confirmed its exit —
    # gates the graceful-drain lease release (see _terminate_child_for_stop).
    child_confirmed_dead = False

    # SIGTERM handling: clean exit on compose stop / systemctl stop.
    # Sets a flag the loop checks between iterations.
    stopping = {"flag": False}

    def _handle_sigterm(signum, frame):
        logger.info("cloud_worker: received signal %s — shutting down", signum)
        stopping["flag"] = True

    # Install handler only when running as __main__; tests call
    # run_supervisor directly and manage their own signals.
    if threading_is_main():
        try:
            signal.signal(signal.SIGTERM, _handle_sigterm)
            signal.signal(signal.SIGINT, _handle_sigterm)
        except (ValueError, OSError):
            # Signals unavailable in certain embed contexts.
            pass

    while True:
        if stopping["flag"]:
            logger.info("cloud_worker: stop requested; exiting supervisor loop")
            break
        if max_iterations is not None and iteration >= max_iterations:
            break
        iteration += 1

        # Pre-claim auth gate (2026-06-25 loop-wedge root cause): a worker
        # whose writer provider is unauthenticated must NOT spawn the claim
        # subprocess. A dead-auth worker claims tasks, fails every one, and
        # corrupts the queue (failed > succeeded; genuine peer successes lost
        # to Invalid-transition). Self-quarantine: skip the spawn, beat, back
        # off, re-check — a re-seeded credential resumes claiming next tick.
        auth = _worker_auth_health(daemon_args)
        if auth is not None and auth.get("status") == "not_logged_in":
            state.auth_quarantine_count += 1
            logger.error(
                "cloud_worker: writer provider %s is unauthenticated (%s) — "
                "QUARANTINING worker, not claiming. Re-seed provider auth to "
                "resume. (2026-06-25 loop-wedge prevention)",
                auth.get("provider"), auth.get("detail"),
            )
            write_supervisor_heartbeat(
                universe, state, iteration=iteration, phase="auth_quarantined",
                planned_sleep_s=auth_quarantine_backoff,
            )
            sleep_fn(auth_quarantine_backoff)
            continue

        try:
            proc = spawn_fn(universe)
        except OSError as exc:
            logger.error("cloud_worker: spawn failed: %s", exc)
            state.crash_count += 1
            state.clean_exit_count = 0
            state.total_crashes += 1
            delay = _compute_backoff(
                state.crash_count,
                base=crash_backoff, mult=backoff_mult, ceiling=max_backoff,
            )
            logger.info("cloud_worker: backoff %.1fs after spawn failure (consec=%d)",
                        delay, state.crash_count)
            write_supervisor_heartbeat(
                universe, state, iteration=iteration, phase="spawn_failed",
                planned_sleep_s=delay,
            )
            sleep_fn(delay)
            continue
        state.last_spawn_at = _utcnow_iso()
        write_supervisor_heartbeat(
            universe, state, iteration=iteration, phase="spawned",
            subprocess_pid=getattr(proc, "pid", None), subprocess_alive=True,
        )

        # Poll until subprocess exits, while respecting stop signal.
        returncode: int | None = None
        queue_restart_reason = ""
        # The subprocess attempts its dispatcher claim during startup. If
        # BranchTasks are already pending, polling immediately would terminate
        # the child before it gets a chance to claim them, creating a restart
        # loop. Start the producer clock now and only restart if the task is
        # still pickable after one poll interval.
        last_producer_poll = time.monotonic()
        last_beat = time.monotonic()
        while True:
            if time.monotonic() - last_beat >= 15.0:
                last_beat = time.monotonic()
                write_supervisor_heartbeat(
                    universe, state, iteration=iteration, phase="polling",
                    subprocess_pid=getattr(proc, "pid", None),
                    subprocess_alive=True,
                )
            if stopping["flag"]:
                logger.info("cloud_worker: terminating subprocess on stop signal")
                child_confirmed_dead = _terminate_child_for_stop(proc)
                returncode = proc.returncode if proc.returncode is not None else -1
                break
            rc = proc.poll()
            if rc is not None:
                returncode = rc
                break
            if producer_poll_interval > 0:
                now = time.monotonic()
                if now - last_producer_poll >= producer_poll_interval:
                    last_producer_poll = now
                    if not _queue_has_running_branch_task(universe):
                        appended = _pump_branch_task_producers(universe)
                        if appended > 0:
                            queue_restart_reason = (
                                f"{appended} producer task(s)"
                            )
                        elif _has_pickable_branch_task(universe):
                            queue_restart_reason = "pending BranchTask"

                        if queue_restart_reason:
                            logger.info(
                                "cloud_worker: queued %s; "
                                "restarting subprocess to pick them up",
                                queue_restart_reason,
                            )
                            try:
                                proc.terminate()
                                proc.wait(timeout=30)
                            except subprocess.TimeoutExpired:
                                logger.warning(
                                    "cloud_worker: subprocess did not exit "
                                    "after producer restart; killing",
                                )
                                try:
                                    proc.kill()
                                except OSError:
                                    pass
                                returncode = -1
                                break
                            except OSError:
                                returncode = -1
                                break
                            returncode = 0
                            break
            sleep_fn(poll_interval)

        state.record_exit(returncode if returncode is not None else -1)
        logger.info(
            "cloud_worker: subprocess exited rc=%s (%s); %s",
            returncode,
            (
                f"queue-restart:{queue_restart_reason}"
                if queue_restart_reason
                else "clean" if returncode == 0 else "crash"
            ),
            state.summary(),
        )

        if stopping["flag"]:
            break

        if returncode == 0:
            delay = _compute_backoff(
                state.clean_exit_count,
                base=idle_backoff, mult=backoff_mult, ceiling=max_backoff,
            )
        else:
            delay = _compute_backoff(
                state.crash_count,
                base=crash_backoff, mult=backoff_mult, ceiling=max_backoff,
            )
        logger.info("cloud_worker: sleeping %.1fs before next spawn", delay)
        write_supervisor_heartbeat(
            universe, state, iteration=iteration, phase="backoff",
            planned_sleep_s=delay,
        )
        sleep_fn(delay)

    # Graceful drain: on shutdown (SIGTERM/compose stop), the just-killed child
    # may have orphaned a still-valid lease mid-node. Release it now so a live
    # peer can pick the work up immediately, rather than stranding it until the
    # ~30min TTL or our replacement's startup reclaim (PR #1401 backstop). Only
    # when the child's exit is CONFIRMED — releasing while it can still run could
    # terminalize a peer's re-claimed row (mark_status has no owner guard).
    if stopping["flag"] and child_confirmed_dead:
        _release_own_orphaned_leases(universe)
    write_supervisor_heartbeat(
        universe, state, iteration=iteration, phase="stopped",
    )
    return state


def threading_is_main() -> bool:
    """Return True when called from the main thread.

    signal.signal() only works from the main thread. We guard the
    handler install so tests that invoke run_supervisor from a worker
    thread don't trip.
    """
    import threading
    return threading.current_thread() is threading.main_thread()


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="workflow.cloud_worker",
        description="Cloud-side supervisor for 24/7 node execution.",
    )
    parser.add_argument(
        "--universe",
        default="",
        help="Explicit universe path. Default: WORKFLOW_UNIVERSE / "
             "first PROGRAM.md or soul.md / WORKFLOW_DATA_DIR/default-universe.",
    )
    parser.add_argument(
        "--idle-backoff", type=float, default=DEFAULT_IDLE_BACKOFF_S,
        help=f"Seconds to sleep after a clean daemon exit (default: "
             f"{DEFAULT_IDLE_BACKOFF_S}).",
    )
    parser.add_argument(
        "--crash-backoff", type=float, default=DEFAULT_CRASH_BACKOFF_S,
        help=f"Initial backoff on crash (default: {DEFAULT_CRASH_BACKOFF_S}).",
    )
    parser.add_argument(
        "--max-backoff", type=float, default=DEFAULT_MAX_BACKOFF_S,
        help=f"Backoff ceiling (default: {DEFAULT_MAX_BACKOFF_S}).",
    )
    parser.add_argument(
        "--max-iterations", type=int, default=None,
        help="Stop after this many supervisor iterations (testing only).",
    )
    parser.add_argument(
        "--producer-poll-interval",
        type=float,
        default=DEFAULT_PRODUCER_POLL_INTERVAL_S,
        help="Seconds between cloud-side producer scans while the "
             f"subprocess is running (default: {DEFAULT_PRODUCER_POLL_INTERVAL_S}).",
    )
    parser.add_argument(
        "--provider",
        default="",
        help="Pin the supervised fantasy_daemon writer provider.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="DEBUG-level logging.",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    universe = Path(args.universe) if args.universe else _resolve_universe_path()
    if not universe.exists():
        logger.warning("cloud_worker: universe dir does not exist yet: %s", universe)
        logger.warning("cloud_worker: fantasy_daemon will create it on first run")

    logger.info(
        "cloud_worker: starting supervisor host=%s universe=%s host_user=%s",
        socket.gethostname(), universe, _cloud_host_user(),
    )

    state = run_supervisor(
        universe,
        idle_backoff=args.idle_backoff,
        crash_backoff=args.crash_backoff,
        max_backoff=args.max_backoff,
        producer_poll_interval=args.producer_poll_interval,
        max_iterations=args.max_iterations,
        daemon_args=["--provider", args.provider] if args.provider else None,
    )
    logger.info("cloud_worker: supervisor exited; %s", state.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
