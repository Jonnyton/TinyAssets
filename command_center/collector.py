"""Collector — turns repo + provider signals into a village snapshot.

Data sources (all read-only, all best-effort):

- ``STATUS.md`` Work table          → claimed lanes (who said they're working)
- ``scripts/worktree_status.py``    → worktree islands (dirty = someone's hands in it)
- ``~/.claude/projects/**.jsonl``   → Claude Code sessions (main + subagent)
- ``~/.codex/sessions/**.jsonl``    → Codex CLI sessions
- ``~/.kimi-code/session_index*``   → Kimi CLI sessions (+ ``agents/`` subagents)
- ``.agents/activity.log`` + git    → the event feed
- universe data dirs (``u-*``)      → the sky archipelago (daemon-run universes)

Nothing here ever crashes the server: every probe degrades to "absent".
"""

from __future__ import annotations

import json
import os
import re
import secrets
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from . import parsers
from .mcp_client import McpClient

# ---------------------------------------------------------------------------
# Config

PROVIDERS = ("claude", "codex", "kimi", "cursor", "cowork", "gemini", "aider")

#: (zone id, dir prefix, emoji, label). Only zones whose dir exists are shown.
CORE_ZONES: list[tuple[str, str, str, str]] = [
    ("keep", "workflow", "🏰", "The Keep · engine"),
    ("api", "workflow/api", "⚙️", "API halls"),
    ("tests", "tests", "🧪", "Proving grounds"),
    ("docs", "docs", "📚", "Library"),
    ("scripts", "scripts", "🧰", "Workshop"),
    ("ideas", "ideas", "💡", "Idea garden"),
    ("agents", ".agents", "🏕️", "Agent camp"),
    ("web", "WebSite", "🌐", "Web quarter"),
    ("packaging", "packaging", "📦", "Packing house"),
    ("deploy", "deploy", "🚀", "Launch pad"),
    ("openspec", "openspec", "📜", "Charter hall"),
    ("knowledge", "knowledge", "🧠", "Brain loft"),
    ("domains", "domains", "🗺️", "Domain fields"),
    ("assets", "assets", "🎨", "Art loft"),
    ("square", "", "🏛️", "Village square"),
]

GENRE_EMOJI: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"castl|kingdom|fantasy|dragon|quest|magic", re.I), "🏰"),
    (re.compile(r"space|starship|planet|galax|alien", re.I), "🚀"),
    (re.compile(r"cook|recipe|kitchen|food", re.I), "🍳"),
    (re.compile(r"detect|mystery|noir|crime", re.I), "🕵️"),
    (re.compile(r"robot|cyber|AI\b|machine", re.I), "🤖"),
    (re.compile(r"pirate|sea|ocean|ship|voyage", re.I), "⛵"),
    (re.compile(r"garden|farm|forest|nature", re.I), "🌳"),
    (re.compile(r"research|paper|study|science", re.I), "🔬"),
]

ACTIVE_S = 5 * 60  # <5 min → actively working
RECENT_S = 30 * 60  # <30 min → recently seen
TRANSCRIPT_WINDOW_S = 2 * 3600  # transcripts older than this are ignored
_VILLAGE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
_COMMAND_CENTER_BEARERS = ("TINYASSETS_VILLAGE_TOKEN", "WORKFLOW_MCP_TOKEN")


class _DispatchCapacity:
    """Atomic process-wide reservation pool for paid peer process trees."""

    def __init__(self, limit: int = 8) -> None:
        self.limit = limit
        self._in_flight = 0
        self._lock = threading.Lock()

    def reserve(self, count: int) -> bool:
        with self._lock:
            if self._in_flight + count > self.limit:
                return False
            self._in_flight += count
            return True

    def release(self, count: int = 1) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - count)


_DISPATCH_CAPACITY = _DispatchCapacity()


class _PeerCleanupError(RuntimeError):
    """The provider process tree could not be proven stopped and reaped."""


@dataclass
class Config:
    root: Path
    host: str = "127.0.0.1"
    port: int = 8787
    token: str | None = None
    dispatch: bool = False
    interval: float = 3.0
    mcp_url: str | None = None
    directory_url: str | None = "https://tinyassets.io"
    mcp_token: str | None = None
    inbox_dir: Path | None = None
    claude_home: Path = field(default_factory=lambda: Path.home() / ".claude")
    codex_home: Path = field(default_factory=lambda: Path.home() / ".codex")
    kimi_home: Path = field(default_factory=lambda: Path.home() / ".kimi-code")
    data_dirs: list[Path] = field(default_factory=list)
    now: object = time.time  # injectable clock for tests

    def __post_init__(self) -> None:
        if self.host not in _LOOPBACK_HOSTS:
            raise ValueError("host must be literal 127.0.0.1 or ::1")
        if (
            isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 0 <= self.port <= 65535
        ):
            raise ValueError("port must be an integer from 0 through 65535")

        token = self.token
        if token is None:
            if "TINYASSETS_VILLAGE_TOKEN" in os.environ:
                token = os.environ["TINYASSETS_VILLAGE_TOKEN"]
            else:
                token = secrets.token_urlsafe(32)
        if not isinstance(token, str) or _VILLAGE_TOKEN_RE.fullmatch(token) is None:
            raise ValueError(
                "TINYASSETS_VILLAGE_TOKEN must contain 20-128 URL-safe characters"
            )
        self.token = token

    @classmethod
    def from_args(cls, args: object) -> "Config":
        root = Path.cwd()
        cfg = cls(
            root=root,
            host=args.host,
            port=args.port,
            dispatch=args.dispatch,
            interval=args.interval,
            mcp_url=args.mcp_url,
            directory_url=getattr(args, "directory_url", "https://tinyassets.io"),
            mcp_token=os.environ.get("WORKFLOW_MCP_TOKEN"),
        )
        cfg.inbox_dir = root / ".agents" / "village-inbox"
        cfg.data_dirs = default_data_dirs(root)
        return cfg


def default_data_dirs(root: Path) -> list[Path]:
    """Candidate roots that may contain ``u-*`` universe dirs."""
    candidates: list[Path] = []
    try:  # canonical resolver, but never hard-depend on the engine
        from workflow.storage import data_dir

        candidates.append(Path(data_dir()))
    except Exception:
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Workflow")
    candidates += [
        root.parent / "Workflow-live-data-snapshot",
        root / "Workflow-live-data-snapshot",
    ]
    seen: set[str] = set()
    out: list[Path] = []
    for cand in candidates:
        key = str(cand).lower()
        if key not in seen and cand.is_dir():
            seen.add(key)
            out.append(cand)
    return out


# ---------------------------------------------------------------------------
# Small probe helpers


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 20) -> str:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _peer_environment() -> dict[str, str]:
    env = os.environ.copy()
    for name in _COMMAND_CENTER_BEARERS:
        env.pop(name, None)
    return env


