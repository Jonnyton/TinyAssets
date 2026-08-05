# The worker fleet serves a universe no authenticated user can repoint

`current: 2026-08-05`. Measured against deployed sha `bb5b3cf5`
(deploy run `30989259215`). Cross-family review: Codex `adapt` — it confirmed
the diagnosis and **refuted the first proposed fix**; see *Rejected fix* below.

## Symptom

`get_status` on the founder home `u-01kxm1vszd8hwp7em418asq8h9`:

```
depth = 4, pending = 4, valid_pending_count = 4, eligible_pending_count = 0
awaiting_compatible_capacity = 4   reason: no_live_compatible_worker
compatible_worker_count = 0        consumer_ready = true
operational_oldest_age_s = 47284   (~13.1 h)
quarantined = 0, invalid_operator_admission = 0
open_brain.runtime_instance_count = 4
```

Four slices are structurally valid, and nothing will ever claim them.

## Root cause

The worker fleet resolves the universe it serves from a **host-global marker**,
while the queued work lives in a **per-user universe**.

1. `cloud_worker._resolve_universe()` falls through to
   `storage.active_universe_id()`, which reads `/data/.active_universe`.
   In production that marker holds `concordance` — the legacy story universe.
   Every supervisor beat is therefore written under `concordance/`.
2. `api.universe._worker_liveness(udir)` globs beat files **inside `udir`**
   (`universe.py:1204-1214`). For `udir = u-01kxm1…` the glob returns nothing,
   so `_compatible_epoch2_workers` returns `[]` and
   `compatible_worker_count = 0` (`universe.py:1485`) — *before* any descriptor
   is validated. Every pending row then classifies
   `awaiting_compatible_capacity` / `no_live_compatible_worker`
   (`branch_tasks_v2.py:604-610`).
3. Independently, the beat pairs the supervisor's universe (`concordance`) with
   `TINYASSETS_RUNTIME_INSTANCE_ID`, which `_pump_cloud_automation_triggers`
   last set for a runtime registered against the *pumped* universe and never
   restored (`cloud_worker.py:1005`). `daemon_registry.py:469-470` compares
   exactly those two values and raises `queue_universe_id_mismatch` — on every
   beat, which is why the worker logs repeat it. This is why
   `runtime_instance_count = 4` in `u-01kxm1…` while its beats are absent: the
   worker's runtime is registered in one universe and its liveness advertised
   in another.

## Why no user can fix it

This is the load-bearing part, and it is a *design* gap rather than a leak:

- An **authenticated** founder's `switch_universe` is request-scoped **by
  design** and deliberately does not touch the marker — "Explicit universe
  selection is not global… must NOT mutate the host-global `.active_universe`
  marker that other users resolve through" (`api/universe.py:5562-5578`).
- Only an **anonymous / dev single-tenant** call writes the marker
  (`api/universe.py:5580-5586`).
- `TINYASSETS_UNIVERSE` cannot be used to pin a worker: `deploy-prod.yml:1415`
  fails the deploy if a worker inherits it, because it "can bind a worker to a
  different universe than the public MCP default".

The multi-tenant fix correctly froze the marker; the worker fleet was never
migrated off it. So the fleet is pinned to whatever universe the marker held
when anonymous writes were still possible, and **no authenticated user —
including the founder — can repoint it through any advertised handle.**

## Rejected fix (recorded so it is not re-attempted)

*Proposal:* have the automation pump record the `(universe, runtime, worker
slot)` triple it binds, and have the liveness beat advertise capacity into each
served universe from that triple.

*Why it is wrong:* the beat asserts a live **consumer** (`subprocess_alive`),
but the pump's runtime binding is a **producer** audience. Cross-universe
pumping happens after the supervised child has exited, and that child was
spawned against `concordance`. Advertising from the pump triple would either
report `subprocess_alive=false` or falsely advertise the next `concordance`
child as a consumer for the target universe. The rows would leave
`awaiting_compatible_capacity` and become claimable by a worker that will never
work them — replacing a visible stall with an invisible one.

## Correct shape

One **real supervised execution context per advertised universe**: a supervisor
whose resolved universe, spawned child, registered runtime, descriptor, and
beat directory all agree. Keep the atomic-record idea, but bind it to spawned
consumers, not to producer-pump audiences.

This is also what the platform model requires — a universe is a user's account,
and many users each run their own. A single host-global marker choosing which
universe the whole fleet serves cannot survive a second user.

