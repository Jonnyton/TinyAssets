# MVP end-to-end walk — live production, 2026-08-05

**Environment:** `https://tinyassets.io/mcp`, production serving
`release_state.git_sha = 868153bdc5be646f35e2cca65bcfc82f6dbb44b2` (= `origin/main`
HEAD), deployed `2026-08-04T23:00:39Z`, `forward_canary_status: passed`.
Hard Rule 14 satisfied — this walk exercised the code production actually runs.

**Verdict: the golden path cannot be walked end to end**, but it reaches
considerably further than a first pass suggested. Authoring and **execution
work on production**; the walk stops at binding a workflow to a scheduled cloud
automation.

> **Correction to this document's own first revision.** It originally claimed
> the walk "stops before step 5 of 8" because the platform had no compute. That
> was wrong and is retracted. `converse` and `run_graph` are **independent
> engine surfaces**: `converse` has no engine, but `run_graph` does, and a
> workflow ran to completion with real provider calls. Generalising from the
> `held/setup_required` response to the whole platform was an inference, not a
> measurement — the error was corrected only by actually executing a run.

> Scope note: this is **supporting evidence, not final chatbot-surface proof**.
> Per AGENTS.md, final acceptance needs a browser-rendered connector
> conversation (`ui-test`). These were direct MCP calls. The blockers below are
> reachable-state facts, not UX claims.

## What works — verified live

| Step | Result | Evidence |
|---|---|---|
| Public surface health | **pass** | `mcp_public_canary.py --assert-handles` exit 0. Mutation-probed first: a bogus URL exits 2, so the green is real rather than a silent no-op |
| 1. Discover a public agent | **pass** | `read_graph target=agents` → 3 definitions |
| 2–3. Remix + customize | **pass** | Published a real 2-parent remix `agent_01kz7kn4vpqz0fp8w6ytq6et9t`; lineage recorded per component with `parent_definition_id`, `credit_share`, `generation_depth: 1`, and both definition and component fingerprints |
| 4. Private binding | **pass** | `agent_binding_01kz7knr5haptc4mzb7f59513z` created; the public `portable_definition` carried **no** provider, destination, or binding reference — the public/private boundary held |

An earlier definition ("V1 Intelligence Agent") describes itself as a remix but
has `lineage: []`. That is a prior test artifact published via `publish` rather
than `remix`, **not** a lineage defect — a fresh `remix` records lineage
correctly, as above.

## Execution works — verified by running one

| Step | Result | Evidence |
|---|---|---|
| 5. Author a workflow | **pass** | Branch `36370cd19f90` built; validation named the exact fix on each rejection (missing node, cycle without exit, `edge spec missing 'from' or 'to'`) |
| 5b. Compiler safety | **pass** | `strict_input_isolation` correctly refused a run whose `input_keys: ["topic"]` had no `state_schema` field to initialise it |
| 5c. Immutable publish | **pass** | `branch_version_id 36370cd19f90@6373b09b`, content hash `6373b09b…` |
| 6. **Execute** | **pass** | Run `c327a8af2ec34142` → `status: completed`, node `summarize: ran`, `__system__: provider_calls`, 10.4s |

