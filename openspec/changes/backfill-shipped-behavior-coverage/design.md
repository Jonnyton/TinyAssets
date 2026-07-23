## Context

PR #1616 established 24 canonical capabilities and identified seventeen groups of shipped behavior without complete canonical ownership. Several groups touch active changes or claimed runtime files. Four are independent and can be made truthful without choosing a future architecture:

1. incremental ASP validation;
2. the installed desktop GUI entry point;
3. coordination guard/mirror checks and JSON diagnostics; and
4. domain Branch-slug and episodic-coordinate registries.

The repository rule is as-built canonical OpenSpec. This change therefore records observable behavior and its limitations rather than converting implementation details into stronger promises.

## Goals / Non-Goals

**Goals:**

- Close four reverse-direction coverage gaps with source-grounded requirements.
- Preserve current failure, mutability, process-local, and packaging boundaries.
- Keep active credential, distributed-execution, connector, OKF, universe, effect, and runtime claims untouched.
- Leave a reproducible evidence map for independent review and later canonical sync.

**Non-goals:**

- Runtime or test changes.
- A one-click tray installer or cross-platform packaging guarantee.
- A persistent, transactional, or thread-safe domain registry.
- An alternate solver, minimal unsatisfiable core, or isolated per-scene ASP evaluation.
- A new coordination protocol or versioned JSON wire standard.

## Decisions

### 1. Backfill in dependency waves

Wave 1 owns only the four coordination-edge-free capabilities. The remaining thirteen groups stay in `backfill-shipped-behavior-coverage-wave2` and retain their active-change dependencies. This avoids a nominally documentation-only proposal racing the semantics of changes that are still being built.

### 2. Add requirements instead of rewriting already-grounded ones

The forward audit classified every existing requirement in these four capabilities as BUILT. The missing contracts are additive. The desktop capability already says that the source tray keeps its tunnel disabled unless explicitly enabled; this delta does not duplicate or weaken that requirement. It adds only the missing installed GUI-command fact.

### 3. State limitations at the requirement boundary

| Capability | Shipped contract | Limitation retained |
|---|---|---|
| `constraint-evaluation` | One Clingo control grounds base/world rules once, accumulates each scene in order, and emits one result after each addition. | Unsatisfied diagnostics inspect base/world text plus the current scene, not an exact solver core or a full prior-scene text snapshot. |
| `desktop-host-runtime` | `[project.gui-scripts]` publishes `tinyassets = tinyassets.desktop.launcher:main`. | This does not prove a packaged installer, a legacy `workflow` alias, or macOS/Linux tray packaging. |
| `development-coordination-runtime` | Cross-provider checks detect referenced missing guards and skill mirror absence/drift; claim, worktree, context, and drift tools emit JSON. | Checks diagnose and prescribe; they do not auto-repair. JSON is the current machine form, not a newly versioned external API. |
| `domain-plugin-runtime` | Process-local registries expose domain-owned Branch slugs and episodic coordinate shapes. | Registrations are mutable process memory, are not persisted or synchronized, and do not make shared episodic tables domain-specific. |

### 4. Treat a stale test as verification debt, not behavioral truth

`pyproject.toml` and PLAN's naming boundary establish `tinyassets` as the current GUI command. A stale test still requires `workflow`. The delta follows source and design truth, records that contradiction, and defers the test-only repair because another provider currently claims `tests/` broadly.

### 5. Sync only after independent review

The proposal validates as an isolated delta first. Canonical specs remain untouched until independent source/requirement review approves all four contracts. Sync and archive happen in the landing lane, atomically with STATUS retirement.

## Risks / Trade-offs

- **Risk: implementation details become accidental forever APIs.** Mitigation: requirements describe observable contracts and explicitly avoid internal class/layout guarantees except where the CLI or registry behavior exposes them.
- **Risk: active work invalidates a backfill before merge.** Mitigation: rebase and re-run the evidence map immediately before foldback; any changed behavior moves back to pending rather than being guessed.
- **Risk: JSON consumers infer a versioned schema.** Mitigation: require semantic parity and current record fields without claiming a compatibility/versioning policy that does not exist.

## Migration Plan

No data or runtime migration exists. After approval, sync the four additive deltas into `openspec/specs/`, run strict validation, archive the change, and delete the landed STATUS row in the same lane.

## Open Questions

None for Wave 1. Future schema versioning for coordination JSON, durable domain registries, and packaged tray installation require separate changes if their current limitations are replaced.
