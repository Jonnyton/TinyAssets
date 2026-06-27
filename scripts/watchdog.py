"""TinyAssets daemon watchdog — probe + restart on sustained failure.

Self-host migration Row L per
``docs/exec-plans/active/2026-04-20-selfhost-uptime-migration.md``.

Beyond systemd's ``Restart=always`` (which handles process crash + OOM),
this watchdog catches the failure mode systemd CAN'T see: the daemon
process is alive but the MCP endpoint is unresponsive (hung request
loop, deadlocked thread, wedged SQLite transaction, etc.).

Mechanism: probe the container-internal MCP endpoint every tick via
``scripts/mcp_public_canary.py``. Track consecutive reds across ticks
via a small state file. On 3 consecutive reds → ``systemctl restart
tinyassets-daemon`` (which the systemd unit wires to
``docker compose down && up``). On GREEN after reds → reset state.

Stdlib only. No third-party deps. Idempotent + race-free because the
timer is single-concurrency at the systemd level.

Exit codes
----------
0  Probe handled (green, first-red, sustained-red, or recovery).
   Restart may or may not have been issued; see stderr/journald for
   the decision.
1  Fatal watchdog failure (cannot invoke canary, cannot read/write
   state, systemctl not available). Unit should alert on this.

State
-----
Persisted at ``/var/lib/tinyassets-watchdog/state.json`` (readable +
writable by the ``workflow`` user). Schema::

    {"consecutive_reds": N, "last_probe_ts": "<iso>",
     "last_restart_ts": "<iso or null>"}

A missing file = zero-reds state. Corrupted file → reset to
zero-reds (warn via stderr).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PROBE_URL = "http://127.0.0.1:8001/mcp"
DEFAULT_STATE_DIR = Path("/var/lib/tinyassets-watchdog")
DEFAULT_STATE_FILE = DEFAULT_STATE_DIR / "state.json"
DEFAULT_CANARY_SCRIPT = Path("/opt/tinyassets/scripts/mcp_public_canary.py")
DEFAULT_SERVICE_UNIT = "tinyassets-daemon.service"
DEFAULT_THRESHOLD = 3
# Min wall-time between restarts. Prevents a wedged daemon from
# being restart-looped every 30s when the underlying problem
# (bad env, dep issue) isn't "restart will fix it."
MIN_RESTART_INTERVAL_SECONDS = 600  # 10 min

# Production alarm-log path. Env-var override allows tests + dev setups
# to redirect to a tmp path without touching the real production file.
# Pre-2026-04-26 default was `_REPO_ROOT / ".agents" / "uptime_alarms.log"`,
# which collided with `tests/test_watchdog.py` writes (no `alarm_log=`
# injection) and contaminated the only signal we had for production
# watchdog behavior. Audit: docs/audits/2026-04-26-restart-loop-correlation.md.
DEFAULT_ALARM_LOG = Path("/var/log/tinyassets/uptime_alarms.log")
ALARM_LOG = Path(
    os.environ.get("TINYASSETS_WATCHDOG_ALARM_LOG", str(DEFAULT_ALARM_LOG))
)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _log(level: str, msg: str) -> None:
    """Emit to stderr + optionally to journald via the `logger` cmd.

    systemd captures stderr of services launched via the .service unit,
    so stderr alone is enough for journald. The `logger` fallback is
    for direct invocations outside systemd.
    """
    line = f"[watchdog {level}] {msg}"
    print(line, file=sys.stderr)


def _append_alarm_log(line: str, alarm_log: Path = ALARM_LOG) -> None:
    """Append one line to the shared uptime_alarms.log. Best-effort."""
    try:
        alarm_log.parent.mkdir(parents=True, exist_ok=True)
        with alarm_log.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except OSError:
        pass


def _load_state(path: Path) -> dict:
    if not path.is_file():
        return {"consecutive_reds": 0, "last_probe_ts": None, "last_restart_ts": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log("WARN", f"state file corrupt ({exc!r}); resetting to zero-reds")
        return {"consecutive_reds": 0, "last_probe_ts": None, "last_restart_ts": None}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _probe(canary_script: Path, url: str, timeout: float) -> tuple[bool, str]:
    """Return (green, message). Green=True on canary exit 0."""
    if not canary_script.is_file():
        return (False, f"canary script missing: {canary_script}")
    try:
        result = subprocess.run(
            [sys.executable, str(canary_script), "--url", url, "--timeout", str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except subprocess.TimeoutExpired:
        return (False, f"canary timeout after {timeout + 5}s")
    except OSError as exc:
        return (False, f"canary invoke error: {exc}")
    if result.returncode == 0:
        return (True, "green")
    # Canary prints diagnostic to stderr; pass through.
    msg = (result.stderr or result.stdout or "").strip().replace("\n", " | ")
    return (False, f"exit={result.returncode}: {msg[:300]}")


GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "Jonnyton/TinyAssets")
GITHUB_API = "https://api.github.com"


def _open_gh_issue(title: str, body: str) -> tuple[bool, str]:
    """Open a GitHub issue via the REST API. Best-effort — never raises.

    Requires ``GH_TOKEN`` env var. If unset, logs a warning and returns
    (False, "GH_TOKEN not set"). Uses stdlib urllib only.
    """
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        return (False, "GH_TOKEN not set; skipping GH issue")
    payload = json.dumps({"title": title, "body": body, "labels": ["watchdog"]}).encode()
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/issues"
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return (True, f"issue #{result.get('number', '?')}: {result.get('html_url', '')}")
    except urllib.error.HTTPError as exc:
        return (False, f"GitHub API HTTP {exc.code}: {exc.read().decode()[:200]}")
    except Exception as exc:
        return (False, f"GitHub API error: {exc!r}")


def _restart_service(unit: str) -> tuple[bool, str]:
    """Issue systemctl restart via sudo. Return (success, message).

    The tinyassets user doesn't have bare systemctl privilege — the
    hetzner-bootstrap.sh script installs a scoped sudoers rule at
    /etc/sudoers.d/tinyassets-watchdog giving the user NOPASSWD ONLY
    for this exact command. Any other systemctl action is refused.
    """
    try:
        result = subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", "restart", unit],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return (False, "systemctl restart timeout (>60s)")
    except OSError as exc:
        return (False, f"systemctl invoke error: {exc}")
    if result.returncode == 0:
        return (True, "restarted")
    return (False, f"systemctl exit={result.returncode}: {result.stderr.strip()[:200]}")


def _iso_to_epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return _dt.datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


def watchdog_tick(
    *,
    canary_script: Path = DEFAULT_CANARY_SCRIPT,
    probe_url: str = DEFAULT_PROBE_URL,
    state_file: Path = DEFAULT_STATE_FILE,
    service_unit: str = DEFAULT_SERVICE_UNIT,
    threshold: int = DEFAULT_THRESHOLD,
    probe_timeout: float = 10.0,
    restart_fn=_restart_service,  # injection seam for tests
    probe_fn=None,  # injection seam for tests
    gh_issue_fn=_open_gh_issue,  # injection seam for tests
    min_restart_interval: float = MIN_RESTART_INTERVAL_SECONDS,
    dry_run: bool = False,
    alarm_log: Path = ALARM_LOG,
) -> dict:
    """Run one probe cycle. Return the post-tick state dict.

    When ``dry_run=True`` (or ``DRY_RUN=1`` env var), probes are still
    executed (read-only) but restarts + GH issues are suppressed.
    """
    if os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes"):
        dry_run = True

    state = _load_state(state_file)

    if probe_fn is None:
        green, probe_msg = _probe(canary_script, probe_url, probe_timeout)
    else:
        green, probe_msg = probe_fn()

    state["last_probe_ts"] = _now_iso()

    if green:
        if state["consecutive_reds"] > 0:
            _log("INFO", f"RECOVERED after {state['consecutive_reds']} red(s)")
        state["consecutive_reds"] = 0
        _save_state(state_file, state)
        return state

    state["consecutive_reds"] = int(state.get("consecutive_reds", 0)) + 1
    _log(
        "WARN",
        f"RED #{state['consecutive_reds']}/{threshold} — {probe_msg}",
    )

    if state["consecutive_reds"] < threshold:
        _save_state(state_file, state)
        return state

    # Threshold crossed. Restart — but rate-limit to avoid hot-loop.
    last_restart_epoch = _iso_to_epoch(state.get("last_restart_ts"))
    now_epoch = _dt.datetime.now(_dt.timezone.utc).timestamp()
    if last_restart_epoch and (now_epoch - last_restart_epoch) < min_restart_interval:
        wait = int(min_restart_interval - (now_epoch - last_restart_epoch))
        _log(
            "WARN",
            f"threshold crossed but last restart was <{int(min_restart_interval)}s ago; "
            f"waiting {wait}s before next restart attempt",
        )
        _save_state(state_file, state)
        return state

    if dry_run:
        _log(
            "INFO",
            f"DRY_RUN: would restart {service_unit} after "
            f"{state['consecutive_reds']} consecutive reds (suppressed)",
        )
        _save_state(state_file, state)
        return state

    _log(
        "ERROR",
        f"threshold crossed ({state['consecutive_reds']} consecutive reds); "
        f"restarting {service_unit}",
    )
    success, restart_msg = restart_fn(service_unit)
    state["last_restart_ts"] = _now_iso()
    if success:
        _log("INFO", f"restart issued: {restart_msg}")
        # Reset streak optimistically. Next probe validates recovery.
        state["consecutive_reds"] = 0
        # Append to shared alarm log so uptime_alarm.py + host sees it.
        alarm_line = (
            f"{_now_iso()} WATCHDOG_RESTART service={service_unit} "
            f"reds={threshold} probe_url={probe_url}"
        )
        _append_alarm_log(alarm_line, alarm_log)
        # Best-effort GH issue so ops gets an out-of-band alert.
        gh_ok, gh_msg = gh_issue_fn(
            f"[watchdog] daemon auto-restarted on {_now_iso()}",
            f"The watchdog on the self-hosted Droplet restarted `{service_unit}` "
            f"after {threshold} consecutive probe failures.\n\n"
            f"**Probe URL:** `{probe_url}`\n"
            f"**Last probe message:** {probe_msg}\n\n"
            f"Check `journalctl -u {service_unit}` for root cause.",
        )
        _log("INFO", f"GH issue: {gh_msg}" if gh_ok else f"GH issue skipped: {gh_msg}")
    else:
        _log("ERROR", f"restart FAILED: {restart_msg}")
        # Keep the streak — maybe next tick succeeds.

    _save_state(state_file, state)
    return state


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="TinyAssets daemon watchdog — one tick.")
    ap.add_argument("--probe-url", default=DEFAULT_PROBE_URL)
    ap.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    ap.add_argument("--service-unit", default=DEFAULT_SERVICE_UNIT)
    ap.add_argument("--canary-script", default=str(DEFAULT_CANARY_SCRIPT))
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    ap.add_argument("--probe-timeout", type=float, default=10.0)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Probe only; suppress restarts, alarm log, and GH issues.",
    )
    args = ap.parse_args(argv)

    try:
        watchdog_tick(
            canary_script=Path(args.canary_script),
            probe_url=args.probe_url,
            state_file=Path(args.state_file),
            service_unit=args.service_unit,
            threshold=args.threshold,
            probe_timeout=args.probe_timeout,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        _log("FATAL", f"watchdog tick crashed: {exc!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
