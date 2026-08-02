# Host-principal owner acceptance and RED-slice claim

**Date:** 2026-08-01
**Current main:** `0dc3a40c042721c5efd68dd369469d4c9cdef1ae`
**Provider:** `drain-20260801-113628-6deab6`
**Scope:** OpenSpec ownership coordination and exact next-slice claim only. No
runtime, migration, canonical-spec, deployment, or rollout change is included.

## Acceptance receipts

- Packaged tray / PR #1736 owner: **ACCEPT** the RFC 8707 resource,
  interactive-`auth_time`, challenge/proof, Ed25519 native-key, and returned
  principal ID/generation client adaptation while retaining account-token and
  desktop-file custody: [receipt](https://github.com/Jonnyton/TinyAssets/pull/1736#issuecomment-5154079630).
- Identity/auth and daemon/host-pool owner: **ACCEPT** the route-local
  exact-audience validator, verified-subject ownership, scope provisioning,
  private stable storage/inventory, and principal-generation linkage distinct
  from insert-always sessions: [receipt](https://github.com/Jonnyton/TinyAssets/pull/1753#issuecomment-5154079683).
- Custody / PR #1746 owner: **ACCEPT** independent trusted checks of current
  host-principal status/generation and provider-assignment generation while
  custody retains every provider-secret/reference lifecycle: [receipt](https://github.com/Jonnyton/TinyAssets/pull/1746#issuecomment-5154079730).

## Task 1.8 collision proof

The next bounded slice is OpenSpec tasks 2.1 and 3.1 only:

- `tinyassets/auth/host_binding.py`
- `tests/test_host_binding_auth.py`
- the existing `openspec/changes/bind-host-principal-to-account/**` task and
  evidence files

Evidence on 2026-08-01:

- `claim_check.py` against the prepared STATUS returned `clear: true`, with
  only this provider's own OpenSpec overlap.
- The same exact check against `origin/main` returned `clear: true` with no
  overlap.
- A bounded file-list inspection of all 98 open PRs found no exact path under
  the change, runtime module, or focused test file.
- A targeted local-worktree check found no dirty copy of either proposed new
  runtime/test path.
- The unfiltered global `worktree_status.py` diagnostic exceeded its
  30-second bound and is not counted as evidence.

External implementation precedent is skipped: this is a route-local extension
of the repository's canonical WorkOS validator pattern, and this recovery
slice only establishes ownership and exact file scope.

The canonical STATUS row now owns those exact paths. Later proof, storage,
host-pool composition, load, packaged parity, deployment, and rendered/organic
acceptance remain in the unchecked OpenSpec tasks and do not block beginning
this RED slice.
