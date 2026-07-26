# Engine OS Sandbox: Current-Main Opus 5 Reconciliation Audit

**Date:** 2026-07-25

**Status:** preliminary independent review; `ADAPT`; not an implementation approval

**Scope:** PR #1573 and the smallest spec-only in-place supersession of
`openspec/changes/engine-os-sandbox/`

**Runtime/build authority:** **none**

## Executive verdict

PR #1573 must not merge in its current form. Retain the change ID
`engine-os-sandbox`, but replace its Bubblewrap-specific proposal in place with
a backend-neutral execution-admission contract.

The current runtime has several distinct failures that the draft collapses into
one:

1. availability diagnostics are consumed as if they were authority or
   attestation;
2. user-controlled code runs in-process with full Python builtins or in a
   same-principal subprocess with no filesystem or network boundary;
3. the proposed whole-universe workspace projection includes credential and
   provider-private subtrees;
4. provider and credential refusals are caught as fallback signals;
5. the proposed Bubblewrap policy shares the full host network; and
6. missing explicit universe context can select maintainer subscription state
   or the wrong ambient universe.

The right correction is admission before provider/backend selection, followed
by independently attested containment. Provider authority, credential custody,
egress enforcement, and backend implementation remain with their current
owners.

This audit records a **preliminary `ADAPT`**, not final Opus 5 approval. The
supplied Opus artifact is strong on C1-C4 and C6-C8, but its C5 owner statement
is contradicted by the exact revision it says it reviewed: merged #1784 already
modifies the Bubblewrap requirement. A fresh opposite-provider review of the
rewritten exact SHA is therefore still mandatory.

## Freshness and evidence stamp

Evidence was re-read on Windows in
`C:\Users\Jonathan\Projects\wf-engine-os-sandbox-reconcile` at
`2026-07-25T23:09:35-07:00`.

| Surface | Fresh evidence |
|---|---|
| Current main | `git fetch --prune origin`; `origin/main=d454a5c5108ad2a4eda70201811640849e25e15b`, committed `2026-07-25T22:53:50-07:00` (`spec: bind authenticated host principal to account (#1753)`). |
| Audit worktree | Local `HEAD=0d32638bc8b10f2621d14992af0bca1e6f2f2652`, a coordination-only claim commit above current main. Existing `.claude/.fleet_*` edits were present and were not touched. |
| PR #1573 | GitHub metadata read `2026-07-25`: open draft, head `3de45c576ac27bc2c011fe410bacbea4bf732b0e`, historical base OID `2b9639a30d55222bca9ac78c0057d6c08c50cb6e`, updated `2026-07-26T02:46:37Z`. Diff is 164 additions across the five files under `openspec/changes/engine-os-sandbox/`; no runtime or tests. |
| Provider-authority owner | PR #1784 merged as `620fed5acf17d23717ccebd3811cb4c741e16b1a` at `2026-07-25T21:39:47-07:00`; `git merge-base --is-ancestor` confirms it is in current `origin/main`. Its active, unarchived change is `openspec/changes/constrain-set-engine-provider-authority/`. |
| Supplied Opus artifact | `C:\Users\Jonathan\AppData\Local\Temp\tinyassets-opus5\sandbox-successor-result.md`, 111 lines, says it reviewed `origin/main@b759682f`. Current main is 14 commits ahead. A path-limited `git diff b759682f..origin/main` over every runtime/spec file reviewed here was empty. |
| C5 contradiction | `git show b759682f:openspec/changes/constrain-set-engine-provider-authority/specs/provider-routing/spec.md` already contains `Requirement: Bubblewrap readiness...` and calls the probe a CLI-readiness heuristic. This is not later drift; it is an error in the supplied C5 owner conclusion. |

Commands used as evidence included `gh pr view 1573/1784 --json ...`,
`gh pr diff 1573 --patch`, exact `git show`/ancestry/diff checks, scoped
`docview.py` reads, and line-targeted `rg` over the files named below. No tests,
runtime, deployment, sync, archive, commit, or push were run or authorized by
this audit.

## Terms that must not be collapsed

| Term | Meaning | What it is not |
|---|---|---|
| **Diagnostic** | A fallible observation such as “a minimal bwrap probe succeeded on this host.” | Permission, workload admission, backend selection authority, or proof the launched workload used that backend. |
| **Authority** | Proof that this requester/background owner may spend this compute and use this exact provider binding for this universe and operation. | Filesystem/network containment. |
| **Admission** | A trusted pre-launch comparison between an immutable `ExecutionRequirement` and a current execution profile/attestation. | The containment mechanism itself. |
| **Containment** | The enforced process/principal/filesystem/network/resource boundary around the actual workload. | A cached host diagnostic, CLI flag, cwd pin, denylist, or authority grant. |
| **Attestation** | Request-bound evidence emitted by the backend that actually enforced the admitted profile. | “bwrap is installed” or a mutable process-lifetime dictionary. |