## Do NOT "fix" this by repointing the marker

`superseded: 2026-08-05` — an earlier revision of this audit proposed
repointing `/data/.active_universe` at the founder home as the smallest
unblock. Host reframe, same day: **the provider-shaped platform worker fleet
is the relic being phased out.** Users bring their own LLM; the only LLMs on
the platform should be ones users host to their universes or rent onto the
market. Repointing the marker would make four slices run tonight by deepening
the dependency on platform-owned workers — the wrong direction.

The stall is a *symptom* of the relic, not an ops incident. Recorded here so
the next session does not re-derive the marker fix and ship it.

## What the relic actually is

Three couplings make the current path platform-owned rather than user-owned:

1. **Workers are provider-shaped containers.** `claude-1`, `claude-2`,
   `codex-1`, `codex-2` exist so that a user binding naming provider `X` can
   find a live runtime stamped with provider `X`:
   `cloud_automation_runtime.resolve` refuses the audience unless
   `runtime_matches_worker_provider(..., provider_name=binding.provider)`
   (`daemon_registry.py:810-835`), and a runtime's `provider_name` comes from
   the *container's* `--provider` flag (`cloud_worker.py:987-999`). N providers
   x M users cannot be pre-provisioned as containers.
2. ~~**Credential resolution fails open.**~~ **RETRACTED, `current: 2026-08-05`.**
   An earlier revision of this audit claimed a universe with no deposited
   credential inherits the container's ambient `CLAUDE_CODE_OAUTH_TOKEN` /
   `CODEX_HOME`, citing `credential_vault.py:596-628`. That function does
   return `{}`, but it is **not on the execution path**. The providers call
   `providers/base.py:348` `subprocess_env_for_provider`, which — given a
   universe — builds a private per-universe runtime root
   (`<universe>/.runtime/provider-child/<provider>/home`) and raises
   `ProviderUnavailableError` when credential resolution fails
   (`providers/base.py:385-408`). It fails **closed**. Callers verified:
   `claude_provider.py:121,212`, `codex_provider.py:143`.

   The error was reading a function body and attributing it to a call site
   without checking who calls it. Found by cross-family review. Whether the
   rest of STATUS concern R2-1 (`set_engine` not constraining
   `allowed_providers`) still holds is a separate question and is NOT
   settled by this correction.
3. **The scheduler is a platform container** whose served universe comes from
   the fleet-global marker described above.

## Where the correct design already exists

- `openspec/changes/activate-requester-owned-cloud-compute-binding` — owner
  -scoped enrollment + `bind_provider`, budgets, credential-reference digests,
  explicitly no maintainer/market fallback. Built through task 3.1; **3.2
  (focused tests + independent security review) and 3.3 (deploy the dark bind
  path and reconcile one enrollment through the rendered phone connector)
  remain open.**
- `openspec/changes/distributed-execution` — the signed job/lease/result
  protocol, real sandbox backend, and authenticated execution route that
  replace provider-shaped containers. **25 tasks done, 83 open.**
- `openspec/changes/activate-custom-agent-runtime-core` (10 done / 2 open) and
  `activate-custom-agent-runtimes` (3 / 5) — the custom cloud agent lane
  another session is driving.
- `openspec/changes/owner-operable-automation` — 0 done / 9 open.

The architecture is specced and largely correct. What is missing is the part
that makes it *user-owned in fact*: closing the credential fail-open, and
replacing provider-shaped platform containers with an execution route that
runs a slice on the requester's own compute.

## Rejected fix #2, recorded so it is not re-attempted

`current: 2026-08-05`. A second attempt made the supervisor re-select its
served universe each iteration (`_universe_to_serve`): keep the configured
universe when it has admissible epoch-2 work, otherwise move to the universe
with the oldest pending row, gated on an existing `provisioned` runtime and an
explicit `TINYASSETS_SINGLE_TENANT_SERVE_ANY_UNIVERSE` opt-in.

Cross-family review: **reject**, with a reproduction. Do not revive it without
answering all of these:

1. **The runtime gate is not an authority gate.** A non-maintainer holding
   `universe:costly` can call public `daemon_create` / `daemon_summon`; summon
   inserts a `provisioned` row. Codex reproduced `created_by="attacker"`
   satisfying the gate. `auth/provider.py:376`, `api/universe.py:2619,2644`,
   `daemon_server.py:1194`.
