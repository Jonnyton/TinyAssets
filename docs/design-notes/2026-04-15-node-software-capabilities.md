---
status: active
---

# Node Software Capabilities — First-Class Plug-and-Play

**Status:** Promotion-ready. Explorer scout #36 + host §10 answers (Q1/Q2/Q3) + new Shape IV software-donation feature folded 2026-04-15. One remaining item pending host: explicit PLAN.md principle approval (§9).
**Related:** Planner memory `project_node_software_capabilities.md`. Memory-scope Stage 2 (`2026-04-15-memory-scope-tiered.md`) for `branch_node_scope.yaml` colocation. Phase G `tinyassets/node_sandbox.py` as the existing subprocess-isolation precedent.
**Target:** MVP that lets a user-sim mission run an Unreal-Engine-backed video-game-creation workflow on the host's existing Unreal install, on-approval.

## 0. Framing

**This is the biggest attack-surface expansion the project has ever shipped.** Nodes invoking arbitrary local software means daemons can: launch Unreal, drive Blender, automate Visual Studio, play games, shell out to anything `subprocess` can reach. The security model is the design — if it's wrong, the project ships a rootkit-by-bid.

Simultaneously: **plug-and-play is the viral hook for the product's breadth.** "Your daemon can summon Unreal Engine" is the feature that turns the fantasy-author demo into a general-purpose workflow platform. Friction at install-time is friction for adoption. The design has to make *both* goals load-bearing, not trade one for the other.

### 0.1 Explorer's key finding: the pattern already exists