Authority can be valid while containment is absent. Containment can be strong
while the caller has no authority to spend it. Admission must require both
where the workload needs both.

## Current-main findings

### 1. Diagnostics currently influence security decisions

`tinyassets/providers/base.py:834-896` probes Bubblewrap once, caches the
result for process life, returns the same mutable dictionary, and never binds
the diagnostic to a subsequent launch.

Two current consumers give the diagnostic more meaning than it has:

- `tinyassets/providers/codex_provider.py:115-120` selects `--full-auto` when
  the diagnostic is truthy and
  `--dangerously-bypass-approvals-and-sandbox` when falsey.
- `tinyassets/authoring/sandbox.py:422-464` reports
  `level="os_isolated"` solely from `bwrap_available` and admits
  `requires_os_isolation=True` on that basis.

The second path is a positive false attestation. Authoring then executes code
through `NodeSandbox` (`tinyassets/authoring/service.py:542,700-777`), not
through Bubblewrap. A host with bwrap installed can therefore claim OS
isolation for a workload never launched under it.

### 2. User-controlled code has full builtins and no OS containment

- Graph `source_code` uses `{"__builtins__": __builtins__}` and
  `exec(src, namespace)` in-process
  (`tinyassets/graph_compiler.py:1806-1810`).
- NodeBid independently does the same
  (`tinyassets/executors/node_bid.py:175-177`).
- The canonical graph spec states this limitation explicitly:
  `openspec/specs/graph-execution-substrate/spec.md:77-91`.

The approval hash and substring scans are admission-like checks over source
text. They are not containment.

### 3. `NodeSandbox` is crash isolation, not a security principal

`tinyassets/node_sandbox.py:293-303` launches
`sys.executable -c <runner>` as the same OS user with a shortened environment.
It does not change uid/gid, mount namespace, or network namespace, and it sets
no OS resource limits. Its child still receives full Python builtins
(`:141-164`). The import allowlist includes `requests` and `httpx`
(`:74-82`), so the subprocess has ordinary host-network reach.

Timeout, output cap, import filtering, and state-key filtering are useful
process controls. They do not establish an OS trust boundary.

### 4. The draft's workspace bind exposes whole-universe private state

PR #1573 `design.md` proposes one read-write bind of the resolved universe
directory at `/workspace`, then claims credential/vault paths are not bound.
Those statements cannot both be true:

- `.credential-vault.json` and `.credentials/` live directly under the
  universe root (`tinyassets/credential_vault.py:16-17,70-72,101`);
- materialized Claude/Codex auth defaults to
  `<universe>/.credentials/<service>`
  (`tinyassets/providers/base.py:245-253`); and
- provider child homes/config/runtime live under
  `<universe>/.runtime/provider-child/<provider>`
  (`tinyassets/providers/base.py:276-318`).

A recursive RW universe bind exposes all of those paths to the child. The
draft also acknowledges that the provider credential placed in the child
environment is visible to the model-controlled process. A closed workspace
projection must therefore be an explicit allowlisted artifact projection, not
the universe root minus a prose denylist.

### 5. Missing explicit universe context can expose ambient authority

`tinyassets/graph_compiler.py:217-248` calls
`call_with_policy_sync(...)` without a `UniverseContext`.
`tinyassets/providers/router.py:296-297,618-620` consequently has no explicit
`universe_dir`. `subprocess_env_for_provider` then:

- uses ambient `TINYASSETS_UNIVERSE` if set; or
- when neither explicit nor ambient universe exists, returns
  `subprocess_env_without_api_keys() or os.environ.copy()`
  (`tinyassets/providers/base.py:346-362`).

