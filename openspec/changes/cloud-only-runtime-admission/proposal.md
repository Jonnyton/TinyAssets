# Cloud-only runtime admission

## Why

PLAN.md § Cross-Cutting Principles (founder directive, 2026-09-21 PDT) requires
that the hosted platform run exclusively on cloud infrastructure and that
`DESKTOP-KCPMGP3` — the founder's personal home desktop — never serve platform
traffic, execute platform/universe work, supply a model relay, hold required
runtime state, schedule recovery, or become a temporary/emergency/fallback
dependency. AGENTS.md carries the matching prohibition. The directive is
explicit that a hostname denylist is not the boundary and that "unknown
provenance is not proof of a cloud executor". It is also explicit that this is
the *required design*, not a claim the code already enforces it.

Today it does not. Every "cloud" marker in the tree is self-asserted by the
process asserting it:

- `daemon_registry.ensure_daemon_runtime` (`tinyassets/daemon_registry.py:489-530`)
  writes `"runtime_registration": "cloud_worker"` into runtime metadata
  unconditionally, on any machine, revalidated on this branch at base
  `02b1e628`.
- `claim_assigned` (`tinyassets/branch_tasks_v2.py:462-511`) is the CAS that
  actually transfers task ownership. Its in-transaction predicate is
  `_transaction_allows_assigned_consumer` plus an optional `authority_claim`
  callback; **executor class is a parameter of neither**. The only
  executor-class check in the claim path is `_consumer_skip_reason`
  (`tinyassets/runtime/assigned_queue_consumer.py:110-119`), evaluated in the
  claimer's own Python before the transaction — a diagnostic, not a gate.
- Foreground and served provider execution stamp the class as a literal:
  `agent_runtime_provider_execution.py:1225`, `background_served_provider.py:1336,1547`.
- Public ingress accepts *token possession*: `scripts/run-tunnel.sh:55-58` execs
  `cloudflared tunnel run --token`, and `deploy/compose.yml:182` passes
  `CLOUDFLARE_TUNNEL_TOKEN`. Possession is a credential fact, not provenance.
- `automation_executor_class` is a nullable descriptive column whose CHECK still
  admits `'tray'` (`tinyassets/storage/request_admissions.py:264-267`, read back
  at `branch_tasks_v2.py:1368`). Cloud-only is not expressible as a storage
  constraint today.

Two corrections bound the claim this change makes. A dev-local clone of the DB
is **not** the live platform DB, and no path from a local claim to production
authority or routing has been demonstrated — so the present state is an
unenforced boundary, not a proved production breach. And a droplet-injected
secret or a copied tunnel token remains copyable; nothing available here is
hardware attestation, and this proposal does not describe anything as such.

No live desktop dependency was proved either: the local inventory shows no
TinyAssets or `cloudflared` service/process and the legacy drain/guard tasks are
disabled. The gap is therefore an *architecture* gap to close before the next
accident, not an active outage.

## What Changes

One fail-closed provenance resolver, consumed at the four boundaries a registry
or claim guard alone would miss, plus an explicit separation of application
enforcement from cloud network/credential custody.

1. **Provenance resolver** — `resolve_platform_runtime_provenance()`,
   fail-closed: absent or unverifiable evidence ⇒ not cloud ⇒ refuse, never a
   host fallback. Hostname, container name, compose label and env naming are
   never evidence (they travel with a checkout).
2. **Claim admission inside the CAS transaction** — the invariant moves into
   `_transaction_allows_assigned_consumer` / the `authority_claim` callback,
   which already receive `conn`, `candidate`, `consumer_lease`.
   `_consumer_skip_reason` stays as the refusal-ledger diagnostic.
3. **Runtime registration** — `ensure_daemon_runtime` writes the *resolved*
   registration and refuses rather than writing `cloud_worker`. A registration
   row binds the admitted cloud instance id plus a boot epoch and is
   re-validated on read, so a row written on cloud cannot be replayed by a
   later local process.
4. **Startup / foreground / served execution** — serving startup resolves provenance once and refuses to serve unadmitted, with no degraded local
   mode; the three literal `executor_class="cloud"` sites take the resolver's
   result.
5. **Off-cloud ingress is prevented, not merely refused** — the repo deletes its
   own ability to enroll a Cloudflare connector or publish a public ingress
   (`_start_tunnel`, `fantasy_daemon/__main__.py:3294`, called at `:3542,3755,3844`,
   re-exported at `tinyassets/__main__.py:48,63`), because a connector that
   *receives then refuses* has already absorbed public availability. Origin
   refusal stays as the backstop for what deletion and custody cannot cover.
6. **Recovery** — watchdog, release-reconcile and stale-runtime retirement leave
   work pending rather than re-homing it to an unadmitted runtime.
7. **Custody, stated and verified, not coded here** — the cloud network and
   credential controls (Cloudflare tunnel/Access, DO firewall, GitHub secrets)
   are named as invariants and verified read-only from hosted CI by a bounded
   preflight (`scripts/cloud_only_preflight.py`, added here, **not run**).
   Production authority rests on this custody layer; the resolver is an
   accidental-start guard, not attestation.

## Impact

- Affected specs: new capability `cloud-only-runtime-admission`.
- Affected code (implementation follows review, not in this change):
  `tinyassets/branch_tasks_v2.py`, `tinyassets/daemon_registry.py`,
  `tinyassets/runtime/assigned_queue_consumer.py`,
  `tinyassets/agent_runtime_provider_execution.py`,
  `tinyassets/background_served_provider.py`,
  `tinyassets/foreground_run_provider.py`, serving startup, one new
  read-only verification workflow.
- Risk: an over-strict resolver takes production down. Mitigated by landing the
  resolver plus its ledger first in observe-and-record mode on the droplet,
  confirming it resolves CLOUD there, and only then flipping the four refusal sites.
- Non-goals: no new privileged agent fleet, no new provider account, no new MCP
  tool, no runtime guard in this change, no infrastructure mutation.

## What this change does *not* claim

The resolver is an **accidental-start guard**, not attestation: unsigned
link-local metadata plus a deploy-copied expected id is forgeable by a local
root operator. The boundary is closed by Layer C custody plus the deletion of
the in-repo connector-enrollment path; the resolver makes accidents refuse
loudly. Record-only preflight and record-only resolver are **observation, and
explicitly incomplete** — the boundary is not closed until the refusals are
flipped and a deployed sha proves them live. Free-user acceptance requires the
user's own OpenRouter OAuth authorization, an eligible free-model approval and a
first actual tool-capable response — not a "zero-setup" or "no-credential"
provider, which does not exist.