def _wait_for_process_group_exit(
    pgid: int,
    *,
    label: str,
    timeout: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        except OSError as exc:
            raise _PeerCleanupError(
                f"{label} process group {pgid} could not be verified stopped: {exc}"
            ) from exc
        if time.monotonic() >= deadline:
            raise _PeerCleanupError(
                f"{label} process group {pgid} still exists after cleanup"
            )
        time.sleep(0.01)


def _provider_pgid(identity_path: Path, *, wrapper_pid: int) -> int:
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _PeerCleanupError(
            f"provider process identity could not be read for wrapper {wrapper_pid}: {exc}"
        ) from exc
    if (
        not isinstance(identity, dict)
        or type(identity.get("wrapper_pid")) is not int
        or identity["wrapper_pid"] != wrapper_pid
        or type(identity.get("provider_pgid")) is not int
        or identity["provider_pgid"] <= 0
        or identity["provider_pgid"] == wrapper_pid
    ):
        raise _PeerCleanupError(
            f"provider process identity is invalid for wrapper {wrapper_pid}"
        )
    return identity["provider_pgid"]


def _kill_peer_tree(
    proc: subprocess.Popen[bytes],
    provider_pgid_file: Path | None = None,
) -> None:
    cleanup_errors: list[_PeerCleanupError] = []
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            cleanup_errors.append(_PeerCleanupError(
                f"taskkill failed for peer process tree {proc.pid}: {exc}"
            ))
        else:
            if result.returncode != 0:
                cleanup_errors.append(_PeerCleanupError(
                    f"taskkill failed for peer process tree {proc.pid} "
                    f"with exit code {result.returncode}"
                ))
    else:
        try:
            os.killpg(proc.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except ProcessLookupError:
            pass
        except OSError as exc:
            cleanup_errors.append(_PeerCleanupError(
                f"process-group cleanup failed for peer {proc.pid}: {exc}"
            ))
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            try:
                proc.kill()
            except OSError as kill_exc:
                cleanup_errors.append(_PeerCleanupError(
                    f"peer wrapper {proc.pid} fallback kill failure: {kill_exc}"
                ))
            cleanup_errors.append(_PeerCleanupError(
                f"peer wrapper {proc.pid} did not exit after process-tree cleanup"
            ))
        else:
            cleanup_errors.append(_PeerCleanupError(
                f"peer wrapper {proc.pid} did not exit after process-tree cleanup"
            ))
    except OSError as exc:
        cleanup_errors.append(_PeerCleanupError(
            f"peer wrapper {proc.pid} could not be reaped: {exc}"
        ))
    if os.name != "nt":
        try:
            _wait_for_process_group_exit(proc.pid, label="peer wrapper")
        except _PeerCleanupError as exc:
            cleanup_errors.append(exc)
        if provider_pgid_file is not None:
            try:
                provider_group = _provider_pgid(
                    provider_pgid_file,
                    wrapper_pid=proc.pid,
                )
            except _PeerCleanupError as exc:
                cleanup_errors.append(exc)
            else:
                try:
                    os.killpg(
                        provider_group,
                        getattr(signal, "SIGKILL", signal.SIGTERM),
                    )
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    cleanup_errors.append(_PeerCleanupError(
                        f"provider process-group cleanup failed for "
                        f"{provider_group}: {exc}"
                    ))
                try:
                    _wait_for_process_group_exit(
                        provider_group,
                        label="provider",
                    )
                except _PeerCleanupError as exc:
                    cleanup_errors.append(exc)
    if cleanup_errors:
        raise _PeerCleanupError("; ".join(str(error) for error in cleanup_errors))


def _run_peer(
    cmd: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: dict[str, str],
) -> str:
    """Run the peer wrapper and reap its process tree before returning."""

    kwargs: dict[str, object] = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        kwargs["start_new_session"] = True
    provider_pgid_file: Path | None = None
    try:
        identity_index = cmd.index("--provider-pgid-file")
    except ValueError:
        pass
    else:
        if identity_index + 1 < len(cmd):
            provider_pgid_file = Path(cmd[identity_index + 1])
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            **kwargs,
        )
    except OSError:
        return ""
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_peer_tree(proc, provider_pgid_file)
        try:
            proc.communicate()
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise _PeerCleanupError(
                f"peer wrapper {proc.pid} pipes could not be reaped after cleanup: {exc}"
            ) from exc
        return ""
    except OSError:
        _kill_peer_tree(proc, provider_pgid_file)
        raise
    if proc.returncode == 125:
        raise _PeerCleanupError("peer wrapper reported unverified process-tree cleanup")
    return stdout.decode("utf-8", errors="replace")


def _new_dispatch_artifact(anchor: Path, *, label: str) -> Path:
    anchor.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{anchor.stem}.{label}-",
        suffix=".tmp",
        dir=anchor.parent,
    )
    os.close(fd)
    path = Path(name)
    path.unlink()
    return path


def _remove_dispatch_artifact(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _age_label(ts: float | None, now: float) -> str:
    if not ts:
        return "unknown"
    delta = max(0, int(now - ts))
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _liveness(ts: float | None, now: float) -> str:
    if ts is None:
        return "claimed"
    age = now - ts
    if age < ACTIVE_S:
        return "active"
    if age < RECENT_S:
        return "recent"
    return "idle"


def _newest_mtime(path: Path) -> float | None:
    """Newest mtime anywhere under ``path`` (shallow, capped)."""
    newest: float | None = None
    try:
        if path.is_file():
            return path.stat().st_mtime
        count = 0
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in parsers._DIR_PRUNE]
            for name in filenames:
                count += 1
                if count > 500:
                    return newest
                try:
                    mtime = (Path(dirpath) / name).stat().st_mtime
                except OSError:
                    continue
                newest = max(newest or 0.0, mtime)
    except OSError:
        return None
    return newest


class _Throttle:
    """Run expensive probes at most every ``period`` seconds; cache result."""

    def __init__(self, period: float) -> None:
        self.period = period
        self._at = 0.0
        self._value: object = None

    def call(self, fn, *args):
        now = time.monotonic()
        if now - self._at >= self.period:
            self._at = now
            self._value = fn(*args)
        return self._value


# ---------------------------------------------------------------------------
# Zones


def discover_zones(cfg: Config, worktrees: list[dict], recent_files: list[tuple[str, float]],
                   now: float) -> list[dict]:
    zones: list[dict] = []
    heat: dict[str, int] = {}
    for relpath, mtime in recent_files:
        if now - mtime < 15 * 60:
            zone_dirs = {zid: prefix for zid, prefix, _, _ in CORE_ZONES}
            heat[parsers.zone_for_relpath(relpath, zone_dirs)] = heat.get(
                parsers.zone_for_relpath(relpath, zone_dirs), 0
            ) + 1
    for zid, prefix, emoji, label in CORE_ZONES:
        if prefix and not (cfg.root / prefix).is_dir():
            continue
        zones.append(
            {
                "id": zid,
                "kind": "core",
                "prefix": prefix,
                "emoji": emoji,
                "label": label,
                "heat": heat.get(zid, 0),
            }
        )
    for lane in worktrees:
        zones.append(
            {
                "id": f"wt-{lane['slug']}",
                "kind": "island",
                "prefix": "",
                "emoji": "🏝️",
                "label": lane["slug"],
                "heat": 5 if lane.get("dirty") else 0,
                "branch": lane.get("branch"),
                "dirty": lane.get("dirty", False),
                "stale": (lane.get("age_hours") or 0) > 24 and lane.get("dirty"),
                "path": lane.get("path", ""),
            }
        )
    return zones


def _worktree_lanes(cfg: Config) -> list[dict]:
    """Active-ish lanes from scripts/worktree_status.py --json."""
    script = cfg.root / "scripts" / "worktree_status.py"
    if not script.is_file():
        return []
    out = _run(["python", str(script), "--json"], cwd=cfg.root, timeout=30)
    try:
        lanes = json.loads(out)
    except ValueError:
        return []
    if not isinstance(lanes, list):
        return []
    keep: list[dict] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        state = str(lane.get("state") or "")
        path = str(lane.get("path") or "")
        if state == "MISSING" or not path or not Path(path).is_dir():
            continue
        if lane.get("current"):
            continue  # the main checkout is the village itself, not an island
        if lane.get("dirty") or "ACTIVE" in state or "IN_FLIGHT" in state:
            keep.append(lane)
    return keep[:12]


