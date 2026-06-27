---
status: active
---

# Multi-Provider Concurrent Daemon Runtime in Tray

**Status:** draft r6, 2026-04-12 (pin mechanism corrected to env var — verified against landed code)
**Owner:** planner (spec) / dev (impl)
**Paired with:** Task A (status bridge, dev-owned)
**Scope:** `universe_tray.py`, `fantasy_author/__main__.py`, `tinyassets/providers/router.py`, `tinyassets/preferences.py`

**Revision notes (r2):**
- CLI entry point corrected: flag lives on `fantasy_author.__main__` (already
  landed at line 1500). Top-level CLI entry point is `tinyassets-cli` /
  `python -m tinyassets`; the `--provider` flag is on the domain module. Kept
  the fantasy_author path because Task B daemons are fantasy_author daemons.
- Preferences file: `~/.tinyassets/preferences.json` (LANDED in
  `tinyassets/preferences.py` at `_TINYASSETS_USER_DIR = Path.home() /
  ".workflow"`). NOT `~/.claude/workflow_preferences.json` and NOT
  repo-local. Reason: Claude Code owns `~/.claude/` exclusively (it
  rewrites settings.json, keybindings.json, teams/, tasks/ on updates)
  and bundled updates could collide. `~/.tinyassets/` is a dedicated
  user-scope dir for this project. Per-host-operator scope, orthogonal
  to per-universe `config.yaml`. Team-lead override 2026-04-12.
  (r2 incorrectly stated repo-local `output/.tray_preferences.json`;
  planner misread the landed module header. Corrected in r3.)