Explorer scout (#36, 2026-04-15) surfaced that the **`required_llm_type` / `served_llm_type` pair is the capability-filter template**. A node declares what it needs (`required_llm_type: "claude-opus"`); a daemon declares what it serves (`served_llm_type: "claude-opus"`); the dispatcher at `tinyassets/dispatcher.py:230-238` filters bids on match. This design generalizes that pair from string-scalar to list-of-capabilities (`required_capabilities: list[str]` / `served_capabilities: list[str]`) and extends the filter to set-inclusion. **The engineering surface is smaller than the product ambition suggests.**

### 0.3 Host's 2026-04-15 decisions (§10 answers)

Three product choices locked; they reshape MVP scope:

- **Pattern C (UI automation) is in MVP, not deferred.** Each node declares its pattern; **Pattern C is the default** because it is most like the actual user experience. Pattern B is also in MVP. Node authors pick per-node. This is the expensive call — UI automation adds real MVP cost but is load-bearing for the "daemon plays Minecraft" brand.
- **Auto-install default: `always`.** Install and update without prompting. The approval gate is software-level trust ("this daemon is allowed to run Unreal on my machine"), not per-install friction. Revocation is the key verb — a host approves Unreal once, that stands until revoked; same for updates.
- **Approval granularity: per-software, persistent, host-level.** Not per-branch-version, not per-node-instance. Approvals accumulate as the host's software-trust profile; revocation is granular to a single capability.

Consequence: the design's center of gravity shifts from "approval per run" to "approval per software, maintained as a trust list." The friction cost is front-loaded (first time a user sees an Unreal-requiring node) and amortized after.

### 0.4 New feature: cross-host software donation (Shape IV)

Host reframed multi-computer in this session: remote daemon-invocation isn't worth building (same problem as "let other daemon run the node"). But **peer-to-peer software donation IS worth building.** If Host A has Unreal's installer cached and Host B needs it, B requests from A instead of re-downloading from the internet — faster, cheaper, shares the bandwidth across the multiplayer set.

**This is not a security bypass.** Donation still routes through the full security layer stack: binary-signature verification, trusted publisher check, universe allow-list, per-software approval. Donation moves *the bits*; it doesn't move *the trust*.

See §7 for the Shape IV design.

### 0.2 Explorer's key constraint: sandboxes currently *prevent* this

The three existing node-execution paths all specifically prevent launching external binaries — that's why Phase G sandboxing exists. An `external_tool_node` type (new) is the clean escape seam; extending `tools_allowed` enforcement would re-litigate the Phase G threat model. **MVP introduces a new node type, not a sandbox hole.**

## 1. Requirement declaration syntax

### Where

**Two locations, one source of truth.** Per explorer's scout, `NodeDefinition` at `tinyassets/branches.py:101-150` is the existing authoritative schema for what a node IS (including `required_llm_type`, `dependencies`, `tools_allowed`). That's where `required_capabilities: list[str]` lives — as a sibling of `dependencies`. This is the canonical declaration.

**`<branch>/node_scope.yaml` carries the same field as a view-friendly override**, so the memory-scope manifest stays the single "what this node reaches out to" reviewer surface (per memory-scope Stage 2 §4). At branch-registration time, if `node_scope.yaml` declares `requires:` for a node, it must match or be a subset of the `NodeDefinition.required_capabilities`; mismatch fails registration with a loud error.

Rationale: NodeDefinition is the code-truth; the YAML is the reviewer-truth. Forcing them to agree at registration prevents silent drift. Splitting without this check is the real failure mode.

### Syntax

```yaml
# <branch>/node_scope.yaml
default:
  universe_member: true
  breadth: full_canon
  requires: []            # default: no software requirements

nodes:
  render_game_cinematic:
    universe_member: true
    breadth: full_canon
    capability_pattern: ui_automation    # or: headless (Pattern B). Default: ui_automation.
    requires:
      - id: unreal_engine
        version: ">=5.4"
        optional: false
      - id: ollama
        version: ">=0.3"
        optional: false
      - id: python
        version: "==3.11.*"
        optional: false
        # python is special — see §Versioned runtimes below

  suggest_character_design:
    capability_pattern: headless          # opt out of default UI automation
    requires:
      - id: ollama
        version: ">=0.3"
        model: "llama3.1:70b"   # extension field, tool-specific
        optional: false
      - id: blender
        version: ">=4.0"
        optional: true           # node degrades gracefully if missing
```

### Fields per requirement

| Field | Required? | Shape | Example |
|---|---|---|---|
| `id` | yes | Canonical capability ID (well-known names; see §3 registry). Lowercase, underscore-separated. | `unreal_engine`, `ollama`, `blender`, `visual_studio`, `python`, `node`, `docker` |
| `version` | yes | PEP 440 specifier OR semver range. Both parse; registry resolver normalizes. | `">=5.4"`, `"==5.4.4"`, `">=5.4,<6"` |
| `optional` | no (default `false`) | If `true`, node is runnable without it; the node detects absence and branches. | `true`/`false` |
| tool-specific extensions | no | Arbitrary keys namespaced under the requirement. Registry passes them to the tool handler. | `model: "llama3.1:70b"` for `ollama` |

### Per-node `capability_pattern` field (host-decided 2026-04-15)

New at the per-node level, sibling of `requires:`:

| Value | Meaning |
|---|---|
| `ui_automation` | **Default.** Node drives the software's UI via pyautogui/pywinauto/etc. Like the actual user experience. |
| `headless` | Node invokes the software via CLI / file-IO. Faster, less fragile, but limits what the daemon can do. |
| `auto` | Handler-specific — handler decides based on task. Opt-in for handlers that expose both. |

The field is per-node because a single node's task determines which pattern fits. Some nodes only need headless (batch-build a game project); some need UI (play through a game level); a few could go either way.

**Invariant:** `capability_pattern` must be supported by every handler named in `requires:`. Registration-time check: if any required handler doesn't implement the declared pattern, fail registration with a clear message. Each bundled handler declares which patterns it supports in its manifest.

### What this is NOT

- **Not a package manager.** Dev does not write `pip install langgraph` here. Python dependencies for node code are the bundle's `pyproject.toml` (per packaging spec). THIS is for **external software** the node invokes: engines, games, binaries with independent install stories.
- **Not a transitive resolver.** Each node declares only what it directly invokes. If Unreal needs Visual Studio to build, the Unreal capability handler handles that; the node doesn't.
- **Not a replacement for `required_llm_type`.** The two coexist in the MVP; explorer flagged the string-scalar field as a candidate for later migration into `required_capabilities`. Leave the existing field alone for MVP (reuse its dispatcher-filter pattern, don't churn the field itself).

## 2. Versioned runtimes (the Python trap)

Python is in the `requires` list as an illustration — but it's a trap. The daemon itself is Python; the node is running *inside* a daemon process; a `python: ==3.11.*` requirement on the node is either tautological (already have it) or requires sub-process-with-different-python (which means the node isn't a Python node any more; it's a subprocess orchestrator).

**Rule:** Python version declarations are advisory (the node documents what it was tested on); the registry surfaces them for UI/troubleshooting but does not auto-install Python. Same for Node.js, any language runtime the host itself depends on. **External software** (Unreal, Blender, games, non-Python binaries) is the first-class case.

## 3. Capability registry shape

### MVP shape — explorer-recommended: YAML per host

**Revised per explorer scout.** MVP uses a hand-maintained YAML file at `<repo_root>/hosts/<host_id>.yaml`, not a SQLite database. Mirrors the explorer-recommended path; auto-detection deferred to post-MVP.

```yaml
# hosts/jonathan-desktop.yaml
host_id: jonathan-desktop
served_capabilities:
  - id: claude-opus
  - id: unreal_engine
    version: "5.4.4"
    install_path: "C:/Program Files/Epic Games/UE_5.4"
  - id: ollama
    version: "0.3.12"
    install_path: "C:/Users/Jonathan/AppData/Local/Programs/Ollama/ollama.exe"
```

Hand-maintained means: host writes this file once (or `capabilities init` CLI scaffolds it from a wizard). File is version-controlled per Phase 7 "GitHub as canonical shared state" direction — a daemon pulling the repo sees which hosts in the multiplayer set can serve which capabilities.

### Post-MVP: auto-detection + SQLite cache

Once auto-detect handlers land (post-MVP), the SQLite shape I originally drafted becomes the cache layer behind the YAML: YAML is the committed source of truth; SQLite is the fresh-scan cache with a staleness window. MVP skips this — YAML is enough for one user's one host.

```sql
-- POST-MVP ONLY. Kept here for design continuity; do not ship in MVP.
CREATE TABLE capabilities (
    capability_id   TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    installed       INTEGER NOT NULL,
    version         TEXT,
    install_path    TEXT,
    detected_at     REAL NOT NULL,
    detection_method TEXT NOT NULL,
    handler_id      TEXT NOT NULL
);
```

```sql
CREATE TABLE capabilities (
    capability_id   TEXT PRIMARY KEY,      -- e.g. "unreal_engine"
    display_name    TEXT NOT NULL,         -- "Unreal Engine"
    installed       INTEGER NOT NULL,      -- 0 or 1
    version         TEXT,                  -- "5.4.4"
    install_path    TEXT,                  -- OS-specific absolute path
    detected_at     REAL NOT NULL,
    detection_method TEXT NOT NULL,        -- "auto" | "manual" | "installer"
    handler_id      TEXT NOT NULL          -- which capability handler owns this
);

CREATE TABLE capability_install_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id   TEXT NOT NULL,
    event           TEXT NOT NULL,         -- "detect" | "install_start" | "install_complete" | "install_fail"
    timestamp       REAL NOT NULL,
    actor           TEXT,                  -- who triggered: "host_auto" | user_login | daemon_id
    details_json    TEXT
);
```

### Capability handlers

Each known software type has a **capability handler** — a small Python module implementing a fixed interface:

```python
class CapabilityHandler(Protocol):
    id: str                      # "unreal_engine"
    display_name: str

    def detect(self) -> DetectedCapability | None:
        """Scan the host for this software. Return version + path if found."""

    def install(self, version_spec: str, *, progress: Callable) -> InstallResult:
        """Fetch+install. May require user confirmation (handler-specific)."""

    def invoke(self, args: list[str], *, cwd: Path, env: dict, **kwargs) -> InvocationHandle:
        """Start the software. Return a handle to control it."""

    def verify(self, install_path: Path) -> bool:
        """Sanity-check an install (file exists, version check passes)."""
```

Handlers live in `tinyassets/capabilities/handlers/` (one file per capability). Bundled handlers for the MVP: `unreal_engine.py`, `ollama.py`. Others ship over time. Third-party handlers: out of scope for MVP; flag §7.

### Detection

At daemon start, a **capability scan** runs: each handler's `detect()` probes the host (registry keys on Windows, well-known paths on Linux/Mac, Spotlight/AppsFolder, `where <binary>`). Results populate `capabilities` table. Scan is cached with a staleness window (default 24 hours); MCP tool `refresh_capabilities` forces re-scan.

Handlers that can't auto-detect (because the software has no predictable location) ask the user for a path on first encounter, then cache it.

### Handler lookup by capability ID

A capability ID in `required_capabilities` (e.g. `unreal_engine`) maps to exactly one handler via a registry:

```python
HANDLERS: dict[str, CapabilityHandler] = {
    "unreal_engine": UnrealEngineHandler(),
    "ollama": OllamaHandler(),
    # ...
}
```

Missing handler for a declared capability = node preflight fails loudly with `UnknownCapability` error. No silent proceed.

### Dispatcher filter (MVP one-line extension)

Explorer confirmed `tinyassets/dispatcher.py:230-238` already filters bids by `required_llm_type` matching host's `served_llm_type`. MVP extends this to check `required_capabilities` ⊆ `served_capabilities` set:

```python
# tinyassets/dispatcher.py (pseudocode of the extension)
if bid.required_llm_type and bid.required_llm_type != host.served_llm_type:
    continue  # existing filter
if bid.required_capabilities:
    if not set(bid.required_capabilities).issubset(host.served_capabilities):
        continue  # NEW: capability filter
```

This is the main new runtime code path. Everything else is schema + handler + bundling.

## 4. Resolution flow

```
Daemon picks a node
    │
    ▼
Preflight: load node's requires[] from branch_node_scope.yaml
    │
    ▼
For each required capability:
    │
    ├── Lookup handler (fail loud if unknown)
    │
    ├── Query capabilities table (cache hit / miss)
    │
    ├── If miss / stale: handler.detect()
    │
    ├── If detected: version-match against requires[].version
    │     ├── Match: mark available, continue
    │     └── Mismatch: fall to install flow
    │
    └── If not detected: fall to install flow
    │
    ▼
Install flow (per missing/mismatched capability):
    │
    ├── Consult host auto_install policy (§5)
    │     ├── always + allowed for this capability: run handler.install(), log
    │     ├── ask: emit host-approval prompt via MCP tray UI; wait
    │     └── never: node preflight fails with MissingCapability
    │
    ├── Install runs:
    │     ├── Success: rerun detect, update registry, continue preflight
    │     ├── Failure: log, mark capability as "install_failed_<timestamp>"
    │
    ▼
All required capabilities resolved?
    ├── Yes: node runs.
    └── No:
        ├── Node has optional-only missing: runs with degraded context, emits warning.
        ├── Node has required-missing: bid returns, logs "CapabilityUnavailable".
        │    - In paid-market context: bid refund, node stays in queue for a daemon with capabilities.
        │    - In non-paid context: node errors out, operator sees the gap.
```

### Failure mode detail

**Install fails.** Handler emits a structured failure result (network error / signature check failed / disk full / user rejected UAC). Logged to `capability_install_log`. Node bid returns with `CapabilityInstallFailed` status. Policy:
- Retry: NOT automatic. The host clicks "retry install" in the tray UI, or a subsequent daemon run picks up the node (re-checks capability, gets another chance at install).
- Skip: optional requirements skip silently; required fail the node.
- Bid return: yes, this IS a bid return — the paid market already has this path from Phase G.

**Version drift during a run.** A node that starts with Unreal 5.4 and discovers mid-run the install was upgraded to 5.5: the node's handle to the Unreal process is still live; log the drift but don't interrupt. The NEXT preflight re-checks.

## 5. Auto-install policy + security (combined, because inseparable)

### Host-level setting — host-decided 2026-04-15

**Default: `always`.** Auto-install and auto-update without per-install prompts. The approval gate is software-level (you approved Unreal Engine → all installs and updates of Unreal Engine proceed without further prompts). Revocation is the control surface: remove approval → future installs refuse; existing install stays until explicitly uninstalled.

```yaml
# ~/.tinyassets/config.yaml or host settings
capability_policy:
  install_mode: always            # always | ask | never. Host default: always.
  update_mode: always             # always | ask | never. Host default: always.

  approved_software:              # per-software, persistent, host-level trust
    - id: unreal_engine
      approved_at: 2026-04-15T14:30Z
      approved_by: jonathan
      # revoke by removing this entry; future install/update calls refuse
    - id: ollama
      approved_at: 2026-04-15T14:31Z
      approved_by: jonathan

  per_capability_overrides:       # exceptional cases — a single software
    blender:                      # treated differently from the global mode
      install_mode: ask

  trusted_publishers:
    - epic_games
    - anthropic
    - meta                         # Ollama ships upstream
  untrusted_publisher_policy: reject   # reject | ask_with_warning

  sandbox:
    during_install: isolated
    post_install: system
```

**The `approved_software` list is the host's software-trust profile.** First time a daemon needs `unreal_engine`, host is asked once (modal prompt; not the tray, this is load-bearing consent). After approval, `install_mode: always` takes effect — future installs + updates proceed without prompts. Revocation removes the entry; the next install attempt asks again or refuses based on `install_mode`.

**Why this shape matches host intent:** zero-friction when a trusted daemon wants to install a trusted software; unambiguous revocation story; approvals accumulate as a durable profile that travels with the user's config (can be reviewed, exported, version-controlled).

### Security layering (multi-layer by design — single layer fails catastrophically)

1. **Capability handler is signed code.** Handlers ship with the daemon bundle, signed as part of the release. A third-party handler would require a future "install capability handler" flow — out of MVP scope. In MVP, only bundled handlers exist.
2. **Binary signature verification.** Before install, the handler verifies the installer binary's publisher signature (Authenticode on Windows, codesign on macOS, GPG on Linux). Signature mismatch = install rejected regardless of auto-install setting.
3. **Allow-list per universe.** A universe can declare `allowed_capabilities: [unreal_engine, ollama]`; nodes running in that universe can only use capabilities on the list. Corporate universes use this hard. Public universes default to "all bundled capabilities allowed"; host-restricted universes set a tighter list.
4. **Per-software approval gate (host-decided 2026-04-15).** Host approves each software once; approval is persistent and host-level (not per-branch-version, not per-node-instance). First time any node needs Unreal Engine, host sees a modal "approve Unreal Engine for daemon use?" — one click. Subsequent nodes, installs, and updates proceed without prompts as long as the approval holds. **Revocation is the control surface** — remove the approval entry, future invocations refuse.
5. **Subprocess isolation during invoke.** Phase G's `node_sandbox.py` already isolates node code execution. Capability invocations are subprocesses *of* the sandboxed node — they inherit the sandbox's constraints (cwd, env, resource limits). Upgrading to VM/container isolation is a future concern for zero-trust capabilities (e.g. user-submitted unsigned binaries); MVP sticks with subprocess.

**The multi-layer principle:** any single layer failing doesn't breach the system. Unsigned binary passes signature check? Universe allow-list still rejects. Universe allows? Per-software approval still refuses. Approval granted? Sandbox still constrains. Five layers, any one holds. **Donation (§7 Shape IV) moves bits across layer 2 — it does not bypass any layer; signature verification applies to donated installers identically.**

### What the security model does NOT do (MVP)

- No full container isolation. Out of scope for MVP; flagged for Phase 2+.
- No per-invocation resource quotas (CPU / RAM / GPU caps per capability call). Out of MVP.
- No audit-log export to an external SIEM. The `capability_install_log` is local.

## 5.5. New node type: `external_tool_node` (explorer-recommended seam)

Explorer scout surfaced that all three current execution paths (prompt-template, source-code-sandboxed, NodeBid exec-pattern-scanned) **specifically prevent external-binary launches** — Phase G's threat model is load-bearing on that restriction. Poking a hole in `tools_allowed` re-litigates that threat model; a clean new node type does not.

**Introduce `external_tool_node` as a fourth execution path.** This type:
- Declares `required_capabilities` as its defining field.
- Bypasses Phase G's Python exec-pattern-scan (it's not Python exec'ing; it's subprocess-of-declared-binary).
- Inherits Phase G's **approval gate** — `approved=True` is mandatory. Host reviews the manifest (which binaries, which capabilities, which universe) as code-review before first run.
- Runs inside `tinyassets/node_sandbox.py`'s subprocess wrapper — the sandbox is the execution container for the node's orchestration code; capability invocations are child subprocesses inheriting the sandbox constraints.
- Cannot coexist with prompt-template or source-code execution in the same node. A node is exactly one of these four types.

### Authoring surface

```python
# NodeDefinition (conceptual; actual shape from tinyassets/branches.py:101-150)
class NodeDefinition(TypedDict):
    node_def_id: str
    kind: Literal["prompt_template", "source_code", "external_tool", "node_bid"]
    required_capabilities: list[str]    # NEW field, required for kind="external_tool"
    # ... existing fields
```

Validation:
- `kind == "external_tool"` REQUIRES `required_capabilities` non-empty.
- `kind != "external_tool"` rejects `required_capabilities` entries that aren't LLMs/MCP-tools (silent-drift guard). Non-external nodes can still request LLMs via the existing `required_llm_type` field.

This cleanly separates "node invokes external software" from the three paths that don't.

## 6. Daemon-to-software invocation patterns

Three invocation shapes, chosen per capability handler:

### Pattern A — Subprocess with stdin/stdout

Default for CLI tools (`ollama run`, `python script.py`, `ffmpeg`). Handler's `invoke()` returns a `subprocess.Popen`-like handle; node writes to stdin, reads from stdout, waits for exit. Node_sandbox precedent covers this.

**Use for:** Ollama, Python scripts, ffmpeg, most scientific tools, CLI binaries.

### Pattern B — Subprocess with file-based IPC

For GUI software that doesn't talk via pipes. Node writes request files to a watch folder; software reads; software writes response files; node polls. Slow, but universal.

**Use for:** Blender background rendering, Visual Studio build targets, any "run this project file" GUI.

### Pattern C — UI automation driver

For software the daemon needs to *interactively drive* (playing a game, clicking through an editor). Handler returns a driver object wrapping `pyautogui` / `pywinauto` / platform-specific automation. Node scripts the UI.

**Use for:** Unreal Engine editor (the MVP target if the node builds a game inside the editor), Unity editor, GUI games. High fragility; fall back to Pattern B whenever possible.

### Invocation → node_sandbox relationship

The node itself runs inside `tinyassets/node_sandbox.py`'s subprocess. Capability invocations are subprocesses *from* that sandbox. Resource inheritance: the sandbox's `cwd`/`env`/`limits` cascade to child invocations. The capability handler's `invoke()` is called with these as positional args.

**Default isolation posture:** subprocess-of-subprocess. Fast enough, matches Phase G. Container/VM posture is future.

### Phase G approval gate generalizes directly

Explorer called out `bids/README.md:52-128` as the security precedent: three-layer defense (approval + pattern-scan + input-shape), with *"the approval gate is the real boundary."* Host reviews source code before first run; approval is code-review.

Generalization for external_tool_node: **host approves the node's manifest** — the `required_capabilities` list, the author, the universe — before first run. "Does this node want Unreal Engine? Yes, and it's part of a video-game branch I authored. Approve." Approval is remembered per-branch-version (per §5 recommendation).

Pattern-scan doesn't apply — there's no Python source for the host to scan. Input-shape still applies (the node's arguments passed to invocations are structured/typed). The approval gate bears more load in the external_tool_node case, which is why universe-level allow-lists and per-capability settings matter as defense-in-depth per §5.

## 7. Multi-computer resolution

**Host direction:** "this could be all on the fly… so whatever software people want to give the daemon access to." Multi-computer is implied but underspecified.

**Explorer scout:** multi-host capability is already modeled in a narrow sense — market-level multi-host via shared git `bids/` with `served_llm_type` filter. Extension to `served_capabilities: [claude-opus, unreal_engine-5.4]` is natural — same shape, list instead of scalar. **What is NOT modeled today: cross-host hopping** (Computer X needs Unreal AND Ollama, only Y has Unreal, only Z has Ollama). Single-node-needing-multiple-capabilities-split-across-hosts is the unresolved hard problem.

Three product shapes (each viable; different capital/complexity):

### Shape I — Refuse-on-miss (MVP default)

Daemon on Computer X picks a node requiring Unreal. X doesn't have it. Node's bid **returns to pool**. Any other daemon (same user's install on Computer Y, or different user entirely) eligible to pick it up if they have the capability. Daemon X sees "capability missing, returned bid" in its log; host sees it in the tray UI.

- **Pros:** zero new infra. Uses existing bid-market.
- **Cons:** requires the user already has multiple daemons + shared branch/goal; a single-computer user sees "can't run, install Unreal yourself."
- **MVP verdict: ship this.** Clear failure mode, no new concepts.

### Shape II — Remote-invoke bridge (DEPRECATED 2026-04-15)

~~Daemon X runs the node's Python logic locally, but capability invocations route over the network to a "capability server" on Computer Y.~~

**Host deprecated this shape 2026-04-15.** Same problem-space as "let another daemon run the node" — already solved by Shape I's bid-routing. Shape IV (software donation) solves the actual itch: help hosts acquire software they need, don't federate every invocation across the network.

### Shape III — Daemon migration

Daemon X serializes its state mid-node-run, ships to Y, resumes. LangGraph's checkpointing primitive could support this in principle.

- **Pros:** feels magical.
- **Cons:** serialization of live subprocess state is generally hopeless. Migration mid-Unreal-render = impossible.
- **MVP verdict: never, or much later.** Don't scope.

### Host-decided 2026-04-15: Shape I-strict for node routing + Shape IV for software donation

Remote daemon-invocation (Shape II) is explicitly **deprecated** — it's the same problem as "let other daemon run the node," solved by Shape I's bid-routing. Cross-host software-donation (Shape IV) IS worth building.

### Shape IV — Peer-to-peer software donation (NEW, host-directed 2026-04-15)

Host A has Unreal installer cached. Host B's daemon picked a node requiring Unreal but B doesn't have it. Instead of B downloading from the internet, B asks A for the installer. A sends the bits; B installs locally.

**Why this is worth building separately from Shape I-split:**
- Shape I-strict says "B can't run this node." Shape IV says "B can run this node, once A helps B get set up." Different economics: donation is one-shot (install once, run forever); remote-invoke is per-call.
- Software downloads are the slow path. Peer-to-peer sharing in a multiplayer set (family members, coworkers, friends) is natural and useful regardless of workflow.
- The trust surface is well-defined: donation transports bits; full security layer stack (§5) still evaluates them on the receiving host.

**Protocol shape (MVP):**

1. **Donation manifest** — per-host, sibling of `hosts/<host_id>.yaml`:

   ```yaml
   # hosts/<host_id>.yaml
   host_id: jonathan-desktop
   served_capabilities:
     - id: unreal_engine
       version: "5.4.4"
       install_path: "C:/..."
   donations_offered:
     - id: unreal_engine
       version: "5.4.4"
       installer_path: "C:/installers/UnrealEngine-5.4.4-Installer.exe"
       publisher_signature: "epic_games"     # must match trusted_publishers to be useful
       size_bytes: 2147483648
       sha256: "abc123..."
   ```

2. **Discovery** — shared via the same `bids/` git path the market uses (per explorer §5 scout). Every host committing its YAML publishes what it can donate.

3. **Request protocol** — Host B's preflight sees missing Unreal; checks `donations_offered` across the peer set; picks a host that offers it with a matching signature. Writes a donation-request to git or a direct-file-transfer channel (MVP: git — slow but zero new infra; if git LFS not configured, donation-request is the file's direct URL and transfer is over HTTP/filesystem). Host A sees the request, copies the file to a pickup location, notifies B.

4. **Receive + verify on B** — Host B runs full security stack:
   - Signature check (same as fresh-download).
   - `sha256` check against donation manifest.
   - Per-software approval gate (§5 layer 4) still applies — first-time Unreal still asks B for approval; donation doesn't auto-approve.
   - Universe allow-list still applies.

5. **Install proceeds locally** — B runs the installer via the handler as if it had been downloaded from the internet. Registry updates; capability becomes served on B.

### Shape IV MVP scope

- Donation manifest (YAML extension).
- Discovery via existing `bids/` git path.
- Simple request-pickup protocol (git-based for MVP; direct-transfer post-MVP).
- Full security stack on receive (reuses §5 layers 2+4+universe-allow-list; not new code).

**What's out of Shape IV MVP:**
- Large-file transfer optimization (Unreal installers are multi-GB; MVP accepts slow git-based transfer as the price of zero-new-infra).
- Bandwidth throttling on the donating host.
- Donation trust-reputation (did Host A donate clean bits last time? MVP trusts publisher signature only).
- Cross-universe donation preferences.

### Shape IV effort

~1-2 additional dev days on top of MVP baseline. The heavy lifting is the donation-manifest YAML and the request-pickup loop; security reuses §5.

### Shape I-strict stays for node routing

Node still refuses to run on a host that doesn't serve its capabilities (post-installation). Shape IV solves the "get the software" problem; Shape I-strict governs "where does the node run." Combined flow: Host B's daemon picks a node; B is missing a capability; B requests donation from A; A donates; B installs; B runs the node. No cross-host per-invocation routing.

### Unresolved: multi-capability-per-node across hosts (unchanged)

If a node requires `[unreal_engine, specialized_mocap_software]` and no peer donates the mocap software, Shape IV doesn't help — Shape I-strict still says "no host matches, bid sits." This is accepted MVP limitation; user-sim will surface demand.

## 8. MVP scope

**Single user-sim mission acceptance:** a daemon on the host picks a `video_game_workflow` branch, one of its nodes requires Unreal Engine 5.4+, the registry detects the host's existing install, the node runs an Unreal Engine headless build via Pattern A or B, artifacts land in the universe's output dir.

### Critical-path scope (MVP) — revised 2026-04-15 post host §10 answers

1. **NodeDefinition schema: add `required_capabilities: list[str]` + `capability_pattern: str`** as siblings of `dependencies` at `tinyassets/branches.py:101-150`.
2. **DispatcherConfig schema: add `served_capabilities: list[str]`** at the config site (explorer to name the exact line post-claim).
3. **Dispatcher filter extension** at `tinyassets/dispatcher.py:230-238` — one-line set-inclusion check per §3 above.
4. **Host-capability YAML** at `hosts/<host_id>.yaml` — hand-maintained. Extended with `donations_offered:` (Shape IV).
5. **New node type `external_tool_node`** — §5.5. Bypasses Python sandbox; inherits approval gate; invokes declared binaries via CapabilityHandler.
6. **`CapabilityHandler` protocol + TWO invocation patterns + two handlers:**
   - `UnrealEngineHandler` implementing BOTH Pattern B (headless builds) AND Pattern C (UI automation via pywinauto/pyautogui). Pattern C is the default per node's `capability_pattern`. **This is the most expensive MVP item** — UI automation is fragile and Unreal Editor is a big surface.
   - `OllamaHandler` — Pattern A (subprocess pipe) only. Pattern C not meaningful for CLI tools.
7. **Per-software approval gate.** Reuse Phase G's `approved=True` mechanism but widen the scope object: approval is per-software-id, persistent, stored in `capability_policy.approved_software`. First-time modal prompt on a daemon needing unapproved software; subsequent installs/updates proceed with `install_mode: always`.
8. **Auto-install + auto-update.** Handler `install()` runs automatically when the node preflight finds a missing or out-of-version capability AND the software is approved. Manual revocation via host config edit or a future MCP tool.
9. **Shape IV software-donation manifest + request-pickup protocol.** Per §7 Shape IV. Adds ~1-2 days on top of baseline.
10. **Shape I-strict dispatcher behavior.** Missing capability (post-donation-attempt) = bid doesn't match host, stays in pool.
11. **MCP tools:** `capabilities action=list|approve|revoke|request_donation`. The `approve` and `revoke` verbs make the approval surface first-class.

### Explicitly out of MVP

- **Auto-detect** (scanning host for installed software). MVP reads hand-maintained host YAML.
- **Auto-install is now IN MVP** (host decision reversal from initial draft). Install handler fetches + runs the installer when a capability is missing AND approved.
- **SQLite cache for capabilities.** YAML is enough for one user's one host; DB cache is post-MVP.
- **Pattern C is now IN MVP** (host decision reversal from initial draft). Unreal Engine handler ships with UI-automation support.
- **Shape II remote-invoke: deprecated entirely**, not just deferred.
- **Shape I-split** (a node decomposing across multiple hosts): deferred.
- **Shape IV advanced features:** large-file transfer optimization, bandwidth throttling, donation reputation.
- **Third-party capability handlers.** Bundled-only.
- **Publisher signature verification for in-bundle handlers.** Bundled handlers ARE the trust root. Handler-signature-check is §5 layer 1; binary-signature-check on installers (§5 layer 2) IS in MVP and is load-bearing for Shape IV.
- **Universe-level allow-list.** MVP = all bundled handlers allowed in any universe.
- **Resource quotas.**

### MVP effort estimate — revised 2026-04-15 post host §10

**~7-10 dev days.** Pattern C + auto-install + Shape IV push this back up from the 3-5 day explorer-aligned estimate.

- **Day 1:** NodeDefinition `required_capabilities` + `capability_pattern` fields, DispatcherConfig `served_capabilities`, dispatcher filter extension, host YAML loader including `donations_offered`. Template tests from `required_llm_type` suite.
- **Day 2:** `external_tool_node` node type, validation (pattern-handler-compatibility check at registration), integration with node-kind dispatch.
- **Day 3:** `CapabilityHandler` protocol supporting all three patterns (A/B/C). `OllamaHandler` Pattern A implementation. End-to-end smoke: node declares ollama dep, daemon picks, Ollama runs.
- **Day 4:** `UnrealEngineHandler` Pattern B (headless builds). Windows paths + Unreal's `UnrealBuildTool` CLI quirks eat the day.
- **Day 5-6:** `UnrealEngineHandler` Pattern C (UI automation via pywinauto/pyautogui). **This is the risky segment.** UI automation on Unreal Editor is fragile; expect to descope to "click through one deterministic scenario" for MVP acceptance. Document what works, what doesn't, what needs Pattern B fallback.
- **Day 7:** Auto-install flow — installer download, signature verification, handler `install()` invocation, registry update. `capability_policy` file schema + first-use modal prompt for approval.
- **Day 8-9:** Shape IV — `donations_offered` manifest, discovery via `bids/` git path, request-pickup protocol, receive-side security layer verification (reuses §5 layers 2 + 4).
- **Day 10:** MCP tools (`list|approve|revoke|request_donation`), polish, end-to-end tests, user-sim dry-run.

**Risk on Pattern C:** UI automation is inherently flaky. If day 5-6 reveals that Unreal Editor automation can't hit a reliable user-sim demo, fall back to Pattern B for Unreal and document Pattern C support as "framework only, no fully-automated game" until a cheaper target (e.g. a Minecraft-world-editor) proves the Pattern C pipeline end-to-end. **Flag to host at day-5 checkpoint.**

## 9. PLAN.md alignment

Two sections:

**§Engine And Domains (L210):** this IS a domain-extension mechanism. The engine provides the capability-resolution framework; domains declare their required capabilities; new domains (fantasy-videogame, scientific-computing, corporate-Excel) consume the framework without the engine needing per-domain code. Directly matches "engine stays lean; domains carry their own weight."

**§Distribution And Discoverability (L186):** capability handlers are a distribution concern — bundled handlers ship with the daemon, new handlers are a future distribution channel. Tie-in: the packaging auto-build from `tinyassets/` (per `2026-04-14-packaging-mirror-decision.md`) will include `tinyassets/capabilities/handlers/` in the bundle. Five-dep surface unchanged; handlers are pure Python that subprocess out.

**§Multiplayer Daemon Platform (L102):** "public attributable actions." Software invocation is exactly the kind of action that should be attributable — who ran Unreal on whose universe. The `capability_install_log` contributes this.

**New principle to propose for PLAN.md** (flagged for host approval): **"The daemon's software surface is declarative, host-registered, and multi-layer-authorized."** Rationale: elevates this from an implementation detail to a cross-cutting principle so future domain work inherits the posture.

## 10. Open questions

### 10.1 Host-answered 2026-04-15

**Q1 — Unreal Engine invocation pattern for MVP. ANSWERED: per-node choice, Pattern C (UI automation) default.** Pattern B also in MVP. Each node's `capability_pattern` field picks; `ui_automation` is the default because it's closest to the actual user experience. Both patterns mandatory in MVP.

**Q2 — Auto-install policy default. ANSWERED: `always`.** Installs and updates proceed without prompts, subject to per-software approval. Approval is the trust surface; install is friction-free once the software is approved. Revocation via host config is the granular control.

**Q3 — Approval granularity. ANSWERED: per-software, persistent, host-level.** Not per-branch-version, not per-node-instance. Host sees a modal on first-time-needed, approves once, the approval persists until revoked. Revocation = remove the entry from `capability_policy.approved_software`.

### 10.2 Still open (non-blocking)

4. **Capability handler location.** Recommend `tinyassets/capabilities/handlers/` per §3. Alternative: a plugin dir for third-party handlers. Defer third-party.
5. **Version spec syntax.** Recommend PEP 440 (pip's syntax). PEP 440 is weirder for software that uses semver (Unreal is semver-ish); let handlers normalize internally.
6. **Host YAML location.** Recommend `hosts/<host_id>.yaml` (at repo root, version-controlled per Phase 7 direction). Alternative: per-user `~/.tinyassets/hosts/`. Phase 7 direction suggests repo-root.
7. **Tray UI integration.** Phase H tray shows daemon status. Recommend adding a "Capabilities" panel listing served capabilities, pending approvals, donation offers/requests. Defer if Phase H merge still volatile.
8. **PLAN.md principle approval.** §9 proposes a new PLAN.md principle ("The daemon's software surface is declarative, host-registered, and multi-layer-authorized"). **Not yet explicitly approved by host** — PLAN.md changes require explicit sign-off per AGENTS.md. Flagging for host confirmation before dev-promotion.
9. **Pattern C fallback criteria.** If UI-automation on Unreal Editor proves too flaky during Day 5-6 implementation (§8), what's the fallback — defer Pattern C support for Unreal specifically, or defer all of Pattern C from MVP? Recommend: keep Pattern C in the handler protocol + ship one Pattern C reference integration (maybe a simpler software target) + document Unreal Pattern C as "best-effort" if it's fragile. Day-5 checkpoint with host to decide.
10. **Shape IV donation-request discovery latency.** Git-based discovery means a daemon sees new donation offers at sync cadence. A daemon preflight-blocked on missing capability waits until next sync. Recommend: MVP accepts this; document latency. Post-MVP: direct peer signaling.

### Explorer-confirmed 2026-04-15 (scout #36)

- **Existing pattern IS the template:** `required_llm_type` / `served_llm_type` + dispatcher filter at `tinyassets/dispatcher.py:230-238`. Generalize to list. Confirmed.
- **NodeDefinition has no binary-requirements field today** (`tinyassets/branches.py:101-150`). `tools_allowed` exists but is stub — declared + unenforced. Clean add site for `required_capabilities`.
- **All three execution paths prevent external binaries** (prompt-template, source-code-sandboxed, NodeBid exec). Escape seam = new `external_tool_node` type (explorer preferred; planner agreed — §5.5).
- **Phase G approval gate is the security precedent** (`bids/README.md:52-128`). Host approval = code review. Generalizes cleanly to capability-manifest approval.
- **Multi-host capability routing exists at market level** via shared git `bids/`, but **cross-host per-node splitting is unresolved**. I-strict MVP posture documented.
- **`_producer_sandbox_reject`** at `tinyassets/producers/node_bid.py:44-81` is the "declare-then-resolve" code pattern to mirror.

### Remaining explorer scout items (non-blocking)

- Exact line for DispatcherConfig `served_capabilities` addition (explorer to point when dev claims).
- Whether `bids/` git path is still canonical post Phase 7 GitHub migration.

## 11. Landing sequence

MVP lands AFTER:
- Memory-scope Stage 2 (`branch_node_scope.yaml` has to exist for `requires:` to live on it).
- Packaging Option 1 (so the MVP can actually reach users when it lands — no point building capability system into a broken bundle).

MVP lands BEFORE:
- Any user-sim mission involving Unreal or external software.
- Marketing / viral launch referencing "daemons can play games."

Post-MVP follow-on sequence:
1. Third-party handler plugin dir.
2. Publisher signature verification.
3. Universe-level allow-list.
4. Pattern C (UI automation) for Unreal / Unity.
5. Multi-computer Shape II (remote-invoke bridge).
6. Resource quotas.
7. Container isolation posture.

Each post-MVP item is independent and claimable. Flagging Pattern C as the one with the largest user-experience payoff after MVP — "daemon plays Minecraft" is the demo that sells the viral story.
