## Context

The current production compose shape and queue runtime were built around four long-lived containers pinned to provider families. Per-universe serving bindings now persist the user-selected credential authority, and the founder has removed the four workers from production. The remaining daemon already owns the durable queue cycle and can execute a claimed BranchTask; its provider call currently lacks a serving-binding context and historically depended on worker pins or ambient host auth.

## Goals / Non-Goals

**Goals:**

- Make the daemon the queue consumer without creating a replacement fleet abstraction.
- Resolve one current serving binding and credential snapshot for the physical task universe, bind that authority to every provider call in the run, and clean the snapshot afterward.
- Keep unavailable work pending with typed `no_requester_owned_executor` evidence so another runnable task can proceed.
- Remove fixed workers, host-pool clients, provider chains/pins, worker secrets, and fleet-only health/supervisor code.
- Preserve queue durability, transactional claim/fencing, ingress, memory, canaries, status, Slack's opt-in profile, and provider adapters.

**Non-Goals:**

- No platform fallback, provider ranking, market credential, or alternate-provider retry.
- No new serving-binding format or changes to the merged serving-binding public modules beyond deleting fleet/fallback references.
- No production deployment or migration of user vault records.

## Decisions

1. **One sealed assigned-credential context per branch run.** A small daemon-side resolver reads the current provider assignment, resolves the universe's sole serving agent binding, revalidates the binding/custody transactionally through the existing serving-binding authority helper, snapshots the credential, and returns an immutable authority object. The router accepts only that exact provider for the run. This reuses the merged serving-binding source of truth without teaching the queue about vault secrets.

2. **Pending hold evidence, not terminal failure.** A BranchTask gains a sanitized `hold_reason` field. Before claiming, the daemon refreshes credential availability for pending tasks: unavailable tasks receive `no_requester_owned_executor`, available tasks clear the marker, and the stateless dispatcher skips held rows. No unavailable task is claimed or failed, and a later credential assignment makes it runnable without queue migration.

3. **No fallback code remains in the provider router.** Served request authority, armed background authority, and assigned-credential authority each produce a one-provider route. Calls without one of those authorities hold before provider access. Provider failure exhausts that provider only. Per-node policy may set model parameters but cannot select a different provider.

4. **The daemon service is the only default LLM runtime container.** Compose retains `daemon`, `tunnel`, `logs`, and profile-gated `slack-agent`. Deployment and recovery accept no worker image/route inputs and materialize no shared Codex/Claude host auth for workers. The deploy fence asserts this exact worker-free ownership set.

5. **Delete obsolete surfaces instead of shimming them.** `tinyassets.cloud_worker`, its healthcheck, the fleet/writer-pinned cloud automation runtime, `tinyassets.host_pool`, and fleet-only tests are removed. Callers are rewired to daemon/credential authority or removed; no compatibility aliases remain.

## Risks / Trade-offs

- **[Risk] One daemon provides less parallel queue throughput than four fixed workers.** → Capacity is intentionally credential/user chosen; future concurrency scales through explicit credentials and daemon runtimes, not a hard-coded provider fleet.
- **[Risk] A binding can change between readiness scan and launch.** → The launch resolver revalidates and snapshots after claim; failure requeues/holds the task with the same typed reason rather than widening authority.
- **[Risk] Removing fallback exposes previously hidden provider outages.** → Typed hold/exhaustion evidence is the desired fail-closed behavior; user-designed workflow branches may model explicit alternatives.
- **[Risk] Large deletion exposes stale imports and full-suite-only assumptions.** → Run focused deletion/rewire tests after each slice, then the complete CI required-test surface and compare failures with origin/main.

## Migration Plan

1. Land worker-free deployment shape and fence assertions while production workers are already absent.
2. Land daemon credential resolver, pending hold evidence, and exact router authority.
3. Remove fleet/host-pool modules and update all inbound imports/tests.
4. Rebuild the plugin mirror and run the complete required-test surface.
5. Commit the branch only; merge/deploy remain separate reviewed actions.

Rollback is a normal git revert before merge. Production workers were physically removed, so restoring the old repository shape would not restore execution and is not an operational rollback plan.

## Open Questions

None. The founder architecture fixes the authority and fallback decisions for this change.