2. `provisioned` encodes no worker id, provider, owner, executor class, live
   descriptor, or freshness, and the listing returns every historical row.
3. The producer path already minted cross-universe runtimes but never routed
   the child there. This change would have converted those ambient registry
   records into authority to move and spawn the physical worker.
4. Real exposure is **fleet-resource hijacking / DoS**, not subscription theft
   — see the retraction above.
5. The pre-spawn auth gate checks host-global subscription health, not the
   selected universe's credential, so a host-authenticated worker would
   repeatedly enter an uncredentialed universe and fail.
6. **Fairness is broken by construction:** selection counts capacity-blind
   pending work and picks oldest without checking this worker can execute it.
   One permanently incompatible row pins the worker and starves every
   executable universe — and such a row in the *configured* universe prevents
   selection entirely.
7. Exception handling did not consistently fail toward "do not move": an
   unreadable configured universe reads as `(0, 0)`, moving the worker off a
   universe whose workload is merely unreadable.
8. **Cost:** this installation has **259 non-hidden directories** under the
   data root. One operational read each, ≥3 SQLite statements per read, is
   ~777 statements per idle turn against a 10s backoff.

## Independent findings worth keeping (not about the rejected patch)

- **`TINYASSETS_AUTOMATION_OWNER_USER_ID` leaks like the worker id did.** The
  pump sets it and never restores it; a later spawn filters runtime
  registration by that stale owner. Same env-smuggled-identity class as the
  beat-filename drift fixed in #2323, and live today independent of any
  selection change. `cloud_worker.py:1121,1190,1195`.
- **259 directories under the data root.** Any per-universe sweep is an
  O(dirs) cost, and `read_graph target=graphs` already surfaces storage dirs
  (`cloud-automation-inputs`, `daemon_wikis`) as universes.

## Route decision (cross-family, 2026-08-05)

Five routes were ranked. Verdict: **R5 — build a dedicated, binding-scoped
executor service for the founder universe, explicitly pinned AND
credential-isolated.** Ranking R5 > R3 > R4 > R1 > R2.

**There is no safe route that unblocks these four rows without a deploy-config
change.** Marker manipulation redirects shared workers; a fabricated or copied
beat either fails descriptor matching or advertises capacity that cannot
execute (`api/universe.py:1324`).

Why each alternative fails:

- **R1 — pin an existing worker to the universe:** rejected. The workers share
  `/data/.codex` and `/data/.claude` and subprocesses inherit the parent
  environment (`deploy/compose.yml:165`), so pinning one would execute this
  user's rows on **maintainer credentials**. Amending the deploy guard is
  acceptable *only* for a new, explicitly declared, credential-isolated
  service; relaxing it for the existing fleet would regress the
  fleet-diversion protection it enforces today
  (`.github/workflows/deploy-prod.yml:1413`).
- **R2 — make `UNIVERSE_SERVER_DEFAULT_UNIVERSE` outrank the marker:**
  rejected as "plainly routing around the guard with a sibling variable, not a
  legitimate security distinction". Both variables select the worker's
  universe; changing precedence just makes the guard's grep blind to
  equivalent diversion (`cloud_worker.py:133`).
- **R3 — one supervisor per served universe in one container:** rejected as
  stated. One process resolves one universe once. Public directories, pending
  rows, and provisioned runtimes are *demand*, not *serving authority*; the
  enrollment manifest is the only plausible authority signal in current code,
  and shared in-container credentials remain unisolated (`cloud_worker.py:1707`).
- **R4 — `user-assigned-llm-policy` task 4.1:** does **not** unblock these
  rows. 4.1 changes automation executor selection from `daemon_id` to
  `provider_binding_id`; it does not touch epoch-2 capacity discovery, which
  still begins with heartbeat files inside the universe's own directory
  (`api/universe.py:1285`).

R5 must derive deployment eligibility from an active, unexpired,
operator-enrolled `{owner, universe, provider, credential_reference_digest}`
record — not directory existence, queued rows, or public runtime records
(`provider_work_enrollment.py:99`).

## Independent security finding

**The runtime fence never attests the credential reference.** It verifies the
binding's owner/universe/provider against the runtime's universe/provider but
never compares `credential_reference_digest`
(`storage/provider_work_authority.py:1956`). That omission is what permits
ambient maintainer credentials to satisfy the fence, and it is why R5 needs
credential isolation at the service level rather than trusting the binding
check alone. Filed as its own STATUS row; not fixed here.