def scan_recent_files(
    cfg: Config, window_s: float = 6 * 3600, limit: int = 300
) -> list[tuple[str, float]]:
    """(repo-relative path, mtime) for files touched in ``window_s``."""
    cutoff = time.time() - window_s
    found: list[tuple[str, float]] = []
    for dirpath, dirnames, filenames in os.walk(cfg.root):
        dirnames[:] = [d for d in dirnames if d not in parsers._DIR_PRUNE]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                mtime = full.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                rel = full.relative_to(cfg.root).as_posix()
                found.append((rel, mtime))
                if len(found) >= limit:
                    return sorted(found, key=lambda item: -item[1])
    return sorted(found, key=lambda item: -item[1])


# ---------------------------------------------------------------------------
# Agents


def _path_in_scope(path: str | None, cfg: Config, lane_paths: list[str]) -> bool:
    if not path:
        return False
    norm = str(path).replace("\\", "/").lower()
    root = str(cfg.root).replace("\\", "/").lower()
    if norm.startswith(root):
        return True
    return any(norm.startswith(lp.lower().replace("\\", "/")) for lp in lane_paths)


def _zone_of_file(file_path: str | None, cwd: str | None, cfg: Config,
                  zone_dirs: dict[str, str], lane_by_path: dict[str, str]) -> str:
    """Pick the zone an agent stands in from the file it touched (or its cwd)."""
    for candidate in (file_path, cwd):
        if not candidate:
            continue
        norm = str(candidate).replace("\\", "/")
        for lane_path, lane_zone in lane_by_path.items():
            if norm.lower().startswith(lane_path.lower()):
                return lane_zone
        rel = parsers.norm_rel(norm, cfg.root)
        if rel:
            return parsers.zone_for_relpath(rel, zone_dirs)
    return "square"


def _provider_from_branch(branch: str | None) -> str | None:
    if not branch:
        return None
    head = branch.split("/", 1)[0].lower()
    return head if head in PROVIDERS else None


