# First usable file slice: isolated release inventory

Date: 2026-09-20. Builder worktree `run-input-file-custody/TinyAssets` contains
preserved experimental cloud ancestry. **Do not merge/push that branch wholesale.**
Root owns integration and release. Comparison target is reviewed shared foundation
`f65ceeb9`; retain its activation/recovery correction and any successor fixes.

## Current isolated assembly

The release worktree `run-file-custody-release/TinyAssets` on
`codex/file-custody-release` starts at consumer `f9b91ed7`, not the experimental
file ancestry. Owned paths were imported from file candidate `4dd99ba4` using
explicit patches. Foundation runs/containment/provision files, consumer runtime,
the consumer's lazy-unavailable origin registry and common schema/runtime are
byte-unchanged. Only the file compiler context, file physical-deletion additions,
five reset table classifications and independent file maintenance cursor were
merged into shared paths. Conversation expiry/model bridge/receipt observers
remain intact. Existing read_graph request_key positional ordering is preserved.

Consumer's review-disposition/specification/test-only successor is imported as
`456d9368`, `82145d50` and `7e17f751` (originals `47025163`, `50774c81`,
`d3fa5f91`). The maintenance AST fixture binds both cursors and tests independent
file/admission/delivery failure. Lower-level file fixtures explicitly acquire the
real admitted-worker guard instead of relying on superseded implicit family
enrollment, with no-guard refusal retained. No production runtime changed for
either fixture correction.

## Not file dependencies

Do not import this branch's `tinyassets/runs.py`: its only difference from the
foundation is the older unconditional root-family enrollment, which would undo
the activation correction. Likewise do not import this branch's
`node_sandbox.py`, `workspace_cgroup_join.py`, `workspace_cgroup_kernel.py`,
`workspace_family.py` or `workspace_provision_process.py`. Their differences are
experimental containment wiring, not used by owned authoring capture or reads.
No cgroup bootstrap fixtures, host configuration or cloud launch documents are
needed. Keep the foundation's worker guard/use, family provenance and prepared
invocation interfaces, which file reads actually require.

## Necessary custody additions

Copy the file modules and their tests, preserving independent ownership and
lifecycle: `tinyassets/run_file_{binding,capture,cleanup,contract,erasure,node,
reader,release,retention,sources}.py`; `tinyassets/storage/{run_files,
run_file_lock}.py`; `tinyassets/execution_authority/{blob_stream,blob_proof}.py`
file streaming changes. These use existing storage, authority, authoring session,
reset barrier and workspace byte accounting APIs; they create no new executor.

`tinyassets/workspace_pool.py` difference from the foundation is the 54-line
byte-only `reserve_transfer_bytes` extraction. Preserve that hunk, including
scope-bound replay and no fabricated workspace-job observation. Canonical
compiler difference is the 58-line alias/read-context/explicit placement work
from `722f7156`, separate from consumer model/receipt edits in the same file.

Executable `io_manifest` preservation and strict runtime declarations require
changes in `authoring/io.py`, `authoring/models.py`, `authoring/store.py`,
`branches.py`, `branch_versions.py` and `daemon_server.py`. Do not omit these as
presentation-only work: without them capture references can be lost before the
immutable version contract or cannot resolve their real owned authoring source.

## Shared admission dependencies and lifecycle

Generic envelope/common worker provenance predates this builder resume; preserve
the foundation guard hooks and `76804605` common carrier/on-settled semantics.
`5292b378` adds origin fields/immutable replay checks, pure origin validator,
single static registry, safe prior-marker exception handling and the independent
bounded boot/maintenance admission scan. `d2695029` adds reserve-only direct
intake. `59ca33f6` adds the pure read-only uncertainty classifier.

Canonical consumer import does NOT need custody modules: its registry adapter
imports are lazy. Keep consumer's current static exports and v1 execution options,
and its same initial/recovery registry call. Never infer origin from file presence.

Retain exact generic `run_input_admissions` reset/account lifecycle from
`89b5ea23` (consumer release already imports its isolated equivalent), and file
custody reset/account cleanup from `e4e93d97`, retention `6c518ed5`, bound-read /
selective settlement `a2003223`. Current file tables and physical deletion debt
must all remain classified. Preserve tombstones and cleanup ordering; no
origin/object table may be omitted merely because an idle reset happens to pass.

## Public route candidate

`tinyassets/api/run_files.py`, `api/runs.py`, `universe_server.py` and
`engine_mcp_server.py` expose same-owner capture/read/release/limits plus direct
and versioned file admission. Public run status uses the shared pure classifier
after owner validation. The new version selector is appended to signatures to
preserve positional callers and has existing source-read checks on both handles.
Merge only these file-specific route hunks where consumer edits overlap.

Rebuild all canonical mirrors after assembly. Evidence and remaining release
gates are in `verification.md`; test counts from this mixed-ancestry tree do not
substitute for rerunning the assembled candidate on Windows/Linux and CI.
