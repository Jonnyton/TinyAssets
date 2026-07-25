## Context

Bootstrap runs as root, clones `/opt/tinyassets`, and intentionally transfers
that checkout to the non-login `tinyassets` service account. It later asks Git
for `HEAD` as root so the shared uptime installer can receive an immutable
`TINYASSETS_SOURCE_SHA`. Git correctly rejects that ownership mismatch. Repeat
bootstrap also reaches root-owned `fetch` and `reset` operations against the
already service-user-owned checkout.

The checkout path is a bootstrap constant, the remote and branch are explicit,
and the service account is the existing owner expected by the deployed
compose/runtime path. The fix must preserve rerun convergence without asking
root Git to trust a lower-privilege user's mutable repository.

## Goals / Non-Goals

**Goals:**

- Make fresh and repeat bootstrap resolve the exact checked-out commit.
- Ensure every Git process runs as the checkout's current owner.
- Pass a validated full lowercase SHA to the shared uptime installer.
- Preserve the intentional service-account ownership of the checkout.

**Non-Goals:**

- Change repository location, remote, branch selection, or service ownership.
- Add global/system Git configuration.
- Treat live DR success as implied by unit tests; the exact landed drill remains
  the acceptance proof.

## Decisions

### Match Git execution identity to checkout ownership

On a fresh host, root clones the repository and resolves `HEAD` while the
checkout is still root-owned. On a repeat run, bootstrap first converges the
checkout ownership to `tinyassets`, then a small `service_repo_git` wrapper
uses `sudo -u tinyassets -- git -C /opt/tinyassets ...` for `fetch`, `reset`,
and `rev-parse`. No Git process receives a `safe.directory` exception.

Alternative considered: use invocation-local
`git -c safe.directory=/opt/tinyassets`. This avoids persistent or wildcard
trust but still authorizes root Git to consume configuration and hooks from a
lower-privilege, mutable checkout, so it is rejected.

Alternative considered: capture `HEAD` before `chown` without changing repeat
operations. That fixes only a fresh clone; a rerun already begins with
service-user ownership and fails at `fetch`.

### Validate the resolved SHA before changing later host state

Resolve `HEAD` immediately after clone/update, require exactly 40 lowercase hex
characters, and save it in `TINYASSETS_CHECKOUT_SHA`. Pass that value to the
shared installer after ownership transfer. An empty or malformed result fails
at the repository boundary with a bootstrap-specific error.

## Risks / Trade-offs

- **[The service-owned checkout can contain account-controlled Git config or
  hooks]** → Repeat Git commands execute as that same non-login service account;
  root Git never opts into the checkout with `safe.directory`.
- **[A future checkout-path override could broaden trust]** → The path remains a
  hard-coded bootstrap constant. Any future configurability requires separate
  canonical-path and privilege-boundary validation.
- **[Structural tests cannot reproduce a real provider host]** → The exact
  landed production DR drill must prove Debian bootstrap, restore, state,
  connector probe, and cleanup.

## Migration Plan

1. Land the helper, SHA validation, focused regressions, and synced spec.
2. Dispatch the DR workflow from the exact landed commit.
3. Record the terminal evidence; if bootstrap fails again, retain the bounded
   failure and require cleanup before another attempt.

Rollback is a normal git revert.

## Open Questions

None.