def _kimi_state(sdir: Path) -> dict:
    """Read a Kimi session's state.json (title + subagent registry)."""
    try:
        state = json.loads((sdir / "state.json").read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def detect_agents(cfg: Config, worktrees: list[dict], zones: list[dict], now: float) -> list[dict]:
    agents: list[dict] = []
    zone_dirs = {z["id"]: z.get("prefix", "") for z in zones if z["kind"] == "core"}
    lane_by_path = {
        str(lane["path"]).replace("\\", "/"): f"wt-{lane['slug']}"
        for lane in worktrees
        if lane.get("path")
    }
    lane_paths = list(lane_by_path)
    cutoff = now - TRANSCRIPT_WINDOW_S

    def add_agent(**kw) -> None:
        agents.append(kw)

    # -- Claude Code -----------------------------------------------------
    projects = cfg.claude_home / "projects"
    if projects.is_dir():
        try:
            transcripts = sorted(
                projects.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
            )
        except OSError:
            transcripts = []
        for path in transcripts[:40]:
            try:
                if path.stat().st_mtime < cutoff:
                    break  # sorted desc; rest are older
            except OSError:
                continue
            info = parsers.parse_claude_transcript(
                parsers.head_jsonl(path) + parsers.tail_jsonl(path)
            )
            if not _path_in_scope(info.get("cwd"), cfg, lane_paths):
                continue
            sid = str(info.get("session_id") or path.stem)[:8]
            kind = "subagent" if path.stem.startswith("agent-") else "main"
            label = parsers.make_label(info.get("first_prompt"))
            add_agent(
                id=f"claude-{sid}",
                name=label or f"Claude·{sid}",
                label=label,
                provider="claude",
                kind=kind,
                action=info.get("action") or "thinking",
                file=info.get("file"),
                zone=_zone_of_file(info.get("file"), info.get("cwd"), cfg, zone_dirs, lane_by_path),
                ts=info.get("ts"),
                model=info.get("model"),
                task=info.get("last_prompt"),
                branch=info.get("branch"),
                serial=sid,
            )
            if info.get("sidechain") and kind == "main":
                add_agent(
                    id=f"claude-{sid}-task",
                    name=f"↳ {label}" if label else f"Claude·{sid}·task",
                    label=f"↳ {label}" if label else "",
                    provider="claude",
                    kind="subagent",
                    action="running a delegated task",
                    file=info.get("file"),
                    zone=_zone_of_file(
                        info.get("file"), info.get("cwd"), cfg, zone_dirs, lane_by_path
                    ),
                    ts=info.get("ts"),
                    model=info.get("model"),
                    parent=f"claude-{sid}",
                    branch=info.get("branch"),
                    serial=f"{sid}·task",
                )

    # -- Codex CLI -------------------------------------------------------
    sessions_root = cfg.codex_home / "sessions"
    if sessions_root.is_dir():
        try:
            rollouts = sorted(
                sessions_root.glob("**/rollout-*.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            rollouts = []
        for path in rollouts[:25]:
            try:
                if path.stat().st_mtime < cutoff:
                    break
            except OSError:
                continue
            info = parsers.parse_codex_rollout(
                parsers.head_jsonl(path) + parsers.tail_jsonl(path)
            )
            if not _path_in_scope(info.get("cwd"), cfg, lane_paths):
                continue
            sid = str(info.get("session_id") or path.stem)[-8:]
            label = parsers.make_label(info.get("first_prompt") or info.get("last_prompt"))
            add_agent(
                id=f"codex-{sid}",
                name=label or f"Codex·{sid}",
                label=label,
                provider="codex",
                kind="main",
                action=info.get("action") or "thinking",
                file=info.get("file"),
                zone=_zone_of_file(info.get("file"), info.get("cwd"), cfg, zone_dirs, lane_by_path),
                ts=info.get("ts"),
                task=info.get("last_prompt"),
                branch=info.get("branch"),
                serial=sid,
            )

    # -- Kimi CLI --------------------------------------------------------
    index = cfg.kimi_home / "session_index.jsonl"
    if index.is_file():
        try:
            lines = index.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        sessions = []
        for line in lines:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            sdir = Path(obj.get("sessionDir") or "")
            if not sdir.is_dir():
                continue
            if not _path_in_scope(obj.get("workDir"), cfg, lane_paths):
                continue
            mtime = _newest_mtime(sdir)
            if mtime is None or mtime < cutoff:
                continue
            sessions.append((mtime, obj, sdir))
        for mtime, obj, sdir in sorted(sessions, key=lambda s: -s[0])[:10]:
            sid = str(obj.get("sessionId") or sdir.name).replace("session_", "")[:8]
            workdir = str(obj.get("workDir") or "")
            state = _kimi_state(sdir)
            label = parsers.make_label(state.get("title"))
            add_agent(
                id=f"kimi-{sid}",
                name=label or f"Kimi·{sid}",
                label=label,
                provider="kimi",
                kind="main",
                action="working in its session",
                file=None,
                zone=_zone_of_file(None, workdir, cfg, zone_dirs, lane_by_path),
                ts=mtime,
                branch=None,
                serial=sid,
                task=state.get("title"),
            )
            agents_map = state.get("agents") if isinstance(state.get("agents"), dict) else {}
            sub_names = [k for k in agents_map if k != "main"]
            if sub_names:
                for sub_name in sorted(sub_names)[:6]:
                    homedir = agents_map[sub_name].get("homedir")
                    sub_dir = Path(homedir) if homedir else sdir / "agents" / sub_name
                    sub_mtime = _newest_mtime(sub_dir) or mtime
                    if sub_mtime < cutoff:
                        continue
                    sub_id = sub_name.replace("agent-", "")[:8]
                    add_agent(
                        id=f"kimi-{sid}-{sub_id}",
                        name=f"↳ {label}" if label else f"Kimi·{sid}·{sub_id}",
                        label=f"↳ {label}" if label else "",
                        provider="kimi",
                        kind="subagent",
                        action="assisting the main session",
                        file=None,
                        zone=_zone_of_file(None, workdir, cfg, zone_dirs, lane_by_path),
                        ts=sub_mtime,
                        parent=f"kimi-{sid}",
                        serial=f"{sid}·{sub_id}",
                    )
            else:
                sub_root = sdir / "agents"
                if sub_root.is_dir():
                    try:
                        subs = sorted(
                            sub_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
                        )
                    except OSError:
                        subs = []
                    for sub in subs[:4]:
                        if sub.name == "main":
                            continue
                        try:
                            sub_mtime = _newest_mtime(sub) or sub.stat().st_mtime
                        except OSError:
                            continue
                        if sub_mtime < cutoff:
                            continue
                        sub_id = sub.name.replace("agent-", "")[:8]
                        add_agent(
                            id=f"kimi-{sid}-{sub_id}",
                            name=f"↳ {label}" if label else f"Kimi·{sid}·{sub_id}",
                            label=f"↳ {label}" if label else "",
                            provider="kimi",
                            kind="subagent",
                            action="assisting the main session",
                            file=None,
                            zone=_zone_of_file(None, workdir, cfg, zone_dirs, lane_by_path),
                            ts=sub_mtime,
                            parent=f"kimi-{sid}",
                            serial=f"{sid}·{sub_id}",
                        )

    # -- STATUS.md claims ------------------------------------------------
    status_path = cfg.root / "STATUS.md"
    claims: list[dict] = []
    if status_path.is_file():
        try:
            claims = parsers.parse_status_claims(status_path.read_text(encoding="utf-8"))
        except OSError:
            claims = []
    live_providers = {a["provider"] for a in agents}
    for claim in claims:
        provider = (claim.get("provider") or "").lower()
        base = provider.split("-")[0]
        if base in live_providers and claim.get("active"):
            for agent in agents:  # enrich the live agent with its claim
                if agent["provider"] == base and not agent.get("claim"):
                    agent["claim"] = claim["task"]
            continue
        first_file = next(
            (
                f
                for f in claim.get("files", [])
                if (not f.endswith("/") and "/" in f) or f.endswith(".py")
            ),
            claim.get("files", [""])[0] if claim.get("files") else "",
        )
        label = parsers.make_label(claim["task"], max_len=40)
        add_agent(
            id=f"claim-{parsers.slugify(provider or 'unknown')}",
            name=label or (provider or "unknown").replace("-", "·"),
            label=label,
            provider=base if base in PROVIDERS else "unknown",
            kind="main",
            action=f"claimed: {claim['task']}",
            file=first_file or None,
            zone=parsers.zone_for_relpath(first_file, zone_dirs) if first_file else "square",
            ts=None,
            claim=claim["task"],
        )

    # -- finalize --------------------------------------------------------
    for agent in agents:
        agent["status"] = _liveness(agent.get("ts"), now)
        agent["seen"] = _age_label(agent.get("ts"), now)
        if agent.get("parent"):
            continue
    agents.sort(key=lambda a: (a["kind"] != "main", -(a.get("ts") or 0)))
    return agents[:40]


# ---------------------------------------------------------------------------
# Universes — the sky archipelago


def _strip_frontmatter(text: str) -> str:
    """Drop the leading --- fenced YAML block (OKF bundles), keep the body."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4 :].lstrip("\r\n")


def _universe_name(udir: Path, data_root: Path | None = None) -> str:
    # 1. the root Universe Index projects learned names for browsing
    if data_root is not None:
        index = data_root / "universes.md"
        if index.is_file():
            try:
                for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
                    if udir.name not in line or "|" not in line:
                        continue
                    cells = [c.strip().strip("`") for c in line.split("|")]
                    # rows look like: | `u-…` | Learned name | status | … |
                    if len(cells) < 4:
                        continue
                    learned = cells[2]
                    normalized = learned.lower().replace("-", " ").replace("_", " ")
                    if learned and "not learned" not in normalized and udir.name not in learned:
                        return learned[:40]
            except OSError:
                pass
    # 2. the universe's own identity file (body, not frontmatter)
    identity = udir / "identity.md"
    if identity.is_file():
        try:
            body = _strip_frontmatter(identity.read_text(encoding="utf-8", errors="replace"))
            for line in body.splitlines():
                text = line.strip().lstrip("#").strip()
                m = re.match(r"(?:learned\s+)?name\s*[:=]\s*(.+)", text, re.I)
                if m and "not learned" not in m.group(1).lower():
                    return m.group(1).strip()[:40]
        except OSError:
            pass
    # 3. honest placeholder — per the personification spec, never invent a name
    return f"unnamed mind · {udir.name.replace('u-', '')[:8]}"


def _universe_premise(udir: Path) -> str:
    for name in ("soul.md", "founder.md", "origin.md"):
        path = udir / name
        if not path.is_file():
            continue
        try:
            text = _strip_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for para in re.split(r"\n\s*\n", text):
            para = para.strip().lstrip("#").strip()
            if len(para) > 30:
                return re.sub(r"\s+", " ", para)[:160]
    return ""


def _universe_words(udir: Path) -> tuple[int, int]:
    """(chapter files, total words) under output/ — capped and cheap."""
    out = udir / "output"
    if not out.is_dir():
        return 0, 0
    files, words = 0, 0
    try:
        for path in sorted(out.rglob("*.md"))[:60]:
            files += 1
            try:
                words += len(path.read_text(encoding="utf-8", errors="replace").split())
            except OSError:
                continue
    except OSError:
        pass
    return files, words


def _universe_preset(udir: Path) -> str:
    """Provider preset from <universe>/config.yaml (tiny YAML-subset read)."""
    path = udir / "config.yaml"
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    found: dict[str, str] = {}
    for line in lines:
        m = re.match(
            r"^(preferred_writer|preferred_judge|allowed_providers)\s*:\s*(.+)$", line.strip()
        )
        if m:
            found[m.group(1)] = m.group(2).strip().strip("\"'")
    writer = found.get("preferred_writer", "")
    judge = found.get("preferred_judge", "")
    if writer and judge and writer != judge:
        return f"{writer} / {judge}"
    return writer or judge or found.get("allowed_providers", "")


def discover_universes(cfg: Config, now: float) -> list[dict]:
    universes: list[dict] = []
    seen: set[str] = set()
    for data_root in cfg.data_dirs:
        try:
            children = sorted(data_root.iterdir())
        except OSError:
            continue
        for udir in children:
            if not udir.is_dir() or not udir.name.startswith("u-"):
                continue
            key = udir.name.lower()
            if key in seen:
                continue
            seen.add(key)
            premise = _universe_premise(udir)
            emoji = next((e for pat, e in GENRE_EMOJI if pat.search(premise)), "☁️")
            newest = _newest_mtime(udir)
            chapters, words = _universe_words(udir)
            last_line = ""
            for log_name in ("activity.log", "log.md"):
                log_path = udir / log_name
                if log_path.is_file():
                    try:
                        lines = [
                            ln.strip()
                            for ln in log_path.read_text(
                                encoding="utf-8", errors="replace"
                            ).splitlines()
                            if ln.strip()
                        ]
                        last_line = (lines[-1][:140] if lines else "")
                    except OSError:
                        pass
                    if last_line:
                        break
            live = newest is not None and (now - newest) < RECENT_S
            universes.append(
                {
                    "id": udir.name,
                    "name": _universe_name(udir, data_root),
                    "emoji": emoji,
                    "premise": premise,
                    "preset": _universe_preset(udir),
                    "path": str(udir),
                    "words": words,
                    "chapters": chapters,
                    "ts": newest,
                    "seen": _age_label(newest, now),
                    "status": "alive" if live else "dormant",
                    "last_activity": last_line,
                    "source": "local",
                }
            )
    universes.sort(key=lambda u: -(u.get("ts") or 0))
    # live platform universes ride the sky too (deduped against local dirs)
    local_ids = {u["id"] for u in universes}
    for live in platform_snapshot().get("universes", []):
        if live["id"] not in local_ids:
            universes.append(live)
    return universes[:24]


def _platform_url(cfg: Config) -> str | None:
    if cfg.mcp_url:
        return cfg.mcp_url
    if cfg.directory_url:
        return cfg.directory_url.rstrip("/") + "/mcp"
    return None


def _live_universe(entry: dict) -> dict | None:
    """Map a read_graph target=graphs entry to a village universe record."""
    uid = str(entry.get("id") or entry.get("universe_id") or "")
    if not uid:
        return None
    if uid.startswith("u-") and len(uid) > 12:
        pretty = f"unnamed mind · {uid[2:10]}"  # ULID serials are not names
    else:
        pretty = uid.replace("-", " ").replace("_", " ").strip().title()
    phase = str(entry.get("phase_human") or entry.get("phase") or "")
    staleness = str(entry.get("staleness") or "")
    ts = parsers.iso_to_epoch(entry.get("last_activity_at"))
    words = entry.get("word_count") or 0
    emoji = next((e for pat, e in GENRE_EMOJI if pat.search(uid)), "☁️")
    brief = {
        "phase": phase or None,
        "words": words or None,
        "accept_rate": entry.get("accept_rate"),
    }
    return {
        "id": uid,
        "name": pretty,
        "emoji": emoji,
        "premise": phase,
        "preset": "",
        "path": "",
        "words": words,
        "chapters": 0,
        "ts": ts,
        "seen": "",
        "status": "alive" if staleness == "fresh" else "dormant",
        "staleness": staleness,
        "last_activity": phase,
        "accept_rate": entry.get("accept_rate"),
        "source": "live",
        "brief": {k: v for k, v in brief.items() if v is not None},
    }


def platform_state(cfg: Config) -> dict:
    """Live platform snapshot via the 5-handle MCP surface.

    Reads: ``read_graph target=graphs`` (universes), ``read_page`` (commons
    pulse), ``get_status`` (platform persona). Anonymous reads are open;
    writes (converse/write_*) need OAuth — chat degrades honestly.
    """
    empty = {"reachable": False, "universes": [], "market": {}, "commons": [], "status": {}}
    url = _platform_url(cfg)
    if not url:
        return empty
    client = McpClient(url, token=cfg.mcp_token)
    raw_list = client.call_tool("read_graph", {"target": "graphs"})
    if raw_list is None:
        return empty
    entries = raw_list.get("universes") if isinstance(raw_list, dict) else raw_list
    if not isinstance(entries, list):
        entries = []
    now = time.time()
    universes: list[dict] = []
    for entry in entries[:14]:
        if not isinstance(entry, dict):
            continue
        universe = _live_universe(entry)
        if not universe:
            continue
        if universe["ts"]:
            universe["seen"] = _age_label(universe["ts"], now)
        else:
            universe["seen"] = ""
        universes.append(universe)
    universes.sort(key=lambda u: -(u.get("ts") or 0))
    # per-universe daemon detail for the freshest few (accept rate, pause state)
    for universe in universes[:6]:
        detail = client.call_tool(
            "read_graph", {"target": "graph", "graph_id": universe["id"]}
        )
        daemon = (detail or {}).get("daemon") if isinstance(detail, dict) else None
        if isinstance(daemon, dict):
            universe["brief"]["paused"] = daemon.get("is_paused")
            if daemon.get("accept_rate") is not None:
                universe["accept_rate"] = daemon["accept_rate"]
                universe["brief"]["accept_rate"] = daemon["accept_rate"]
    # commons pulse — the shared public knowledge space
    commons: list[dict] = []
    raw_pages = client.call_tool("read_page", {"query": "commons"})
    if isinstance(raw_pages, dict) and isinstance(raw_pages.get("results"), list):
        for page in raw_pages["results"][:12]:
            if not isinstance(page, dict):
                continue
            title = str(page.get("title") or page.get("path") or "")[:90]
            path = str(page.get("path") or "")
            if title:
                commons.append({"name": title, "path": path})
    status = client.call_tool("get_status", {})
    return {
        "reachable": True,
        "universes": universes,
        "market": {},
        "commons": commons,
        "branches": [],
        "status": status if isinstance(status, dict) else {},
        "fetched_at": now,
    }


# Platform fetch runs on its own slow thread — network never stalls the
# 3-second village poller.
_PLATFORM: dict = {
    "reachable": False,
    "universes": [],
    "market": {},
    "commons": [],
    "branches": [],
    "status": {},
}
_PLATFORM_LOCK = threading.Lock()
_PLATFORM_STARTED = False


def platform_snapshot() -> dict:
    with _PLATFORM_LOCK:
        return {k: (list(v) if isinstance(v, list) else v) for k, v in _PLATFORM.items()}


def ensure_platform_worker(cfg: Config) -> None:
    global _PLATFORM_STARTED
    with _PLATFORM_LOCK:
        if _PLATFORM_STARTED:
            return
        _PLATFORM_STARTED = True
    if not _platform_url(cfg):
        return

    def loop() -> None:
        while True:
            try:
                result = platform_state(cfg)
                with _PLATFORM_LOCK:
                    _PLATFORM.clear()
                    _PLATFORM.update(result)
            except Exception as exc:  # never kill the thread
                print(f"[village] platform probe failed: {exc!r}", flush=True)
            time.sleep(60)

    threading.Thread(target=loop, name="village-platform", daemon=True).start()


# ---------------------------------------------------------------------------
# Events


class History:
    """Rolling event feed: seeded from logs, grown by observing diffs."""

    def __init__(self, maxlen: int = 400) -> None:
        self.events: deque[dict] = deque(maxlen=maxlen)
        self._seq = 0
        self._agent_ids: set[str] = set()
        self._lane_heads: dict[str, str] = {}
        self._claim_keys: set[str] = set()
        self._seen_files: dict[str, float] = {}
        self._seeded = False

    def _add(self, ts: float, actor: str, kind: str, text: str, zone: str = "") -> None:
        self._seq += 1
        self.events.append(
            {"id": self._seq, "ts": ts, "actor": actor, "kind": kind, "text": text, "zone": zone}
        )

    def seed(self, cfg: Config, worktrees: list[dict], now: float) -> None:
        if self._seeded:
            return
        self._seeded = True
        log_path = cfg.root / ".agents" / "activity.log"
        if log_path.is_file():
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-20000:]
            except OSError:
                tail = ""
            for ev in parsers.parse_activity_log(tail, limit=25):
                self._add(ev.get("ts") or now, ev["actor"], ev["kind"], ev["text"])
        for lane_root, actor in [
            (cfg.root, "village"),
            *[
                (Path(lane["path"]), lane.get("branch") or lane["slug"])
                for lane in worktrees
                if lane.get("path")
            ],
        ]:
            out = _run(
                ["git", "log", "--since=48.hours", "--format=%ct|%an|%s", "-n", "12"],
                cwd=lane_root,
            )
            for line in out.splitlines():
                parts = line.split("|", 2)
                if len(parts) != 3:
                    continue
                try:
                    ts = float(parts[0])
                except ValueError:
                    continue
                self._add(ts, parts[1].strip() or actor, "commit", parts[2].strip()[:140])
        self._sort()

    def observe(self, cfg: Config, snapshot_agents: list[dict], worktrees: list[dict],
                recent_files: list[tuple[str, float]], now: float) -> None:
        # arrivals / departures
        current = {a["id"]: a for a in snapshot_agents}
        for aid, agent in current.items():
            if aid not in self._agent_ids:
                self._add(now, agent["name"], "arrive",
                          f"{agent['name']} walked into the village — {agent['action']}",
                          agent.get("zone", ""))
        for aid in self._agent_ids - set(current):
            self._add(now, aid, "leave", f"{aid} left the village")
        self._agent_ids = set(current)

        # claims diff
        claims = set()
        status_path = cfg.root / "STATUS.md"
        if status_path.is_file():
            try:
                for claim in parsers.parse_status_claims(status_path.read_text(encoding="utf-8")):
                    claims.add((claim["provider"], claim["task"][:60]))
            except OSError:
                pass
        for provider, task in claims - self._claim_keys:
            if self._claim_keys:  # skip the initial seed burst
                self._add(now, provider or "someone", "claim", f"{provider} claimed: {task}")
        self._claim_keys = claims

        # fresh commits per lane (compare HEADs between polls)
        for lane in [{"path": str(cfg.root), "slug": "village", "branch": "main"}, *worktrees]:
            path = lane.get("path")
            if not path or not Path(path).is_dir():
                continue
            head = _run(["git", "log", "-1", "--format=%H|%ct|%an|%s"], cwd=Path(path))
            parts = head.strip().split("|", 3)
            if len(parts) != 4:
                continue
            sha, ts_s, author, subject = parts
            prev = self._lane_heads.get(str(path))
            self._lane_heads[str(path)] = sha
            if prev and prev != sha:
                try:
                    ts = float(ts_s)
                except ValueError:
                    ts = now
                self._add(ts, author.strip(), "commit",
                          f"{subject.strip()[:120]} ({lane.get('slug', 'lane')})")

        # fresh file writes, attributed to the freshest agent in that zone
        zone_dirs = {zid: prefix for zid, prefix, _, _ in CORE_ZONES}
        by_zone: dict[str, dict] = {}
        for agent in snapshot_agents:
            zone = agent.get("zone", "")
            if not zone:
                continue
            if zone not in by_zone or (agent.get("ts") or 0) > (by_zone[zone].get("ts") or 0):
                by_zone[zone] = agent
        for relpath, mtime in recent_files[:60]:
            prev = self._seen_files.get(relpath)
            self._seen_files[relpath] = mtime
            if prev is None or mtime <= prev:
                continue
            if relpath.startswith(".agents/village-inbox/"):
                continue  # our own talk channel is not village news
            zone = parsers.zone_for_relpath(relpath, zone_dirs)
            actor = by_zone.get(zone, {}).get("name", "someone")
            self._add(mtime, actor, "edit", f"{actor} touched `{relpath}`", zone)
        if len(self._seen_files) > 5000:
            self._seen_files = dict(list(self._seen_files.items())[-2500:])
        self._sort()

    def _sort(self) -> None:
        items = sorted(self.events, key=lambda e: (e.get("ts") or 0, e.get("id") or 0))
        self.events = deque(items, maxlen=self.events.maxlen)


# ---------------------------------------------------------------------------
# Snapshot assembly (module-level state so diffs survive between polls)

_HISTORY = History()
_THROTTLES = {"worktrees": _Throttle(15.0), "commits_seed": _Throttle(30.0)}


def snapshot(cfg: Config) -> dict:
    now = float(cfg.now() if callable(cfg.now) else time.time())
    ensure_platform_worker(cfg)
    worktrees = _THROTTLES["worktrees"].call(_worktree_lanes, cfg) or []
    recent_files = scan_recent_files(cfg)
    zones = discover_zones(cfg, worktrees, recent_files, now)
    agents = detect_agents(cfg, worktrees, zones, now)
    universes = discover_universes(cfg, now)
    _HISTORY.seed(cfg, worktrees, now)
    _HISTORY.observe(cfg, agents, worktrees, recent_files, now)
    events = list(_HISTORY.events)[-120:]
    edits_1h = sum(1 for _, mtime in recent_files if now - mtime < 3600)
    commits_24h = sum(
        1 for e in events if e["kind"] == "commit" and now - (e.get("ts") or 0) < 86400
    )
    hottest = max((z for z in zones if z["kind"] == "core"), key=lambda z: z["heat"], default=None)
    hour = time.localtime(now).tm_hour
    day_phase = "night" if hour < 6 or hour >= 21 else "sunset" if hour >= 17 else "day"
    return {
        "generated_at": now,
        "repo": cfg.root.name,
        "day_phase": day_phase,
        "zones": zones,
        "agents": agents,
        "universes": universes,
        "world": platform_snapshot(),
        "events": events,
        "stats": {
            "agents_active": sum(1 for a in agents if a["status"] == "active"),
            "agents_total": len(agents),
            "subagents": sum(1 for a in agents if a["kind"] == "subagent"),
            "edits_1h": edits_1h,
            "commits_24h": commits_24h,
            "hottest_zone": hottest["label"] if hottest and hottest["heat"] else None,
            "universes_alive": sum(1 for u in universes if u["status"] == "alive"),
            "universes_total": len(universes),
        },
    }


# ---------------------------------------------------------------------------
# Talk + chat


def _agent_by_id(cfg: Config, agent_id: str) -> dict | None:
    now = time.time()
    worktrees = _worktree_lanes(cfg)
    zones = discover_zones(cfg, worktrees, [], now)
    for agent in detect_agents(cfg, worktrees, zones, now):
        if agent["id"] == agent_id:
            return agent
    return None


def talk(cfg: Config, target: str, message: str) -> dict:
    """Deliver a host message to an agent (inbox file) or universe (note)."""
    if ":" not in target:
        return {"ok": False, "error": "target must be agent:<id> or universe:<id>"}
    kind, ident = target.split(":", 1)
    if kind == "agent":
        return _talk_to_agent(cfg, ident, message)
    if kind == "universe":
        return _talk_to_universe(cfg, ident, message)
    return {"ok": False, "error": f"unknown target kind {kind!r}"}


def _append_inbox(path: Path, who: str, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {stamp} — {who}\n\n{text}\n")


def _inbox_path(cfg: Config, agent_id: str) -> Path:
    base = cfg.inbox_dir or cfg.root / ".agents" / "village-inbox"
    return base / f"{parsers.slugify(agent_id)}.md"


def _universe_mirror_path(cfg: Config, universe_id: str) -> Path:
    """Local mirror of a live-universe conversation (the platform keeps the

    authoritative thread; the mirror gives the chat sheet continuity)."""
    base = cfg.inbox_dir or cfg.root / ".agents" / "village-inbox"
    return base / f"universe-{parsers.slugify(universe_id)}.md"


def _universe_chat_path(cfg: Config, universe: dict) -> Path:
    """The file backing a universe's chat thread (live mirror or universe dir)."""
    if universe.get("source") == "live" or not universe.get("path"):
        return _universe_mirror_path(cfg, universe["id"])
    return Path(universe["path"]) / "village-inbox.md"


def _talk_to_agent(cfg: Config, agent_id: str, message: str) -> dict:
    inbox = _inbox_path(cfg, agent_id)
    agent = _agent_by_id(cfg, agent_id)
    name = agent["name"] if agent else agent_id
    _append_inbox(inbox, "host", message)
    mode = "inbox"
    note: str | None = None
    if cfg.dispatch and agent and agent.get("provider") in ("claude", "codex"):
        if _DISPATCH_CAPACITY.reserve(1):
            try:
                threading.Thread(
                    target=_dispatch_peer_reserved,
                    args=(cfg, agent, message, inbox),
                    name=f"village-dispatch-{agent_id}",
                    daemon=True,
                ).start()
            except BaseException:
                _DISPATCH_CAPACITY.release()
                raise
            mode = "inbox+dispatch"
        else:
            note = "message saved to inbox; provider dispatch capacity is full"
    result = {"ok": True, "mode": mode, "to": name}
    if note:
        result["note"] = note
    return result


def _dispatch_peer_reserved(
    cfg: Config,
    agent: dict,
    message: str,
    inbox: Path,
) -> None:
    release_capacity = True
    try:
        _dispatch_peer(cfg, agent, message, inbox)
    except _PeerCleanupError as exc:
        release_capacity = False
        _append_inbox(inbox, "village", f"(dispatch cleanup unverified: {exc})")
    except Exception as exc:
        _append_inbox(inbox, "village", f"(dispatch failed: {exc})")
    finally:
        if release_capacity:
            _DISPATCH_CAPACITY.release()


def _dispatch_peer(cfg: Config, agent: dict, message: str, inbox: Path) -> None:
    if not cfg.dispatch:
        return
    """Fire a headless peer session on that provider's own budget; reply → inbox."""
    script = cfg.root / "scripts" / "peer_agent.py"
    provider = agent["provider"]
    if not script.is_file():
        _append_inbox(inbox, "village", f"(dispatch unavailable: {script} missing)")
        return
    out_file = _new_dispatch_artifact(inbox, label="reply")
    provider_pgid_file = _new_dispatch_artifact(inbox, label="provider-pgid")
    prompt = (
        f"You are {agent['name']}, one of the agents working in {cfg.root}. "
        f"Your current task: {agent.get('action')}. The host says:\n\n{message}\n\n"
        "Reply briefly as yourself."
    )
    try:
        _run_peer(
            [
                "python",
                str(script),
                provider,
                "--out",
                str(out_file),
                "--provider-pgid-file",
                str(provider_pgid_file),
                "--prompt",
                prompt,
                "--timeout",
                "540",
            ],
            cwd=cfg.root,
            timeout=600,
            env=_peer_environment(),
        )
        try:
            reply = out_file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            reply = ""
        _append_inbox(inbox, agent["name"], reply or "(no reply came back)")
    finally:
        _remove_dispatch_artifact(out_file)
        _remove_dispatch_artifact(provider_pgid_file)


def _engine_note(text: str) -> dict:
    """A notes.json entry matching workflow/notes.py's Note schema."""
    return {
        "id": f"village-{int(time.time() * 1000)}",
        "source": "user",
        "text": text,
        "category": "direction",
        "status": "unread",
        "target": None,
        "clearly_wrong": False,
        "quoted_passage": None,
        "anchor": None,
        "tags": ["agent-village"],
        "metadata": {},
        "timestamp": time.time(),
    }


def _talk_to_universe(cfg: Config, universe_id: str, message: str) -> dict:
    now = time.time()
    for universe in discover_universes(cfg, now):
        if universe["id"] != universe_id:
            continue
        if universe.get("source") == "live":
            url = _platform_url(cfg)
            if not url:
                return {"ok": False, "error": "no platform endpoint configured"}
            client = McpClient(url, token=cfg.mcp_token)
            reply = client.call_tool(
                "converse", {"message": message, "graph_id": universe_id}
            )
            mirror = _universe_mirror_path(cfg, universe_id)
            _append_inbox(mirror, "host", message)
            if reply is None:
                return {
                    "ok": False,
                    "error": "the live endpoint refused (writes need OAuth — "
                    "set WORKFLOW_MCP_TOKEN); your note is mirrored locally",
                }
            reply_text = reply if isinstance(reply, str) else json.dumps(reply)[:2000]
            _append_inbox(mirror, universe["name"], reply_text)
            return {"ok": True, "mode": "converse", "to": universe["name"]}
        udir = Path(universe["path"])
        if (udir / "notes.json").is_file():
            try:
                notes = json.loads((udir / "notes.json").read_text(encoding="utf-8"))
                if not isinstance(notes, list):
                    notes = [notes]
                notes.append(_engine_note(message))
                (udir / "notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")
                return {"ok": True, "mode": "notes.json", "to": universe["name"],
                        "note": f"{universe['name']} reads it at the next scene boundary"}
            except (OSError, ValueError):
                pass  # fall through to the durable file
        _append_inbox(udir / "village-inbox.md", "host", message)
        state = (
            "is asleep and will read this on next wake"
            if universe.get("status") != "alive"
            else "will read this at the next scene boundary"
        )
        return {"ok": True, "mode": "village-inbox", "to": universe["name"],
                "note": f"{universe['name']} {state}"}
    return {"ok": False, "error": f"universe {universe_id!r} not found"}


def chat_history(cfg: Config, target: str) -> list[dict]:
    if ":" not in target:
        return []
    kind, ident = target.split(":", 1)
    if kind == "agent":
        path = _inbox_path(cfg, ident)
        return _parse_inbox_md(path)
    if kind == "universe":
        now = time.time()
        for universe in discover_universes(cfg, now):
            if universe["id"] != ident:
                continue
            if universe.get("source") == "live":
                return _parse_inbox_md(_universe_mirror_path(cfg, ident))
            messages = _parse_inbox_md(Path(universe["path"]) / "village-inbox.md")
            if universe.get("last_activity"):
                ts = universe.get("ts")
                stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""
                messages.append(
                    {
                        "who": universe["name"],
                        "ts": stamp,
                        "text": f"(latest from my log) {universe['last_activity']}",
                    }
                )
            return messages
        return []
    return []


def _parse_inbox_md(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    messages: list[dict] = []
    who, stamp, buf = "host", "", []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s+—\s+(.+)$", line)
        if m:
            if buf:
                messages.append({"who": who, "ts": stamp, "text": "\n".join(buf).strip()})
            stamp, who = m.group(1), m.group(2)
            buf = []
        else:
            buf.append(line)
    if buf:
        messages.append({"who": who, "ts": stamp, "text": "\n".join(buf).strip()})
    return [m for m in messages if m["text"]][-100:]


# ---------------------------------------------------------------------------
# Hire — create agents for a universe

#: Provider CLIs the village knows how to detect (id, label, executable).
LLM_CLIS: list[tuple[str, str, str]] = [
    ("claude", "Claude Code", "claude"),
    ("codex", "Codex CLI", "codex"),
    ("kimi", "Kimi CLI", "kimi"),
    ("gemini", "Gemini CLI", "gemini"),
    ("cursor-agent", "Cursor agent", "cursor-agent"),
    ("aider", "Aider", "aider"),
    ("ollama", "Ollama · local models", "ollama"),
]

#: Providers scripts/peer_agent.py can dispatch today.
_DISPATCHABLE = ("claude", "codex")


def discover_providers(cfg: Config) -> list[dict]:
    """Hireable engines: installed CLIs on this machine + future capacity.

    Anything not installed or not yet built is returned unavailable with an
    honest note — the UI greys it instead of hiding it, so the user can see
    what's coming.
    """
    import shutil

    providers: list[dict] = []
    for pid, label, exe in LLM_CLIS:
        path = shutil.which(exe)
        providers.append(
            {
                "id": pid,
                "label": label,
                "kind": "local-cli",
                "available": bool(path),
                "dispatchable": pid in _DISPATCHABLE,
                "note": (path if path else "not installed"),
            }
        )
    providers.append(
        {
            "id": "hosted",
            "label": "Hosted compute",
            "kind": "hosted",
            "available": False,
            "dispatchable": False,
            "note": "coming with compute onboarding (still being built)",
        }
    )
    providers.append(
        {
            "id": "market",
            "label": "Market capacity",
            "kind": "market",
            "available": False,
            "dispatchable": False,
            "note": "coming with the compute market (still being built)",
        }
    )
    return providers


def _safe_dispatch_text(value: object, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if len(value) > max_length:
        raise ValueError(f"{field_name} is too long")
    if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f"{field_name} contains an unsafe character")
    return value


def hire(cfg: Config, payload: dict) -> dict:
    """Create agent(s) for a universe, or set its engine preset.

    payload: universe_id, provider, count (1-8), task, preset (bool).
    Dispatch = a real peer CLI session on that provider's own budget; the
    reply lands in the universe's village chat thread.
    """
    try:
        unknown = set(payload) - {"universe_id", "provider", "count", "task", "preset"}
        if unknown:
            raise ValueError(f"unknown field: {sorted(unknown)[0]}")
        universe_id = _safe_dispatch_text(
            payload.get("universe_id"), field_name="universe_id", max_length=200
        )
        provider = _safe_dispatch_text(
            payload.get("provider"), field_name="provider", max_length=100
        )
        task = _safe_dispatch_text(
            payload.get("task", ""), field_name="task", max_length=2000
        ).strip()
        preset = payload.get("preset", False)
        if not isinstance(preset, bool):
            raise ValueError("preset must be a boolean")
        count = payload.get("count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 8:
            raise ValueError("count must be an integer from 1 through 8")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not universe_id or not provider:
        return {"ok": False, "error": "universe_id and provider required"}
    if not preset and not cfg.dispatch:
        return {"ok": False, "error": "provider dispatch is disabled"}
    now = time.time()
    universe = next((u for u in discover_universes(cfg, now) if u["id"] == universe_id), None)
    if not universe:
        return {"ok": False, "error": f"universe {universe_id!r} not found"}

    engines = {p["id"]: p for p in discover_providers(cfg)}
    engine = engines.get(provider)
    if not engine:
        return {"ok": False, "error": f"unknown provider {provider!r}"}
    if not engine["available"]:
        return {"ok": False, "error": f"{engine['label']} is {engine['note']}"}

    if preset:
        return _hire_preset(cfg, universe, provider)
    return _hire_dispatch(cfg, universe, engine, task, count)


def _hire_preset(cfg: Config, universe: dict, provider: str) -> dict:
    """Point the universe's own daemon at a new preferred writer engine."""
    if universe.get("source") == "live" or not universe.get("path"):
        return {"ok": False, "error": "preset changes need the universe's local config — "
                "live universes are reassigned through the connector"}
    config_path = Path(universe["path"]) / "config.yaml"
    try:
        text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
        if re.search(r"^preferred_writer\s*:.*$", text, re.M):
            text = re.sub(r"^preferred_writer\s*:.*$", f"preferred_writer: {provider}",
                          text, flags=re.M)
        else:
            text = text.rstrip("\n") + f"\npreferred_writer: {provider}\n"
        config_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"could not write config.yaml: {exc}"}
    return {
        "ok": True,
        "mode": "preset",
        "to": universe["name"],
        "note": f"{universe['name']} will write with {provider} on its next daemon run",
    }


def _hire_dispatch(cfg: Config, universe: dict, engine: dict, task: str, count: int) -> dict:
    """Spawn real peer CLI sessions on the provider's own budget."""
    if not cfg.dispatch:
        return {"ok": False, "error": "provider dispatch is disabled"}
    if not engine["dispatchable"]:
        return {"ok": False, "error": f"{engine['label']} can't be dispatched from the village "
                "yet — set it as the daemon preset instead"}
    script = cfg.root / "scripts" / "peer_agent.py"
    if not script.is_file():
        return {"ok": False, "error": "scripts/peer_agent.py not found"}
    if not _DISPATCH_CAPACITY.reserve(count):
        return {"ok": False, "error": "provider dispatch capacity is full"}
    try:
        chat_path = _universe_chat_path(cfg, universe)
        brief = task or (
            f"Say hello to the universe '{universe['name']}' and propose one concrete "
            "improvement you could make to it."
        )
        _append_inbox(
            chat_path, "village",
            f"🧑‍🏭 hired {count} × {engine['label']} for '{universe['name']}': {brief}",
        )
    except BaseException:
        _DISPATCH_CAPACITY.release(count)
        raise

    def run_one(slot: int) -> None:
        out_file = _new_dispatch_artifact(chat_path, label=f"hire{slot}")
        provider_pgid_file = _new_dispatch_artifact(
            chat_path,
            label=f"hire{slot}-provider-pgid",
        )
        prompt = (
            f"You were hired in Agent Village to work for the universe "
            f"'{universe['name']}' (id {universe['id']}). Premise: "
            f"{universe.get('premise') or 'unknown'}. Task: {brief}\n\n"
            "Answer as the hired agent: what did you do or what do you recommend?"
        )
        try:
            _run_peer(
                [
                    "python",
                    str(script),
                    engine["id"],
                    "--out",
                    str(out_file),
                    "--provider-pgid-file",
                    str(provider_pgid_file),
                    "--prompt",
                    prompt,
                    "--timeout",
                    "540",
                ],
                cwd=cfg.root,
                timeout=600,
                env=_peer_environment(),
            )
            try:
                reply = out_file.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).strip()
            except OSError:
                reply = ""
            _append_inbox(
                chat_path,
                f"{engine['label']}·hire{slot}",
                reply or "(this hire came back empty)",
            )
        finally:
            _remove_dispatch_artifact(out_file)
            _remove_dispatch_artifact(provider_pgid_file)

    def run_reserved(slot: int) -> None:
        release_capacity = True
        try:
            run_one(slot)
        except _PeerCleanupError as exc:
            release_capacity = False
            _append_inbox(
                chat_path,
                "village",
                f"({engine['label']}·hire{slot} cleanup unverified: {exc})",
            )
        finally:
            if release_capacity:
                _DISPATCH_CAPACITY.release()

    started = 0
    try:
        for slot in range(1, count + 1):
            threading.Thread(
                target=run_reserved,
                args=(slot,),
                name=f"village-hire-{slot}",
                daemon=True,
            ).start()
            started += 1
    except BaseException:
        _DISPATCH_CAPACITY.release(count - started)
        raise
    return {
        "ok": True,
        "mode": "dispatch",
        "to": universe["name"],
        "note": f"{count} × {engine['label']} dispatched on their own budget — "
        "watch the universe chat (and the village: they'll walk in as sprites)",
    }