The API-key stripping list does not remove subscription auth homes/tokens such
as `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, or `HOME`.
The result is either the wrong universe's vault or maintainer subscription
state. #1784 owns provider authority and credential eligibility. The residual
owned here is narrower: trusted execution call sites must derive and attach an
immutable execution requirement; an absent requirement is inadmissible.

### 6. Router fallback neutralizes provider-level refusal

In ordinary routing, `ProviderUnavailableError`, `ProviderError`, and then any
other `Exception` are converted into cooldown/diagnostic entries and
`continue` (`tinyassets/providers/router.py:449-493`). Policy routing repeats
the same shape and then falls through to the role chain (`:718-748`).

That catches:

- Codex's `sandbox_workspace=True` refusal, which is a `ProviderError`
  (`tinyassets/providers/codex_provider.py:101-112`);
- provider credential-resolution failure, which is
  `ProviderUnavailableError` (`tinyassets/providers/base.py:398-405`); and
- any future admission exception unless the router explicitly re-raises it
  before both broad handlers.

Provider-side “fail closed” is therefore only a fallback hint today. A terminal
route error taxonomy is required before any admission contract is meaningful.

### 7. Network is unrestricted

Current in-process and same-principal subprocess execution shares the daemon's
network. PR #1573 would add `--unshare-all` and immediately undo network
isolation with `--share-net`, deliberately sharing the full host network
namespace. That is neither “WebFetch only” nor scoped provider egress.

Egress scope belongs to `outbound-boundary-layer`. The sandbox admission lane
may require an egress profile/digest; it must not invent the proxy, grants, or
destination policy.

### 8. Canonical specs truthfully describe several unsafe as-built states

The supersession must explicitly reverse or hand off these current
requirements; it cannot layer aspirational prose beside them:

- `graph-execution-substrate`: “source_code nodes execute in-process behind a
  fail-closed approval gate” (`:77`) and “Branch sandbox demand is advisory
  metadata and never an execution gate” (`:354`).
- `provider-routing`: the Bubblewrap diagnostic selects ordinary Codex mode,
  including the dangerous bypass (`:241-286`).
- `universe-personification-and-relay`: the engine “sandbox” is a cwd pin plus
  deny-enumerated CLI tool policy, with true OS isolation explicitly deferred
  (`:69-78`).
- `distributed-execution`: `runner/v1` is a typed seam whose only built-in
  backend is unavailable; its detached sandbox diagnostic is not a runner
  backend (`:12-168`).

## C1-C8 disposition

| Finding | Current-main disposition |
|---|---|
| **C1 — do not duplicate #1784 authority** | **Blocking, confirmed.** Consume #1784's request/background authority, assignment ceiling, provider binding, and `ProviderAuthorityHeldError`. Engine admission owns only trusted derivation and attachment of `ExecutionRequirement` plus containment-profile matching. |
| **C2 — non-fallbackable exception taxonomy** | **Blocking, confirmed.** Admission/profile refusal needs a distinct terminal type (for example `ExecutionAdmissionError`) that router `call`, policy, ensemble, and bridge paths explicitly re-raise before `ProviderError`/`Exception`. Do not misclassify admission as provider failure, cooldown, exhaustion, or authority hold. `ProviderAuthorityHeldError` is the established sibling shape but is still spec-only: no runtime/test definition exists on current main. |
| **C3 — `inference_only` is never `JobCapability`** | **Required, confirmed.** It is an admission workload class only. `JobCapability` is closed in this lane at `source_exec`, `repo_read`, `repo_exec`, and `coding`; `CAPABILITY_ACTIONS` remains total over those four. |
| **C4 — precise schema freeze and tier ownership** | **Required, confirmed.** Freeze `JOB_REQUEST_SCHEMA_VERSION="runner-job/v1"` and `JOB_RESULT_SCHEMA_VERSION="runner-result/v1"` and their request/result wire shapes. `RunnerCapabilities` is an in-process backend report and may later carry an additive closed isolation tier. `EnforcementReceipt` is serialized inside `runner-result/v1` and must not gain that field here. Unknown/absent tiers deny; a boolean `isolation_enforced` cannot silently upgrade to a stronger tier. Engine admission defines the closed comparison semantics; distributed execution binds real backends to tiers. |
| **C5 — engine owns a narrow provider-routing delta** | **Security conclusion confirmed; owner conclusion refuted.** The dangerous Codex bypass must go and the probe must remain diagnostic-only. But merged #1784 already MODIFIES the exact Bubblewrap heading, at both `b759682f` and current main. A second engine-owned `provider-routing` delta would duplicate an active owner. #1784's sync owner/R2-1a must adapt that heading and runtime; engine admission records a dependency and consumes the result. |
| **C6 — include authoring false attestation** | **Required, confirmed.** Treat `isolation_report`/`require_isolation` as A0 because it makes a positive false claim. The active node-authoring owner must fix its requirement/runtime; this lane records the dependency and regression gate rather than taking a second authoring owner. |
| **C7 — address both graph requirements** | **Required, confirmed.** Add a `graph-execution-substrate` delta that modifies the two exact canonical headings, or explicitly defer each reversal to a named later change. Silent coexistence is invalid. |
| **C8 — fix present-tense fiction** | **Required, confirmed.** Delete the claim that `_sandboxed_config` already performs a Linux availability precheck. Current `tinyassets/universe_intelligence.py:97-113` builds only the model/tool config; no probe is called. |

## Smallest in-place supersession

Retain `openspec/changes/engine-os-sandbox/` and its historical
`created: 2026-07-22`. Replace the remaining artifacts as follows:

| Artifact | Smallest current-main action |
|---|---|
| `.openspec.yaml` | Keep unchanged. |
| `proposal.md` | Full rewrite around the confirmed execution/admission contradictions. Name #1784, node-authoring, credential custody, outbound boundary, and distributed execution as dependencies/owners. |
| `design.md` | Full rewrite. Delete the fixed Bubblewrap mount/namespace design, `--share-net`, runtime bind list, and backend-specific alternatives. Define workload/profile admission, exact closed workspace projection, terminal exception semantics, schema freezes, tier-owner split, and authority consumption. |
| `tasks.md` | Full rewrite. Reset old checked Bubblewrap audit tasks to unchecked because their artifact is deleted. Keep this lane spec/review only; remove runtime, push, deploy, sync, and archive claims. |
| `specs/universe-personification-and-relay/spec.md` | Rewrite the existing MODIFIED requirement under the exact canonical heading `The engine turn is confined by a fail-closed sandbox`, using backend-neutral admission and terminal semantics. |
| `specs/graph-execution-substrate/spec.md` | Add MODIFIED deltas for the two exact canonical headings identified in C7. |
| `specs/provider-routing/spec.md` | **Do not add.** #1784 already owns the affected heading. Record a Depends/handoff to its sync/R2-1a owner. |
| `specs/distributed-execution/spec.md` | **Do not add.** No distributed-execution delta belongs in this change. The runner/backend owner implements and attests tier binding after admission semantics are approved. |
| Any authoring delta | **Do not add.** The active node-authoring owner must repair its false attestation. |

The rewritten design should use an immutable trusted carrier such as
`ExecutionRequirement` with, at minimum:

- workload class;
- exact execution profile/policy digest;
- closed isolation requirement;
- closed workspace projection reference/digest;
- egress requirement reference/digest;
- credential-delivery class that never assumes a raw token may be exposed to a
  model-controlled child; and
- the authority evidence reference consumed from #1784, without re-defining
  that evidence.

`provider_cli` is an execution profile, not a workload class.
`inference_only` is a workload class and never a runner capability. A profile
must not become admissible by boolean coercion, unknown-tier defaulting, cached
host availability, provider fallback, or a provider's self-assertion.

## Exact owner boundaries

| Owner | Owns | Explicitly does not own here |
|---|---|---|
| `engine-os-sandbox` | Backend-neutral workload/profile vocabulary; trusted requirement derivation; admission comparison; closed workspace projection contract; terminal admission semantics; universe and graph requirement deltas. | Provider/credential authority; real backend; proxy/egress; credential brokerage; runtime changes. |
| `constrain-set-engine-provider-authority` / #1784 | Request/background compute authority, provider binding/ceiling, assignment generation, `ProviderAuthorityHeldError`, and the Bubblewrap heading already included in its active delta. | OS containment or workspace implementation. |
| R2-1a/provider-routing implementation owner | Remove diagnostic-driven Codex bypass; implement router re-raise ordering and preserve distinct authority/admission/exhaustion evidence. | Inventing execution authority or a backend. |
| `graph-execution-substrate` runtime owner | Derive requirements at graph/NodeBid call sites and stop in-process execution unless an admitted path exists. | Backend construction. |
| `distributed-execution` | Real backend implementations, backend self-test, current attestation, and binding each backend to the approved closed isolation tiers. | An engine-os-sandbox delta, provider authority, or changing frozen request/result schemas in this lane. |
| Node-authoring owner | Remove the false OS-isolation attestation and bind authoring tests to actual admitted containment. | Treating host bwrap availability as proof. |
| Credential-custody owner | Brokered/opaque credential delivery and closed projection of credential-private state. | Whole-universe RW mounts or raw model-visible credentials. |
| `outbound-boundary-layer` | Scoped egress grants, proxy enforcement, and evidence. | `--share-net` as a substitute for scoped egress. |

## Validation and review gates

### Before the spec-only supersession can be approved

1. Confirm every MODIFIED heading by exact grep against its canonical
   `openspec/specs/<capability>/spec.md`. Strict OpenSpec validation does not
   prove a MODIFIED heading exists canonically.
2. Prove the change contains:
   - no `specs/distributed-execution/spec.md`;
   - no `specs/provider-routing/spec.md` while #1784 owns the heading;
   - no new or changed `JobCapability`;
   - no change to `JOB_REQUEST_SCHEMA_VERSION` or
     `JOB_RESULT_SCHEMA_VERSION`; and
   - no runtime/test/build/deploy task checked or authorized.
3. Run `openspec validate engine-os-sandbox --strict`, then the repository's
   full strict OpenSpec validation.
4. Re-run provider-context and collision checks at the exact review SHA.
5. Obtain fresh opposite-provider review against current `origin/main` and the
   exact rewritten SHA. The reviewer must explicitly re-check C1-C8, including
   the C5 correction in this audit.
6. Host approval is required before promoting any runtime/build lane.

### Required runtime proof after a separately authorized implementation exists

These are future gates, not work authorized by this audit:

- terminal admission/authority exceptions are re-raised through ordinary,
  policy, ensemble, sync-bridge, and retry paths with zero fallback;
- missing execution requirement, missing/unknown tier, stale profile digest,
  or unbound workspace projection denies before provider/backend launch;
- graph `source_code`, NodeBid, authoring test, and tool-capable engine paths
  cannot reach in-process or same-principal-uncontained execution;
- `inference_only` remains outside `JobCapability` and cannot acquire tools,
  workspace, or execution actions through profile fallback;
- the Codex dangerous bypass is unreachable;
- a real backend proves the admitted filesystem, principal, network, resource,
  and cleanup boundaries against escape tests;
- the child cannot enumerate the whole universe, `.credential-vault.json`,
  `.credentials/`, `.runtime/provider-child/`, maintainer auth homes, or raw
  provider tokens;
- scoped egress proves allowed destinations and denies loopback, metadata,
  private-network, and undeclared destinations;
- mutation tests demonstrate each security gate can go red;
- focused, full, and §14 concurrency/load evidence is fresh; and
- an independent security review approves the exact runtime SHA before merge
  or rollout.

## Final classification

**Preliminary Opus 5 disposition: `ADAPT`.**

### Exact-candidate review round

Candidate `51f90c9e` passed structural verification (53/53 strict OpenSpec,
clean diff, exact canonical headings), but semantic review correctly returned
`ADAPT`:

1. accepted-market B2/B13 pre-routing could not be forced through ordinary
   `ProviderInvocation`/`ProviderExecutor`;
2. frozen inner `runner/v1` could not bind the complete requirement and
   backend evidence end to end;
3. isolation labels lacked enforceable property-set definitions;
4. a provider-owned exception did not cover runner/B2 admission; and
5. the engine lane over-specified credential/egress vocabulary.

The same Opus 5 pass also found that the reversed canonical
`source_code ... execute in-process` title requires an explicit
`RENAMED Requirements` entry, and that the advisory sandbox-demand
MODIFIED body must preserve shipped default/round-trip, diagnostic-warning,
and `runnable` behavior.

The successor candidate addresses those findings by using owner-native sealed
bindings of one logical requirement; a distributed-execution-owned outer
capsule keyed to the frozen inner `job_id`; property-set inclusion for
isolation; shared closed `ExecutionAdmissionError` semantics across
provider/runner/B2 paths; opaque owner-defined credential/egress references;
an explicit source-heading rename; and restored advisory behavior. A fresh
exact-head Opus 5 verdict remains required.

Candidate `b0ba1d60` then separated pre-launch admission from post-launch
validation of evidence for the actual execution. Independent verification
found one remaining wording contradiction: it still said pre-launch
capability/self-test evidence proved the *complete* guarantee set even though
that set includes actual launch, enforcement, cleanup, and result evidence.
The current successor therefore limits pre-launch proof to backend capability,
exact planned configuration, and a protocol commitment to return bound launch
evidence. Post-launch validation alone proves the complete guarantee set for
the exact execution before any output can become success or fallback input.
This correction is being restacked on current main `bc1227ee`; a fresh
exact-head Opus 5 verdict and independent verification remain required.

C1 and C2 are structural blockers. C3, C4, C6, C7, and C8 are required
corrections. C5's security requirement remains valid, but its proposed owner
boundary is corrected by current-main evidence: do not create a second
provider-routing delta.

This document is diagnostic evidence only. It does **not** approve an OpenSpec
rewrite, runtime implementation, backend build, test write, commit, push,
merge, sync, archive, deployment, or live acceptance claim.