- Pin mechanism: `TINYASSETS_PIN_WRITER` env var. `fantasy_author/__main__.py:1530`
  sets `os.environ["TINYASSETS_PIN_WRITER"] = args.provider`;
  `tinyassets/providers/router.py:128` reads it per-call and, when set for
  the writer role, narrows the chain to `[pin_writer]` with no fallback.
  Verified against landed code 2026-04-12.
  (r2 incorrectly claimed dict mutation was landed — planner read a stale
  code state before Task 4's env-var refactor. Corrected in r6.)
- Status file: split into per-provider files
  (`output/.daemon_status.<provider>.json`) per reviewer blocker #3.
- Heartbeat: independent 5s timer thread, NOT phase-coupled, per reviewer
  blocker #5.

---

## Purpose

Run multiple pinned-provider daemons side by side from the host tray, so the
operator can compare providers live on one universe (or distinct universes)
without editing config files or restarting the tray. First step toward a real
swarm runtime; not the swarm scheduler itself.

---

## Design Principles

1. **Pinned, not routed.** A daemon started with `--provider X` must call only
   X. No silent fallback to another subscription provider. If X is unavailable,
   that daemon fails loudly (consistent with AGENTS.md hard rule #8).
2. **Provider is the daemon's identity for this feature.** One process per
   provider. The tray keys state by provider name, not by universe or PID.
3. **Subscription uniqueness is a tray-enforced constraint, not a router
   property.** The router doesn't know about subscription limits. The tray
   refuses to spawn a second daemon for the same provider.
4. **Contested filesystem state is out of scope tonight.** Multiple daemons
   writing the same universe will race on `notes.json`, `world_state.db`, KG
   files. Documented risk, deferred solution.

---

## CLI Contract

### `--provider` flag on `fantasy_author.__main__` (LANDED)

```
python -m fantasy_author --universe <name> --provider <provider-name> [...]
```

Valid `<provider-name>` values (writer-role registry keys in
`tinyassets/providers/router.py:FALLBACK_CHAINS["writer"]`):
`claude-code`, `codex`, `gemini-free`, `groq-free`, `grok-free`, `ollama-local`.

**Semantics (as landed at `fantasy_author/__main__.py:1515-1534` and
`tinyassets/providers/router.py:125-131`):**
- When `--provider X` is passed, `__main__` validates `X` against
  `set().union(*FALLBACK_CHAINS.values())` (union of all role chains —
  includes every known provider name across writer, judge, and extract).
  Then sets `os.environ["TINYASSETS_PIN_WRITER"] = X`.
- The router consults `TINYASSETS_PIN_WRITER` per call. For writer-role
  calls with the env var set, it narrows the chain to `[pin_writer]` and
  skips the per-universe preference path. For other roles the env var has
  no effect, so judge/extract continue using their default fallback chains.
- If `X` is not in the known set, `parser.error()` exits non-zero with a
  clear message. Tray catches early exit and shows "failed to start".
- If `X` is in the registry but hits cooldown/quota mid-run, the daemon
  surfaces `AllProvidersExhaustedError` rather than falling through — same
  as any other single-provider exhaustion path. Honors hard rule #8.
- **Writer role only for now.** Future `--judge-provider` /
  `--extract-provider` would follow the same pattern with
  `TINYASSETS_PIN_JUDGE` / `TINYASSETS_PIN_EXTRACT`. Out of scope; see Open Q #3.

### Why env var over dict mutation

Per-call env lookup means the router can't cache a mutated chain from
module-import time. Env vars travel through subprocess boundaries cleanly,
which matters when the tray spawns daemons. `FALLBACK_CHAINS` stays
immutable at module level, so future readers and tests see consistent
state. (r1 proposed this design; r2 mistakenly documented a dict-mutation
alternative; r6 confirms env var is what actually shipped.)

### Registry drift check (reviewer note #1)

`claude-code` is writer-only in the current chains. `codex, gemini-free,
groq-free, grok-free, ollama-local` appear in multiple role chains. If a
future `--judge-provider` is added, validation must key off
`FALLBACK_CHAINS["judge"]` not the writer set. See Open Q #3.

---

## Status File Schema (per-provider; coordinate with dev Task A)

**Path:** `output/.daemon_status.<provider>.json`, one file per running
daemon. Per-provider (not shared) per reviewer blocker #3: atomic
tmp+rename writes cannot coexist safely with RMW-under-lock of a shared
file, and per-provider writers eliminate the entire contention class.

**Writer:** the single daemon that owns that provider key. No other process
writes that file.
**Reader:** tray polls `output/.daemon_status.*.json` on its existing 1s
interval; missing file means `stopped`.
**Write semantics:** write tmp → fsync → `os.replace` (atomic). No lock
needed because only one writer per file.

```json
{
  "schema_version": 1,
  "provider": "ollama-local",
  "pid": 12345,
  "universe": "ashwater",
  "phase": "draft",
  "started_at": "2026-04-12T22:14:03Z",
  "last_heartbeat": "2026-04-12T22:18:41Z",
  "status": "running"
}
```

**Status values:** `starting`, `running`, `paused`, `stopped`, `crashed`.

**Staleness rule:** tray considers a provider `stopped` if
`last_heartbeat` is older than 15s, regardless of what `status` says.
(15s chosen because heartbeat is a 5s independent timer — three missed
beats = stopped. Was 30s in r1; tightened per reviewer #5 since heartbeat
is now timer-driven not phase-coupled.)

**Heartbeat thread (reviewer blocker #5):** each daemon spawns a daemon
thread at startup that writes an updated `last_heartbeat` every 5s,
independent of phase transitions. Phase transitions update the `phase`
field on top of the heartbeat. This prevents long `draft` or `commit`
phases from appearing as `stopped`.

**Shutdown cleanup:** on graceful stop, daemon writes `"status": "stopped"`
as its final write, then deletes the file. If delete fails (race), tray's
staleness rule handles it within 15s.

**Coordination with Task A:** Task A (status bridge) hasn't landed yet as
of this r2. If Task A's bridge wants to aggregate, it can either (a) tail
`output/.daemon_status.*.json` and publish a merged view, or (b) use a
separate aggregation file. Either way, per-provider files remain the
canonical source of truth. Planner will update this section once Task A
lands its interface.

---

## Tray State Model

In `universe_tray.py`, replace:

```python
self.daemon_proc: subprocess.Popen | None = None
```

with:

```python
self.daemon_procs: dict[str, subprocess.Popen] = {}
self.default_provider: str = self._load_default_provider()
```

### `daemon_procs` invariants

- Keyed by provider name.
- Only contains live `Popen` objects. On detected exit, key is removed.
- Mutations happen on the tray thread only; reads from the menu-build thread
  are safe because `dict` copies are atomic for read in CPython.

### Constants (LANDED in `tinyassets/preferences.py`)

```python
# Imported from workflow.preferences — do NOT redefine in universe_tray.py
from workflow.preferences import (
    ALL_PROVIDERS,
    SUBSCRIPTION_PROVIDERS,  # list[str], 5 entries
    LOCAL_PROVIDERS,          # list[str], 1 entry (ollama-local)
)
```

Note the landed shape uses `list[str]` not `set`. Tray menu rendering needs
stable ordering, so lists are correct. Use `set()` coercion for membership
tests (`if p in set(LOCAL_PROVIDERS):`) if hot-path matters; not likely at
1Hz poll.

### Thread-safety for `daemon_procs` (reviewer note #7)

Menu-build thread reads `daemon_procs`; tray thread mutates it. Snapshot at
read entry:

```python
def _build_menu(self) -> Menu:
    snapshot = list(self.daemon_procs.items())  # atomic under GIL
    # iterate snapshot, not self.daemon_procs
```

Avoids `RuntimeError: dictionary changed size during iteration`.

### Default provider persistence (LANDED)

**File:** `~/.tinyassets/preferences.json` (landed in `tinyassets/preferences.py`
at `_TINYASSETS_USER_DIR = Path.home() / ".workflow"`).
Shape:

```json
{
  "default_providers": ["ollama-local"],
  "auto_start_default": true
}
```

**Why `ollama-local` as the default:** it's the only provider with no
subscription quota, so a fresh tray startup never hits a paid API on first
run. Operators explicitly opt into subscription providers by adding them
via the menu. This reinforces the "fail loudly" principle — if a pinned
subscription daemon exhausts, it's because the operator deliberately
chose it, not because an auto-start silently burned quota.

**Why `~/.tinyassets/`, not `~/.claude/` or repo-local:**
- Not `~/.claude/`: Claude Code owns that directory exclusively and rewrites
  settings.json, keybindings.json, teams/, tasks/ on its own updates;
  bundled updates could collide.
- Not repo-local: preferences are per-host-operator, not per-repo-checkout.
  A single operator running two worktrees should share one set of
  preferences.
- `~/.tinyassets/` is a new dedicated user-scope dir for this project, clean
  of external ownership.

**Directory creation:** `preferences.py` must `mkdir(parents=True,
exist_ok=True)` on `~/.tinyassets/` before first write. Missing dir on first
load is not an error — falls back to defaults. (Verify landed module
handles this; if not, file a follow-up.)

**Schema note:** `default_providers` is a **list** (supports auto-starting
multiple providers), not a single value. This is richer than r1's
`default_provider: str`. Tray's auto-start loop iterates the list, subject
to the constraint-enforcement rules below (at most 1/subscription provider,
at most 1 local).

At startup, if `auto_start_default` is true, tray spawns one daemon per
provider in `default_providers`, skipping any that fail constraint checks
with a log warning.

---

## Tray Menu Structure

Multi-select checkbox menu. Clicking a provider row toggles that daemon
(running ↔ stopped). Multiple providers run concurrently.

```
Universe: ashwater
─────────────────
Providers  (toggle to start/stop)
  [✓] ollama-local    running
  [ ] claude-code     stopped
  [ ] codex           stopped
  [ ] gemini-free     stopped
  [ ] groq-free       stopped
  [ ] grok-free       stopped
─────────────────
Auto-start defaults   [✓]
Edit default providers >  (sub-menu of ALL_PROVIDERS, each a checkbox
                           bound to `default_providers` in preferences)
─────────────────
View log              >  (sub-menu: one entry per running provider)
Open MCP URL
Open log folder
─────────────────
Quit
```

### Interaction model

- **Toggle checkbox:** clicking a `[ ]` calls `start(provider)`; clicking
  a `[✓]` calls `stop(provider)`. No submenu indirection for the common
  case.
- **Visual state:** checkbox mirrors `provider in daemon_procs`. Status
  label (`running` / `stopped` / `starting` / `crashed`) comes from
  status-file heartbeat + `proc.poll()`.
- **Disabled rows:** a provider that cannot start right now is greyed
  out. Today this only happens when starting ollama-local would violate
  the local-provider constraint and another local daemon is running
  — currently impossible because ollama-local is the only local
  provider, but code the check so a future second local provider
  triggers it correctly.
- **Default providers submenu** lets the operator tick which providers
  auto-start on tray launch. Writes straight to
  `~/.tinyassets/preferences.json:default_providers`.

### Status labels

- `running` — PID alive, heartbeat fresh.
- `stopped` — no entry in `daemon_procs` or stale heartbeat.
- `starting` — PID alive, last_heartbeat null or <5s since spawn.
- `crashed` — PID gone but status file last said `running`; tray shows this
  label once, then transitions to `stopped` on next refresh.

### Hover tooltip

Aggregates across active daemons, comma-separated in menu order:

```
Single default (fresh tray launch):
  Workflow | Active: ollama-local | MCP: OK | Tunnel: OK

Operator added claude-code on top of the default:
  Workflow | Active: ollama-local, claude-code | MCP: OK | Tunnel: OK

No daemons running:
  Workflow | Idle | MCP: OK | Tunnel: OK
```

Icon color rules unchanged except: **green** now means MCP + tunnel OK AND at
least one daemon running. **yellow** if MCP+tunnel OK but zero daemons
running.

---

## Constraint Enforcement

Two uniqueness rules. Applied in the tray before spawning a daemon.

1. **One daemon per provider name (trivially enforced).**
   `daemon_procs` is keyed by provider name, so a second concurrent
   `claude-code` daemon is structurally impossible. If `start(provider)`
   is called while `provider in daemon_procs`, tray logs and no-ops.
   User-facing: the checkbox is already `[✓]`, so clicking toggles it
   to stop — there's no "start a second" action to invoke. No explicit
   check needed beyond the key-existence guard.

2. **At most one local provider running at a time (real constraint).**
   Today `LOCAL_PROVIDERS = ["ollama-local"]` (one element), so the
   constraint is dormant. Code it anyway so a future second local
   provider triggers correctly:

   ```python
   def _can_start(self, provider: str) -> tuple[bool, str]:
       if provider in self.daemon_procs:
           return False, "already running"
       if provider in LOCAL_PROVIDERS:
           running_locals = [
               p for p in self.daemon_procs
               if p in LOCAL_PROVIDERS
           ]
           if running_locals:
               return False, f"another local provider running: {running_locals[0]}"
       return True, ""
   ```

   Tray greys out local provider checkboxes when another local is
   running. Attempting to start via an uncached click surfaces the reason
   in a log line + one-shot tooltip.

3. **Universe is implicit.** Every spawned daemon binds to whatever
   universe is in `output/.active_universe` at spawn time. Switching
   universes mid-session is out of scope: daemons keep writing to the
   universe they were started on. Document this on the menu as
   "Universe: {name}" at the top — it shows the universe the NEXT start
   will bind to, not necessarily the universe of currently-running
   daemons.

**Note on the earlier "subscription uniqueness" framing:** r1–r4 listed
"at most 1 per subscription provider" as a distinct constraint. It
isn't: subscription-provider uniqueness is per-provider-name, and
per-provider-name uniqueness is the trivial dict-keying rule above.
There's no subscription-bucket concept in the code. Kept this note so
future readers don't re-invent the distinction.

### Spawn command template

```python
cmd = [
    sys.executable, "-m", "fantasy_author",
    "--universe", active_universe,
    "--provider", provider_name,
]
proc = subprocess.Popen(
    cmd, cwd=PROJECT_DIR,
    stdout=open(LOG_DIR / f"daemon.{provider_name}.log", "a"),
    stderr=subprocess.STDOUT,
)
self.daemon_procs[provider_name] = proc
```

Per-provider log files let the menu's "View log" action open the right one.

**Env var handling:** the tray does NOT set `TINYASSETS_PIN_WRITER` itself.
The daemon sets it from `--provider` inside its own process at
`fantasy_author/__main__.py:1530`, so the pin is scoped to that subprocess
and never leaks into the tray's env or sibling daemons. Keeping this
explicit so a future refactor doesn't mistakenly hoist the env var into
the tray's spawn contract.

### Shutdown

- Per-provider Stop: `proc.terminate()`, wait 10s, then `proc.kill()`.
  Remove key from `daemon_procs` regardless of exit code.
- Tray Quit: stop all daemons in parallel (thread per proc), then MCP,
  then tunnel. Cap total shutdown at 20s.

---

## `_any_daemon_alive()` source of truth (reviewer note #8)

The tray's own `daemon_procs` dict is the source of truth for "is any
daemon alive" — NOT the status files. Status files are for cross-process
consumers (external readers, Task A's bridge). The tray managing its own
children reads `proc.poll()`:

```python
def _any_daemon_alive(self) -> bool:
    return any(proc.poll() is None for proc in self.daemon_procs.values())
```

This avoids a race where a daemon has exited but its status file still
lingers, or vice versa. Clean up `daemon_procs` entries when `poll()`
returns non-None (detected in the 1s tray tick).

---

## Migration Path

1. ~~Dev adds `--provider` flag~~ **LANDED** at
   `fantasy_author/__main__.py:1500`. Uses direct `FALLBACK_CHAINS` mutation.
2. ~~Dev builds `tinyassets/preferences.py`~~ **LANDED**. Exports
   `ALL_PROVIDERS`, `SUBSCRIPTION_PROVIDERS`, `LOCAL_PROVIDERS`,
   `load_prefs()`, `save_prefs()`.
3. Dev adds per-provider status file writer to the daemon startup path
   (heartbeat thread writes `output/.daemon_status.<provider>.json` every
   5s; phase transitions update `phase` field).
4. Dev refactors `daemon_proc` → `daemon_procs: dict[str, Popen]` in
   `universe_tray.py`. Add `_any_daemon_alive()` helper reading `.poll()`.
5. Menu rebuild: per-provider submenu reading `output/.daemon_status.*.json`
   for labels; Start/Stop actions; default providers radio sourced from
   `workflow.preferences`; auto-start checkbox.
6. Preferences round-trip on menu changes (save_prefs after each toggle).
7. Manual smoke: start claude-code + ollama-local on ashwater. Verify
   both per-provider status files write/expire correctly, tooltip
   aggregates, per-provider log files populate, Stop on one leaves the
   other running, tray Quit stops everything within 20s.

---

## Open Questions

1. **Contested state.** Two daemons on one universe will stomp each other's
   notes/world-state writes. No lock, no branching, no merge. Acceptable for
   tonight's tray test because the operator chooses when to run two; surface
   a one-time warning dialog when a second daemon is started on a universe
   that already has one running. **Not solving this in this spec.**
2. **Pause action.** Menu shows "Pause (future)" — needs a daemon-side
   signal handler. Punt unless dev has spare cycles.
3. **Per-role pinning.** Current spec pins writer only via direct
   `FALLBACK_CHAINS["writer"] = [X]` mutation in `__main__`. If the
   operator wants "claude-code writes, codex judges," add
   `--judge-provider` / `--extract-provider` flags — but at that point,
   promote the mutation to an env-var or ProviderRouter constructor arg
   so `__main__` doesn't poke router internals for every role. Validation
   must also key off the correct role chain (writer ≠ judge ≠ extract).
   Defer until concrete use case.
4. **Crash visibility.** Currently a crashed daemon just disappears from the
   menu. Consider a transient toast or a `[crashed]` sticky state until the
   user clicks "Clear." Low priority.
   **Related preferences-dir note:** `~/.tinyassets/` must exist before the
   preferences module's first write. Landed module handles this at
   `preferences.py:109` (`path.parent.mkdir(parents=True, exist_ok=True)`).
   Missing dir on first load falls back to `_DEFAULTS` — not an error. If
   that ever regresses, tray startup must still succeed with defaults
   rather than crashing.
5. ~~**Status file contention with Task A.**~~ Resolved r2: per-provider
   files eliminate the contention class. Task A's bridge reads the same
   files; no shared-file writes.
6. **Ollama model selection.** `ollama-local` doesn't say which model. If
   the operator wants to run two Ollama daemons with different models, the
   "one local" rule blocks it. Re-key the dict by `(provider, model)` when
   this becomes real. Not tonight.
7. **Registry drift.** `ALL_PROVIDERS` is hardcoded in the tray. If the
   provider registry grows, the tray silently lacks a menu entry. Consider
   introspecting `ProviderRouter._providers` at menu-build time. Defer;
   provider list is stable for now.

---

## Non-Goals

- Swarm scheduler / cross-host runtime allocation.
- Branch-aware daemon dispatch.
- Shared-state merge resolution.
- Real-time streaming of daemon progress to the tray menu (polling is fine).
- Authentication / permission model for who can start/stop daemons (single
  local operator assumed).
