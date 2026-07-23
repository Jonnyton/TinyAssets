## Context

The production path implements Bubblewrap readiness inside
`tinyassets.providers.base`. `CodexProvider` consumes its once-per-process
cached dictionary to choose between `--full-auto` and
`--dangerously-bypass-approvals-and-sandbox`; Claude and Codex provider paths
also inspect subprocess stderr for four known sandbox-failure signatures.
Compiled graph nodes preserve the provider-layer exception and defensively
scan returned text for the same signatures.

Production deployment adds another consumer: after its public canaries,
`deploy-prod.yml` invokes `verify_llm_binding.py --require-sandbox` in both
auth-bundle branches and retries before preserving the verifier's final exit
code.

Branch metadata has a separate, weaker role. `requires_sandbox` round-trips,
drives list filters, and can produce a validation warning when the cached
probe is unavailable. It does not affect `runnable`, compile admission, or
runtime provider selection.

The repository also exports `tinyassets.sandbox.detect`, an uncached
Linux-only structured probe with a distinct status shape and exception class.
No production caller uses it. The canonical `distributed-execution` base owns
the adjacent `runner/v1` seam but explicitly has no usable OS backend or
production caller.

## Goals / Non-Goals

**Goals:**

- Give every sandbox-availability surface reconciled by this change an exact
  canonical owner.
- Make the production probe, diagnostic probe, and runner seam visibly
  distinct.
- Preserve failure-recognition and propagation behavior without claiming
  stronger fail-closed execution.
- Record user-visible readiness evidence and advisory branch disclosure.

**Non-Goals:**

- Build a usable OS-isolating `SandboxBackend` for `SandboxRunner`, Bubblewrap
  backend, container backend, or WSL2 backend.
- Add OS-level confinement to `converse`, prompt nodes, source-code nodes,
  paid-market jobs, or arbitrary subprocesses.
- Turn `requires_sandbox` into an admission or execution gate.
- Unify the two probe APIs or their exception classes.
- Fix fast-exit error ordering, mutable cache semantics, or dangerous-bypass
  selection.
- Modify the active `distributed-execution` or future engine-sandbox changes.

## Decisions

### Keep readiness, diagnostics, and execution as separate contracts

`provider-routing` owns the cached dictionary actually used by providers.
`distributed-execution` owns the detached exported diagnostic alongside its
unwired runner seam. The two APIs have different platform gates, return
shapes, exception classes, cache behavior, and exception handling, so the spec
must not describe a shared implementation that does not exist.

Neither readiness result is evidence of workload confinement. The production
probe only proves that a version command and a minimal Bubblewrap launch
succeeded; the diagnostic does the same without caching. The runner still has
no usable built-in backend.

### Specify Codex selection honestly

For ordinary calls, a truthy cached `bwrap_available` selects `--full-auto`;
every falsey result selects
`--dangerously-bypass-approvals-and-sandbox`. Founder-facing
`sandbox_workspace=True` calls refuse before this selection. The unavailable
path is therefore an explicit sandbox bypass, not fail-closed readiness.

### Bound fail-loud recognition by actual control flow

The provider helper recognizes four signatures case-insensitively on
non-win32 paths and raises the provider-layer `SandboxUnavailableError` with a
bounded excerpt and remediation. Provider completions call it only after
earlier quick-exit classification. A return-code-1 process that exits within
under five seconds can therefore become `ProviderUnavailableError` before the
sandbox recognizer runs. This ordering is part of the as-built limitation.

Graph code re-raises only the provider-layer exception before generic wrapping.
The separate diagnostic exception is not interoperable with that path.

### Treat requires_sandbox as disclosure metadata

Branch list and validation surfaces disclose declared sandbox demand, but
validation warnings are non-fatal and best-effort. Probe errors can suppress
the warning, while otherwise-valid branches remain runnable. Canonical text
must not repeat the warning's claim that marked nodes universally fail at
runtime, because compile and provider execution do not consume the flag and
ordinary Codex calls can bypass.

### Keep get_status best-effort and read-only

Full `get_status` assembly includes the cached provider probe under
`sandbox_status`. A probe exception is converted into an unavailable
dictionary with a `probe_error` reason so that lookup failure does not itself
abort assembly. Existing no-home, access-denied, and configuration-load
failures return earlier without the field. This extends the existing read-only
status contract; it does not make status a live health refresh or an
enforcement surface.

### Keep scheduled observation distinct from the production post-deploy gate

The scheduled LLM-binding canary intentionally reads only reported binding
status. The production deploy workflow separately invokes the same verifier
with `--require-sandbox`, twelve attempts, and a ten-second retry delay in both
auth-bundle branches. Missing or falsey readiness becomes verifier exit code 5;
a later green attempt recovers. This is post-deploy readiness evidence, not a
model execution or confinement proof.

## Risks / Trade-offs

- **[Risk] Readiness is mistaken for isolation.**
  → State the exact subprocess checks and every missing integration boundary.
- **[Risk] Advisory metadata is treated as a security gate.**
  → Normatively preserve unchanged validity/runnability and the absence of a
  compiler/runtime consumer.
- **[Risk] Duplicate APIs appear interoperable.**
  → Assign them to separate owners and name their incompatible shapes,
  exceptions, platform gates, and cache behavior.
- **[Risk] Canonical text freezes accidental error typing as stronger than it
  is.**
  → Record the quick-exit preemption explicitly.
- **[Risk] Future confinement PRs collide with this backfill.**
  → Modify only canonical as-built specs; treat active distributed-execution
  and PR #1573 as read-only future owners.

## Migration Plan

1. Strictly validate the five capability deltas.
2. Run focused provider, graph, branch, status, and diagnostic tests.
3. Verify runtime/plugin mirror parity and obtain independent
   requirement-to-source plus whole-diff review.
4. Rebase on current `origin/main`, sync only the approved deltas into their
   canonical owners, update the coverage audit, and validate the full tree.
5. Archive the change, merge the reviewed PR, and retire its STATUS claim.

There is no runtime rollout. Reverting the documentation commit is the rollback
if a clause is later shown to misdescribe shipped behavior.

## Open Questions

None. Fixing the recorded security limitations belongs in separately proposed
behavior changes.