Authoring emits an evidence-only receipt that explicitly disclaims being an
authorization grant ("clients must not treat it as permission to execute future
writes") — the right posture.

## Blocker 0 — automation binding rejects every real branch id

The scheduled / computer-off step cannot be reached:

```
write_graph target=automation operation=create  →
{"error":"automation_setup_invalid",
 "detail":"branch_def_id must be a nominal non-bearer reference"}
```

Production mints branch ids as **bare hex** (`36370cd19f90`), while
`_NOMINAL_REFERENCE_PREFIXES` on `origin/main` carries only `branch_` /
`branch:` (`background_branch_authority.py:182-194`). `_reference()` hard-requires
`str.startswith(_NOMINAL_REFERENCE_PREFIXES)`, so **no workaround exists** — no
real branch can bind to a cloud automation until the code changes.

This is **#2291's defect class one line down in the same tuple**. The comment
immediately above `branch_` documents the identical universe-id bug: *"every
fixture in this package uses the `universe_` spelling, so omitting this prefix
rejected every REAL universe while the suite stayed green."* Same allowlist,
same fixture-versus-production spelling gap.

**Already owned:** PR #2292 ("Admit the branch identity shapes production
actually mints") fixes it — open, **draft**, unreviewed, `required-tests` red.
Live production repro attached there as a comment. Not fixed here.

### #2292 verified sufficient for automation creation

Applied PR #2292's head (`098ee63a`) in a throwaway detached worktree and drove
its validator with the exact shapes production mints:

| value | field | result |
|---|---|---|
| `36370cd19f90` | `branch_def_id` | **accept** |
| `36370cd19f90@6373b09b` | `branch_version_id` | **accept** |
| `36370cd19f90@6373b09b` | `pinned_branch_version_id` | **accept** |
| `36370cd19f90@6373b09b` | `branch_def_id` | reject (cross-shape confusion) |
| `36370cd19f90` | `branch_version_id` | reject (cross-shape confusion) |
| `sk-secretbearertoken123` | `branch_def_id` | reject (bearer) |

The fix is **field-aware**: a nominal prefix short-circuits, otherwise a
*per-field* canonical pattern applies (`_CANONICAL_REFERENCE_PATTERNS`). So it
admits the real shapes, still refuses bearer-shaped values, and additionally
refuses def-id/version-id confusion. `tests/test_cloud_automation_api.py` +
`tests/test_background_branch_authority.py` under that head: **152 passed, 1
failed** — the single failure being the rollback defect below, which also fails
on plain `origin/main` and is therefore **independent of #2292**.

**Conclusion: #2292 is necessary and sufficient to unblock automation
creation.** Nothing else stands between a published Branch version and a bound
cloud automation.

### Related: automation rollback violates its documented contract

`tests/test_cloud_automation_api.py::test_phone_rebinds_and_rolls_back_to_published_branch_versions`
fails with:

```
{'error': 'automation_rebind_invalid',
 'detail': 'background_binding_mismatch: background Branch binding does not match the immutable definition'}
```

The handle documentation states *"binding an earlier version rolls back without
mutating either version."* The test encodes that contract and the code now
refuses it, so this is a **real regression, not a stale test** —
quarantining it to green a gate would bury an MVP-relevant capability
(the demo requires preserving prior versions). Owner: the cloud-automation /
background-authority lanes.

## Blocker 1 — a user cannot give their universe an engine

`converse` returns:

```
status: held · reason: setup_required · missing: ["compute", "model_access"]
setup_paths[0].how = "Engine assignment is not exposed by the advertised handles."
note: "Ask the host to use the internal engine-assignment surface."
```

**This is correct behaviour, not a bug.** The universe refuses to think on
anyone else's credentials — the fail-closed posture that
[[ambient-credential-fallback-is-an-identity-leak]] exists to enforce.

Cross-family review (Codex, read-only, verdict `adapt`) confirmed there is no
user-reachable path, with citations:

- `write_graph(target="universe")` always *creates* a universe and **ignores
  `operation`** — it cannot dispatch `set_engine` (`universe_server.py:738`).
- The real setter exists only on the deprecated `universe(action="set_engine")`
  (`api/universe.py:5915`), hidden from `tools/list` (`universe_server.py:2451`).
- `bind_provider` writes *cloud-work* authority from a server-side enrollment
  manifest (`api/cloud_automations.py:419`, `provider_work_enrollment.py:82`)
  and never touches universe config or the vault. `converse` independently
  loads `UniverseContext` and calls its configured writer
  (`universe_intelligence.py:520`). **Two credential surfaces at different
  readiness**: automations are provisioned, conversation is not.
- The only self-serve OAuth flow is GitHub-destination-only
  (`api/cloud_connections.py:108`).

### Do not "fix" this by exposing a handle

Two landed decisions forbid the obvious repair:

- **`retire-mcp-provider-secret-deposit`** is an explicit **BREAKING** change
  prohibiting provider-key deposit through MCP: it "crosses the
  chatbot/control-plane boundary before the requester-controlled executor can
  protect the secret" and can make a shared-universe admin a confused deputy.
- **`constrain-set-engine-provider-authority`** records `set_engine` as an
  unresolved boundary that has drawn `ADAPT` across roughly five review rounds.

The sanctioned repair already has an owner: **`STATUS.md` row 13**,
`activate-requester-owned-cloud-compute-binding` — *"expose a phone-safe
provider enrollment/bind path … no maintainer or market fallback"* —
`claimed:codex-gpt5-desktop`. Its files are off-limits to other lanes.

**The unresolved question is a host decision, not an engineering task:** the
approved demo promises a browser-only user with *no daemon install*, while the
retirement change requires requester-supplied keys to live in a
**requester-controlled executor's OS secret store**. Those two cannot both hold
for a BYO-key user. Either the browser-only user's engine arrives by
subscription enrollment (server-side manifest, no secret crossing MCP — the
shape `bind_provider` already uses for automations), or the demo needs a local
executor. That choice gates steps 5–8.

## Blocker 2 — no Slack connection exists

`read_graph target=connections` → exactly one: `provider: github`,
`connection_class: pull-request-writer`, destination `jonnyton/tinyassets`,
cap 1 PR. The approved demo requires Slack conversation **and** scheduled Slack
delivery, so GitHub cannot substitute (confirmed by the same review). Steps 5
and 7 have no transport. Requires host-supplied Slack workspace + app
credentials.

## Blocker 3 — the workflow-iteration successor does not exist

Step 6 (draft → test → evaluate → revise → approve) needs
`enable-custom-agent-workflow-iteration`, whose admission gate
(`activate-custom-agent-runtimes` task 2.3) has **six preconditions, all
unmet** — three of them naming hardening changes that have never been created.
Recorded in `docs/handoffs/2026-08-04-custom-agent-mvp-handoff.md` §2 (PR #2289,
merged `884011ca`).

## Correction to an earlier claim in this walk

An interim version of this analysis asserted "**0 runs have ever executed** in
universe `u-01kxm1vszd8hwp7em418asq8h9`." **That is unsupported and is
retracted.** `read_graph target=runs` *ignores* `graph_id`
(`universe_server.py:502`) and filters inaccessible private runs afterward
(`api/runs.py:882`), so an empty result means "no runs this caller may see",
not "no runs exist". The blocker stands on the `held/setup_required` response
and the absent Slack connection alone. Caught by cross-family review, not
self-review.

## Unrelated finding surfaced during this walk — `main` is red

`main`'s own CI at `868153bd` reports **`NEW failures: 10`** against its own
quarantine baseline, including
`tests/test_cloud_automation_api.py::test_phone_rebinds_and_rolls_back_to_published_branch_versions`
(`KeyError: 'status'`). Exactly one commit landed between the last green gate
(PR #2289, 22:37) and that state:

```
git log --oneline 884011ca..868153bd
→ 868153bd fix: admit the universe id prefix production actually mints (#2291)
```

#2291 is a correct and valuable fix — admitting the `u-` prefix production
mints is what unblocks real cloud-automation creation — but it moved execution
past a rejection path several tests asserted, and the quarantine list was not
updated. **Every PR cut after it inherits all 10 as "NEW failures."** Triage
belongs to #2291's lane, not to whichever PR happens to notice.

## Test artifacts left on production

No delete operation is exposed on the canonical handle set:

- `agent_01kz7kn4vpqz0fp8w6ytq6et9t` — "E2E Walk Test Agent (2026-08-05)" (public definition)
- `agent_binding_01kz7knr5haptc4mzb7f59513z` — its private binding

## What would unblock the demo, in order

1. **Host decision:** does a browser-only user's engine arrive via subscription
   enrollment, or does the demo assume a local executor? Everything below waits
   on this.
2. **Row 13 lane** (`codex-gpt5-desktop`) lands the phone-safe provider
   enrollment/bind path for the conversational surface, not only cloud work.
3. **Host action:** provision a real Slack workspace + app credentials and a
   Slack destination grant.
4. Clear the six task-2.3 preconditions, including creating the three
   hardening changes that do not exist.
5. Re-walk, then perform the `ui-test` rendered-connector proof.


---

## UPDATE 02:30Z — blocker 0 is fixed and deployed; the wall moved to activation

`#2300` (main's 9 regressions) merged as `0d8f7ccb`, which unblocked `#2292`.
`#2292` merged and **deployed** as `df80b753` — verified the deployed sha
*contains* `_CANONICAL_REFERENCE_PATTERNS`, not merely that it merged.
Cross-family security review of that merge: **approve** — its strongest
objection (attacker-controlled canonical hex) did not survive, because
`_REFERENCE_PATTERN` still gates first, the fields are branch identities only,
and ownership is independently enforced. The widening admits identifiers, not
authority or secrets.

**Step 7 now works.** The exact call that failed earlier succeeded:

```
write_graph target=automation operation=create
→ automation_repo_7a09c311891da0f773aa1a8b024ecd19
  branch_def_id: 36370cd19f90        ← the bare hex previously rejected
  status: activation_requested
  authority.source: requester_owned_provider_binding
  destination: jonnyton/tinyassets · baseline_evaluation: admitted
```

**The remaining wall is activation, not creation.** The automation is
`desired_state: active`, yet:

- `activation.state: stopped`, `executor_class: null`, `subject: null`, and
  `activation.updated_at` is **two hours older than the automation itself** —
  the activation row is executor-owned and nothing advanced it.
- `terminal_receipts: []`, `current_trigger: null`.
- `operation=resume` is accepted but is a **no-op**: `desired_state` was
  already active, so there is no owner-side control left to pull.
- `get_status`: `compatible_worker_count: 0`, cloud-drain
  `runtime_instance_count: 0`.

`deploy/compose.yml` defines four cloud workers (`codex-1/2`, `claude-1/2`
running `python -m tinyassets.cloud_worker`) and the deploy reports success, so
this is a live-state question — no drain runtime instance is claiming work —
not a missing definition. It is the tray-to-cloud cutover, owned by the
`wf-cloud-drain-live-activation-20260803` lane.

### Product finding — the health surface dead-ends

`health` reports `state: activation_stopped` with **`blocker: null` and
`next_action: null`**. An owner who reaches this state is told their automation
is stopped and given nothing to act on — no cause, no remedy. Both fields exist
precisely to carry that, and both are empty in the one state where they matter.
Worth a row independent of the cutover.

### Score after this update

Working live: discover → remix (lineage/credit-share/fingerprints) → customize
→ private binding (no public leakage) → author → immutable publish → **execute
with real provider calls** → **create a scheduled cloud automation under
requester-owned authority**.

Not yet: scheduled *execution* (no drain runtime instance), `converse` (no
engine assigned), Slack (**adapter unbuilt** — `cloud_connections.py` wires only
`github`; `app_outbound_adapter.py` says "a later server-owned Slack adapter
supplies the injected callback"), second-account remix isolation.


---

## UPDATE 03:10Z — step 8's blocker is ops, and the design fix alone will not clear it

Worth stating plainly because it redirects effort: implementing D6 (decouple
executor selection from `daemon_id`) would **not** make step 8 run today.

D6 lets *any* compatible executor claim a requester-owned automation instead of
one named daemon. But production has **zero registered executors**
(`runtime_instance_count: 0`), so there is nothing for a decoupled claim to
match. The blocker is not "an executor refuses this automation" — it is "no
executor is registered at all".

### The exact mechanism, and the one-command diagnostic

`cloud_worker._register_worker_runtime()` (`tinyassets/cloud_worker.py:501`)
registers a runtime instance at startup. Two properties make the current state
invisible:

1. **It is per-universe.** `selector = {"universe_id": universe.name}` →
   `select_project_loop_daemon(...)`. A worker registers for the universes it
   selects a project-loop daemon for, not globally.
2. **It is best-effort.** Both failure paths `return` without raising, so a
   worker stays alive and healthy while silently unregistered.

So the four `cloud_worker` containers in `deploy/compose.yml` can all be running
correctly and still leave `runtime_instance_count: 0` for
`u-01kxm1vszd8hwp7em418asq8h9`.

**Exactly two log lines distinguish the causes.** On the production host:

```bash
docker ps --filter name=cloud_worker
docker logs <cloud_worker_container> 2>&1 | grep -E   'subscription auth not available|no project loop daemon registered|runtime registered'
```

- `"<provider> subscription auth not available; runtime registration will retry
  on next spawn"` → the container cannot see subscription auth. A credential/
  mount problem inside the container, **not** a code defect.
- `"no project loop daemon registered; skipping runtime registration"` →
  `select_project_loop_daemon` returned `None` for that universe. A
  registry/scoping problem: the universe has no project-loop daemon the worker
  will bind to.
- `"runtime registered worker_id=… provider=… runtime=…"` → workers *are*
  registering, and the blocker is elsewhere.

Whichever line appears determines the fix, and none of the three is reachable
without shell on the production host. Owner:
`wf-cloud-drain-live-activation-20260803`.

### Consequence for sequencing

`user-assigned-llm-policy` task 4.x (D6) remains correct and worth landing — it
removes a real coupling — but it is **not** the step-8 unblocker and should not
be scheduled as if it were. The unblocker is getting one worker runtime
registered for the owner's universe.
